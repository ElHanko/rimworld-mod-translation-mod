"""Compute and safely replace the complete deterministic RimWorld XML tree."""
from collections import defaultdict
from pathlib import Path
import shutil
import tempfile
import xml.etree.ElementTree as ET

import config
from common import entry_ready, load_drafts, runtime_identity, runtime_records, validate_draft, translation_state


def collect_expected(drafts, language=None):
    language = config.select_language(language)
    files = defaultdict(list)
    shared = {}
    included = []
    excluded = []
    for path, draft in sorted(drafts, key=lambda item: item[0].name):
        validate_draft(path, draft)
        entries = draft['entries']
        states = [
            (entry, translation_state(entry, language))
            for entry in entries
        ]

        if any(state['needed'] is None for _, state in states):
            raise ValueError(
                f"{draft['package_id']} ({language}): Übersetzungsbedarf unbekannt; "
                f"refresh --language {language} und danach draft --all ausführen"
            )

        needed = [
            entry
            for entry, state in states
            if state['needed'] is True
        ]

        if any(not entry_ready(entry, language) for entry in needed):
            excluded.append(draft['package_id'])
            continue

        selected = [
            entry
            for entry in needed
            if entry_ready(entry, language)
        ]
        if not selected:
            continue
        included.append(draft['package_id'])
        for e in sorted(selected, key=runtime_identity):
            ident = runtime_identity(e)
            texts = e['english'], translation_state(e, language)['text']
            if ident in shared:
                previous, owner = shared[ident]
                if previous != texts:
                    raise ValueError(f'Duplicate-Konflikt {ident}: {owner} / {draft["package_id"]}')
                continue
            shared[ident] = texts, draft['package_id']
            folder = Path('Keyed') if e['type'] == 'keyed' else Path('DefInjected') / e['def_type']
            files[folder / (draft['package_id'] + '.xml')].append(e)
    expected = {}
    for rel, entries in sorted(files.items()):
        root = ET.Element('LanguageData')
        for e in entries:
            ET.SubElement(root, runtime_identity(e)[2]).text = translation_state(e, language)['text']
        ET.indent(root, space='  ')
        content = ET.tostring(root, encoding='utf-8', xml_declaration=True, short_empty_elements=False)
        # Validate XML names, characters and exact text roundtripping before touching output.
        parsed = ET.fromstring(content)
        if [(n.tag, n.text) for n in parsed] != [(runtime_identity(e)[2], translation_state(e, language)['text']) for e in entries]:
            raise ValueError(f'XML verändert Übersetzungstext: {rel}')
        expected[rel] = content
    return expected, included, excluded


def replace_runtime(expected, directory):
    directory.parent.mkdir(parents=True, exist_ok=True)
    if directory.is_symlink() or any(p.is_symlink() for p in directory.rglob('*')):
        raise ValueError('Runtime-Bestand enthält Symlinks; keine Änderung vorgenommen')
    # Leave byte-identical trees in place (also preserves runtime timestamps).
    actual = {p.relative_to(directory): p.read_bytes() for p in directory.rglob('*') if p.is_file()}
    if actual == expected:
        return
    stage = Path(tempfile.mkdtemp(prefix='.rwgt-build-', dir=directory.parent))
    backup = stage / 'previous'
    output = stage / directory.name
    output.mkdir()
    try:
        for rel, content in expected.items():
            path = output / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        runtime_records(output)
        if directory.exists():
            directory.rename(backup)
        try:
            output.rename(directory)
        except BaseException:
            if backup.exists():
                backup.rename(directory)
            raise
    finally:
        # Preserve the backup if rollback itself failed.
        if not backup.exists() or directory.exists():
            shutil.rmtree(stage)


def run(language=None):
    drafts = load_drafts()
    # Validate every selected language before any output is replaced.
    plans = [(language, collect_expected(drafts, language))
             for language in config.selected_languages(language)]
    for language, (expected, included, excluded) in plans:
        directory = config.language_dir(language)
        replace_runtime(expected, directory)
        records = runtime_records(directory)
        print(f'Build {language}: ✓ | {len(included)} Drafts | {len(records)} Einträge | {len(expected)} XML-Dateien | {len(excluded)} unvollständige Drafts ausgeschlossen')
