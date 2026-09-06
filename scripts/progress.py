"""Display durable draft progress."""
from collections import Counter
from common import load_drafts, select_draft


def state(draft):
    needed = [e for e in draft['entries'] if e['needed']]
    return {'needed': len(needed), 'translated': sum(bool(e['german'].strip()) for e in needed),
            'open': sum(not e['german'].strip() for e in needed),
            'review': sum(e['review'] for e in needed), 'retired': len(draft['entries']) - len(needed)}


def run(selector=None):
    drafts = load_drafts()
    if selector:
        drafts = [select_draft(drafts, selector)]
    print(' OFFEN REVIEW BENÖTIGT ÜBERSETZT INAKTIV   PACKAGE-ID NAME')
    totals = Counter()
    for _, draft in drafts:
        s = state(draft)
        totals.update(s)
        marker = '✓' if not s['open'] and not s['review'] else ' '
        print(f"{s['open']:6} {s['review']:6} {s['needed']:8} {s['translated']:9} {s['retired']:7} {marker} {draft['package_id']} {draft['name']}")
    print(f"Benötigt: {totals['needed']} | Übersetzt: {totals['translated']} | Offen: {totals['open']} | Review: {totals['review']} | Nicht mehr benötigt: {totals['retired']}")
