"""Check drafts, source synchronization, generated files and runtime evidence."""
import hashlib
import xml.etree.ElementTree as ET

import config
from build import collect_expected
from common import (entry_identity, load_drafts, load_status, placeholders,
                    runtime_records, semantic_hash)
from draft import updated_draft


def source_errors(drafts, status):
    errors = []
    mods = {m['package_id']: m for m in status['mods']}
    by_package = {d['package_id']: d for _, d in drafts}
    for package, mod in mods.items():
        if mod['entries'] and package not in by_package:
            errors.append(f'{package}: neue offene Einträge ohne Draft; draft --all ausführen')
    for path, draft in drafts:
        expected = updated_draft(draft, mods.get(draft['package_id']))
        if expected != draft:
            errors.append(f'{path.name}: Draft/Status nicht synchron (needed, Englisch oder Def-Auflösung); draft --all ausführen')
        for e in draft['entries']:
            if e['german'].strip() and placeholders(e['english']) != placeholders(e['german']):
                errors.append(f'{path.name}: Placeholder-Abweichung: {entry_identity(e)}')
    return errors


def runtime_errors(expected, directory):
    actual = {p.relative_to(directory): p for p in directory.rglob('*') if p.is_file()}
    errors = [f'Runtime-Datei fehlt: {p}' for p in sorted(expected.keys() - actual.keys())]
    errors += [f'Unerwartete/veraltete Runtime-Datei: {p}' for p in sorted(actual.keys() - expected.keys())]
    for rel in sorted(expected.keys() & actual.keys()):
        if actual[rel].is_symlink() or actual[rel].read_bytes() != expected[rel]:
            errors.append(f'Runtime-Inhalt abweichend: {rel}')
    try:
        runtime_records(directory)
    except (ValueError, ET.ParseError) as exc:
        errors.append(str(exc))
    return errors


def runtime_confirmed(package, records, status):
    subset = {k: v for k, v in records.items() if v['package_id'] == package}
    snapshot = status['runtime'].get(package, {})
    return bool(subset and snapshot.get('confirmed') and snapshot.get('sha256') == semantic_hash(subset))


def run():
    status = load_status()
    drafts = load_drafts()
    errors = source_errors(drafts, status)
    expected, included, excluded = collect_expected(drafts)
    output_errors = runtime_errors(expected, config.LANG)
    errors.extend(output_errors)
    current_config = hashlib.sha256(config.MODS_CONFIG.read_bytes()).hexdigest()
    config_matches = current_config == status['mods_config_sha256']
    if not config_matches:
        errors.append('Aktive Mods seit refresh geändert; refresh ausführen')
    print(f'Build-Bestand: {len(included)} enthaltene, {len(excluded)} unvollständige Drafts')
    print('Lokale Verifikation: ' + ('✗' if errors else '✓ lokal konsistent'))
    for message in errors:
        print(f'FEHLER: {message}')
    if not output_errors:
        records = runtime_records(config.LANG)
        for package in included:
            confirmed = config_matches and runtime_confirmed(package, records, status)
            print(f"Runtime: {'✓' if confirmed else 'ausstehend'} {package}")
    print('Runtime-Aussage bezieht sich auf den gespeicherten Report und die aktive Modkonfiguration.')
    if errors:
        raise ValueError(f'Verifikation fehlgeschlagen: {len(errors)} Fehler')
