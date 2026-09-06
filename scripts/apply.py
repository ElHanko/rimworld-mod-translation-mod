"""Validate the entire work package before atomically replacing its draft."""
from copy import deepcopy
from pathlib import Path

from common import entry_identity, index_entries, load_drafts, load_json, placeholders, write_json


def apply_work(work, drafts):
    if not isinstance(work, dict) or not isinstance(work.get('entries'), list):
        raise ValueError('Ungültiges Arbeitspaket')
    matches = [(p, d) for p, d in drafts if p.name == work.get('draft_file')]
    if len(matches) != 1:
        raise ValueError('draft_file verweist nicht auf genau einen existierenden Draft')
    path, original = matches[0]
    if work.get('package_id') != original['package_id']:
        raise ValueError('Package-ID passt nicht zum Draft')
    draft = deepcopy(original)
    targets = index_entries(draft['entries'])
    seen = set()
    applied = 0
    for item in work['entries']:
        if not isinstance(item, dict):
            raise ValueError('Work-Eintrag muss ein Objekt sein')
        try:
            ident = entry_identity(item)
        except KeyError as exc:
            raise ValueError(f'Work-Identität fehlt: {exc}') from exc
        if ident in seen:
            raise ValueError(f'Doppelter Work-Eintrag: {ident}')
        seen.add(ident)
        target = targets.get(ident)
        if target is None:
            raise ValueError(f'Entry existiert nicht mehr: {ident}')
        if not target['needed']:
            raise ValueError(f'Entry nicht mehr benötigt: {ident}')
        if item.get('english') != target['english']:
            raise ValueError(f'Englischer Quelltext inzwischen geändert: {ident}')
        if item.get('original_german') != target['german']:
            raise ValueError(f'Deutscher Draft inzwischen geändert: {ident}; neues Arbeitspaket erstellen')
        if item.get('package_id', draft['package_id']) != draft['package_id']:
            raise ValueError(f'Falsche Entry-Package-ID: {ident}')
        german = item.get('german')
        if not isinstance(german, str):
            raise ValueError(f'German muss String sein: {ident}')
        if not german.strip():
            continue
        if placeholders(german) != placeholders(target['english']):
            raise ValueError(f'Placeholder-Abweichung: {ident}')
        target.update(german=german, review=False)
        target.pop('previous_english', None)
        applied += 1
    return path, draft, applied


def run(filename):
    path, draft, count = apply_work(load_json(Path(filename).expanduser()), load_drafts())
    if count:
        write_json(path, draft)
    print(f'Übernommen: {count}; Draft: {path}')
