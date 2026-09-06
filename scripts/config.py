"""Repository paths and the single private configuration loader."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'
TRANSLATIONS = ROOT / 'translations'
LANG_ROOT = ROOT / 'Languages'
LANGUAGES = ['German']  # Compatibility default for existing local configurations.


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
        result['languages'] = validate_languages(values.get('languages', ['German']))
        return result
    except (OSError, ValueError) as exc:
        raise ValueError(f'Lokale Config {path}: {exc}. Siehe rwgt.example.json.') from exc


def configure():
    global GAME, WORKSHOP, RIMWORLD_HOME, REPORT_DIR, LOCAL_MODS, MODS_CONFIG, LANGUAGES
    values = load_config()
    LANGUAGES = values['languages']
    GAME = values['game']
    WORKSHOP = values['workshop']
    RIMWORLD_HOME = values['rimworld_home']
    REPORT_DIR = values['report_dir']
    LOCAL_MODS = GAME / 'Mods'
    MODS_CONFIG = RIMWORLD_HOME / 'Config' / 'ModsConfig.xml'


def validate_languages(languages):
    if not isinstance(languages, list) or not languages:
        raise ValueError('languages muss eine nichtleere Liste sein')
    seen = set()
    for name in languages:
        if (not isinstance(name, str) or not name or name != name.strip()
                or name in ('.', '..') or any(c in name for c in '/\\:')
                or any(ord(c) < 32 for c in name)):
            raise ValueError(f'Ungültiger Sprach-/Verzeichnisname: {name!r}')
        if name.casefold() in seen:
            raise ValueError(f'Doppelte Sprache: {name}')
        seen.add(name.casefold())
    return languages


def select_language(language=None):
    if language is None:
        if len(LANGUAGES) != 1:
            raise ValueError('Mehrere Zielsprachen konfiguriert; --language angeben')
        return LANGUAGES[0]
    if language not in LANGUAGES:
        raise ValueError(f'Sprache nicht konfiguriert: {language!r}')
    return language


def selected_languages(language=None):
    return [select_language(language)] if language is not None else LANGUAGES


def language_dir(language):
    validate_languages([language])
    return LANG_ROOT / language
