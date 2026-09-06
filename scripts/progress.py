"""Display durable draft progress."""
from collections import Counter
import config
from common import load_drafts, select_draft, translation_state


def state(draft, language=None):
    language = config.select_language(language)

    states = [
        (entry, translation_state(entry, language))
        for entry in draft['entries']
    ]
    needed = [
        (entry, state)
        for entry, state in states
        if state['needed'] is True
    ]

    return {
        'needed': len(needed),
        'translated': sum(bool(state['text'].strip()) for _, state in needed),
        'open': sum(not state['text'].strip() for _, state in needed),
        'review': sum(state['review'] for _, state in needed),
        'retired': sum(state['needed'] is False for _, state in states),
        'unknown': sum(state['needed'] is None for _, state in states),
    }


def run(selector=None, language=None):
    drafts = load_drafts()
    if selector:
        drafts = [select_draft(drafts, selector)]
    for language in config.selected_languages(language):
        print(f'Sprache: {language}')
        print(' OFFEN REVIEW BENÖTIGT ÜBERSETZT INAKTIV UNBEKANNT   PACKAGE-ID NAME')
        totals = Counter()
        for _, draft in drafts:
            s = state(draft, language)
            totals.update(s)
            marker = '✓' if not s['open'] and not s['review'] else ' '
            print(f"{s['open']:6} {s['review']:6} {s['needed']:8} {s['translated']:9} {s['retired']:7} {s['unknown']:9} {marker} {draft['package_id']} {draft['name']}")
        print(f"Benötigt: {totals['needed']} | Übersetzt: {totals['translated']} | Offen: {totals['open']} | Review: {totals['review']} | Nicht mehr benötigt: {totals['retired']} | Unbekannt: {totals['unknown']}")
