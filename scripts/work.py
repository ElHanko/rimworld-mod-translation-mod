"""Create a bounded temporary work package from a durable draft."""
from copy import deepcopy

import config
from common import load_drafts, select_draft, work_entries, translation_state, write_json


def choose_draft(drafts, selector=None, language=None):
    language = config.select_language(language)
    if selector:
        return select_draft(drafts, selector)
    candidates = [item for item in drafts if work_entries(item[1], language)]
    if not candidates:
        raise ValueError('Keine offenen Übersetzungen mehr vorhanden.')
    return min(candidates, key=lambda item: (len(work_entries(item[1], language)), item[1]['package_id'].casefold()))


def make_work(drafts, selector=None, limit=25, offset=0, language=None):
    language = config.select_language(language)

    if any(
        translation_state(entry, language)['needed'] is None
        for _, draft in drafts
        for entry in draft['entries']
    ):
        raise ValueError(
            f'Übersetzungsbedarf für {language} unbekannt; '
            f'refresh --language {language} und danach draft --all ausführen'
        )

    if limit < 1 or offset < 0:
        raise ValueError('--limit muss positiv und --offset nicht negativ sein')
    path, draft = choose_draft(drafts, selector, language)
    opened = work_entries(draft, language)
    selected = opened[offset:offset + limit]
    if not selected:
        raise ValueError('Für diesen Bereich gibt es keine offenen Einträge.')
    entries = deepcopy(selected)
    for e in entries:
        state = translation_state(e, language)
        e.pop('needed', None)
        e.pop('translations')
        e.update(translation=state['text'], original_translation=state['text'], review=state['review'])
        if 'previous_english' in state:
            e['previous_english'] = state['previous_english']
    return {'language': language, 'package_id': draft['package_id'], 'name': draft['name'], 'draft_file': path.name,
            'offset': offset, 'open_total': len(opened), 'entries': entries}


def run(selector=None, limit=25, offset=0, language=None):
    work = make_work(load_drafts(), selector, limit, offset, language)
    out = config.DATA / 'work' / (work['package_id'] + '.' + work['language'] + '.work.json')
    write_json(out, work)
    print(f"{work['name']}: {len(work['entries'])} von {work['open_total']} offenen Einträgen (Offset {offset})")
    print(f'Arbeitsdatei: {out}')
