"""Display the last status snapshot without re-analyzing sources."""
import config
from common import load_status


def run(language=None):
    status = load_status()
    if language is not None and config.select_language(language) != status['report']['language']:
        raise ValueError(f"Status gehört zu {status['report']['language']}; refresh --language {language} ausführen")
    print(f"Report-Sprache: {status['report']['language']}")
    print(' OFFEN KEYED   DEF UNSERE   PACKAGE-ID NAME')
    for mod in sorted(status['mods'], key=lambda m: (-m['counts']['open'], m['package_id'])):
        c = mod['counts']
        ours = status['runtime'].get(mod['package_id'], {}).get('entries', 0)
        marker = '✓' if c['open'] == 0 else ' '
        print(f"{c['open']:6} {c['keyed']:5} {c['def']:5} {ours:6} {marker} {mod['package_id']} {mod['name']}")
    print(f"Report: {status['report']['source']}")
    print(f"Gesamt: {status['counts']}")
