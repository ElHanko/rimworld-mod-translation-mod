"""Create a bounded temporary work package from a durable draft."""
from copy import deepcopy

import config
from common import load_drafts, select_draft, work_entries, write_json


def choose_draft(drafts, selector=None):
    if selector:
        return select_draft(drafts, selector)
    candidates = [item for item in drafts if work_entries(item[1])]
    if not candidates:
        raise ValueError('Keine offenen Übersetzungen mehr vorhanden.')
    return min(candidates, key=lambda item: (len(work_entries(item[1])), item[1]['package_id'].casefold()))


def make_work(drafts, selector=None, limit=25, offset=0):
    if limit < 1 or offset < 0:
        raise ValueError('--limit muss positiv und --offset nicht negativ sein')
    path, draft = choose_draft(drafts, selector)
    opened = work_entries(draft)
    selected = opened[offset:offset + limit]
    if not selected:
        raise ValueError('Für diesen Bereich gibt es keine offenen Einträge.')
    entries = deepcopy(selected)
    for e in entries:
        e.pop('needed', None)
        # Prevent an old work package from overwriting a later German edit.
        e['original_german'] = e['german']
    return {'package_id': draft['package_id'], 'name': draft['name'], 'draft_file': path.name,
            'offset': offset, 'open_total': len(opened), 'entries': entries}


def run(selector=None, limit=25, offset=0):
    work = make_work(load_drafts(), selector, limit, offset)
    out = config.DATA / 'work' / (work['package_id'] + '.work.json')
    if out.exists():
        raise ValueError(f'Arbeitspaket existiert bereits: {out}. Erst anwenden oder lokal umbenennen/entfernen.')
    write_json(out, work)
    print(f"{work['name']}: {len(work['entries'])} von {work['open_total']} offenen Einträgen (Offset {offset})")
    print(f'Arbeitsdatei: {out}')
