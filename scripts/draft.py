"""Merge current report requirements into durable translation drafts."""
from copy import deepcopy
from collections import Counter

import config
from common import entry_identity, index_entries, load_drafts, load_status, write_json


def merge_entries(current, previous):
    old = index_entries(previous)
    index_entries(current)
    result = []
    path_counts = Counter(entry_identity(e)[:2] for e in current)
    for source in current:
        before = old.pop(entry_identity(source), None)
        if before is None and source['type'] == 'def':
            candidates = [(key, e) for key, e in old.items()
                          if key[:2] == entry_identity(source)[:2]]
            matching = [(key, e) for key, e in candidates
                        if e['def_type'].rsplit('.', 1)[-1] == source['def_type'].rsplit('.', 1)[-1]]
            if len(matching) == 1:
                before = old.pop(matching[0][0])
            elif len(candidates) == 1 and path_counts[entry_identity(source)[:2]] == 1:
                before = old.pop(candidates[0][0])
            elif candidates:
                raise ValueError(f'Def-Identität nicht eindeutig migrierbar: {source["path"]}')
        entry = dict(before or {})
        entry.update(source)
        entry.update(needed=True, german=before['german'] if before else '',
                     review=before.get('review', False) if before else False)
        if before and before['english'] != source['english']:
            entry['review'] = True
            entry['previous_english'] = before.get('previous_english', before['english'])
        result.append(entry)
    for before in old.values():
        entry = deepcopy(before)
        # A disappearing requirement may mean our own translation now works.
        entry['needed'] = before['needed'] and bool(before['german'].strip())
        result.append(entry)
    order = {entry_identity(e): i for i, e in enumerate(previous)}
    return sorted(result, key=lambda e: (order.get(entry_identity(e), len(order)), entry_identity(e)))


def updated_draft(draft, mod):
    result = deepcopy(draft)
    result['name'] = mod['name'] if mod else draft['name']
    result['entries'] = merge_entries(mod['entries'] if mod else [], draft['entries'])
    # Re-resolve preserved Defs too, without changing their stable identities.
    if mod:
        for entry in result['entries']:
            if entry['type'] == 'def':
                resolution = mod['def_types'].get(entry['def_name'])
                if resolution:
                    candidates = resolution
                    matching = [t for t in candidates if t == entry['def_type'] or t.endswith('.' + entry['def_type'])]
                    full = candidates[0] if len(candidates) == 1 else matching[0] if len(matching) == 1 else None
                    entry['def_resolution'] = 'resolved' if full else 'ambiguous'
                    if full:
                        entry['def_type'] = full
                else:
                    entry['def_resolution'] = 'missing'
    return result


def run(selector):
    status = load_status()
    existing = {d['package_id']: (p, d) for p, d in load_drafts()}
    mods = {m['package_id']: m for m in status['mods']}
    if selector == '--all':
        packages = set(existing) | {p for p, m in mods.items() if m['entries']}
    else:
        matches = [p for p in set(existing) | set(mods) if p.casefold() == selector.casefold()]
        if len(matches) != 1:
            raise ValueError(f'Keine eindeutige Package-ID: {selector}')
        packages = set(matches)
    pending = []
    for package in sorted(packages):
        if package in existing:
            path, draft = existing[package]
        else:
            path = config.TRANSLATIONS / (package + '.json')
            draft = {'package_id': package, 'name': mods[package]['name'], 'entries': []}
        pending.append((path, updated_draft(draft, mods.get(package))))
    for path, draft in pending:
        write_json(path, draft)
    print(f'Drafts aktualisiert: {len(pending)}')
