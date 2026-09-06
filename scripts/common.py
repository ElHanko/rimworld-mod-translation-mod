"""Shared draft identities, validation and local file operations."""
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import xml.etree.ElementTree as ET

import config

OWN_PACKAGE = 'elhanko.rimworld.germantranslations'
_SIMPLE_PLACEHOLDER = re.compile(r'\{(?:\d+|[A-Za-z_][A-Za-z0-9_]*)\}')


def placeholders(text):
    return Counter(_SIMPLE_PLACEHOLDER.findall(text))


def load_json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ValueError(f'{path}: {exc}') from exc


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    # os.replace replaces a symlink itself; never write through it.
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temp = Path(stream.name)
        try:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temp.unlink()
            raise
    try:
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def write_json(path, data):
    atomic_write(path, (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode())


def load_status():
    path = config.DATA / 'status.json'
    if not path.is_file():
        raise ValueError("Zuerst './rwgt refresh' ausführen.")
    data = load_json(path)
    if not isinstance(data, dict) or data.get('schema') != 1 or not isinstance(data.get('mods'), list):
        raise ValueError("Ungültiger Status. Zuerst './rwgt refresh' ausführen.")
    return data


def safe_component(value):
    return isinstance(value, str) and bool(re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*', value))


def entry_identity(entry):
    if not isinstance(entry, dict):
        raise ValueError('Eintrag muss ein Objekt sein')
    kind = entry.get('type')
    field = 'key' if kind == 'keyed' else 'path'
    key = entry.get(field)
    if kind not in ('keyed', 'def') or not isinstance(key, str) or not key:
        raise ValueError(f'Ungültige Eintragsidentität: {kind!r}/{key!r}')
    if kind == 'keyed':
        return kind, key
    # Full def_type is correctable metadata, not the stable draft identity.
    scope = entry.get('identity_scope', '')
    if not isinstance(scope, str):
        raise ValueError('identity_scope muss String sein')
    return kind, key, scope


def runtime_identity(entry):
    kind, key = entry_identity(entry)[:2]
    return kind, entry.get('def_type', '') if kind == 'def' else '', key


def index_entries(entries):
    result = {}
    for entry in entries:
        ident = entry_identity(entry)
        if ident in result:
            raise ValueError(f'Doppelter Eintrag: {ident}')
        result[ident] = entry
    return result


def validate_draft(path, draft):
    if not isinstance(draft, dict) or not safe_component(draft.get('package_id')):
        raise ValueError(f'{path}: ungültige Package-ID')
    if path.name != draft['package_id'] + '.json':
        raise ValueError(f'{path}: Dateiname passt nicht zur Package-ID')
    if not isinstance(draft.get('name'), str) or not isinstance(draft.get('entries'), list):
        raise ValueError(f'{path}: name/entries fehlen oder sind ungültig')
    for e in draft['entries']:
        if not isinstance(e, dict):
            raise ValueError(f'{path}: Eintrag muss ein Objekt sein')
        for field in ('english', 'german'):
            if not isinstance(e.get(field), str):
                raise ValueError(f'{path}: {field} muss String sein')
        if 'runtime' in e:
            raise ValueError(f'{path}: Runtime-Evidenz gehört in den lokalen Status, nicht in Draft-Einträge')
        for field in ('needed', 'review'):
            if type(e.get(field)) is not bool:
                raise ValueError(f'{path}: {field} muss Boolean sein')
        if 'previous_english' in e and not isinstance(e['previous_english'], str):
            raise ValueError(f'{path}: previous_english muss String sein')
        if e.get('package_id', draft['package_id']) != draft['package_id']:
            raise ValueError(f'{path}: Package-ID im Eintrag stimmt nicht')
        try:
            _, key = entry_identity(e)[:2]
        except KeyError as exc:
            raise ValueError(f'{path}: Identitätsfeld fehlt: {exc}') from exc
        if not isinstance(key, str) or not key:
            raise ValueError(f'{path}: leerer/ungültiger Key oder Def-Pfad')
        if 'identity_scope' in e and not safe_component(e['identity_scope']):
            raise ValueError(f'{path}: ungültiger identity_scope')
        if e['type'] == 'def':
            if not safe_component(e.get('def_type')) or not isinstance(e.get('def_name'), str) or not e['path'].startswith(e['def_name'] + '.'):
                raise ValueError(f'{path}: ungültige Def-Metadaten: {key}')
            if e.get('def_resolution') not in ('resolved', 'missing', 'ambiguous'):
                raise ValueError(f'{path}: def_resolution fehlt: {key}')
    index_entries(draft['entries'])


def load_drafts():
    result = []
    for path in sorted(config.TRANSLATIONS.glob('*.json')):
        if path.is_symlink():
            raise ValueError(f'Draft darf kein Symlink sein: {path}')
        draft = load_json(path)
        validate_draft(path, draft)
        result.append((path, draft))
    return result


def select_draft(drafts, selector):
    found = [item for item in drafts if item[1]['package_id'].casefold() == selector.casefold()]
    if len(found) != 1:
        raise ValueError(f'Kein eindeutiger Draft: {selector}')
    return found[0]


def work_entries(draft):
    return [e for e in draft['entries'] if e['needed'] and (not e['german'].strip() or e['review'])]


def entry_ready(e):
    return (bool(e['german'].strip()) and not e['review']
            and placeholders(e['english']) == placeholders(e['german'])
            and (e['type'] != 'def' or e.get('def_resolution') == 'resolved'))


def runtime_records(directory):
    records = {}
    for path in sorted(directory.rglob('*.xml')):
        rel = path.relative_to(directory)
        if rel.parts[0] == 'Keyed' and len(rel.parts) == 2:
            kind, def_type = 'keyed', ''
        elif rel.parts[0] == 'DefInjected' and len(rel.parts) == 3:
            kind, def_type = 'def', rel.parts[1]
        else:
            raise ValueError(f'Ungültiger Runtime-Pfad: {rel}')
        root = ET.parse(path).getroot()
        if root.tag != 'LanguageData':
            raise ValueError(f'{rel}: LanguageData fehlt')
        for node in root:
            ident = kind, def_type, node.tag
            if ident in records:
                raise ValueError(f'Doppelter Runtime-Key: {ident}')
            if list(node) or node.attrib:
                raise ValueError(f'{rel}: verschachtelter/attributierter Übersetzungseintrag')
            records[ident] = {'german': node.text or '', 'package_id': path.stem}
    return records


def semantic_hash(records):
    # Formatting and file ownership do not affect what RimWorld receives.
    content = sorted((list(k), v['german']) for k, v in records.items())
    return hashlib.sha256(json.dumps(content, ensure_ascii=False).encode()).hexdigest()
