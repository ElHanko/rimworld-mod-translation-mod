"""Repository paths and the single private configuration loader."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'
TRANSLATIONS = ROOT / 'translations'
LANG = ROOT / 'Languages' / 'German'


def load_config(path=None):
    path = path or ROOT / 'rwgt.local.json'
    try:
        values = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(values, dict):
            raise ValueError('JSON-Wurzel muss ein Objekt sein')
        result = {}
        for key in ('game', 'workshop', 'rimworld_home', 'report_dir'):
            value = values.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f'Pflichtwert {key!r} fehlt oder ist ungültig')
            target = Path(value).expanduser()
            if not target.is_absolute() or '\x00' in value:
                raise ValueError(f'{key!r} muss ein absoluter Pfad sein')
            result[key] = target
        return result
    except (OSError, ValueError) as exc:
        raise ValueError(f'Lokale Config {path}: {exc}. Siehe rwgt.example.json.') from exc


def configure():
    global GAME, WORKSHOP, RIMWORLD_HOME, REPORT_DIR, LOCAL_MODS, MODS_CONFIG
    values = load_config()
    GAME = values['game']
    WORKSHOP = values['workshop']
    RIMWORLD_HOME = values['rimworld_home']
    REPORT_DIR = values['report_dir']
    LOCAL_MODS = GAME / 'Mods'
    MODS_CONFIG = RIMWORLD_HOME / 'Config' / 'ModsConfig.xml'
