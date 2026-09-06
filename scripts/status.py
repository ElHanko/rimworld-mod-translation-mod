"""Display the last status snapshot without re-analyzing sources."""
from common import load_status


def run():
    status = load_status()
    print(' OFFEN KEYED   DEF UNSERE   PACKAGE-ID NAME')
    for mod in sorted(status['mods'], key=lambda m: (-m['counts']['open'], m['package_id'])):
        c = mod['counts']
        ours = status['runtime'].get(mod['package_id'], {}).get('entries', 0)
        marker = '✓' if c['open'] == 0 else ' '
        print(f"{c['open']:6} {c['keyed']:5} {c['def']:5} {ours:6} {marker} {mod['package_id']} {mod['name']}")
    print(f"Report: {status['report']['source']}")
    print(f"Gesamt: {status['counts']}")
