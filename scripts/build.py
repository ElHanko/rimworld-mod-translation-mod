"""Compute and safely replace the complete deterministic RimWorld XML tree."""
from collections import defaultdict
from pathlib import Path
import shutil
import tempfile
import xml.etree.ElementTree as ET

import config
from common import entry_ready, load_drafts, runtime_identity, runtime_records, validate_draft


def collect_expected(drafts):
    files = defaultdict(list)
    shared = {}
    included = []
    excluded = []
    for path, draft in sorted(drafts, key=lambda item: item[0].name):
        validate_draft(path, draft)
        entries = draft['entries']
        if any(e['needed'] and not entry_ready(e) for e in entries):
            excluded.append(draft['package_id'])
            continue
        selected = [e for e in entries if e['needed'] and entry_ready(e)]
        if not selected:
            continue
        included.append(draft['package_id'])
        for e in sorted(selected, key=runtime_identity):
            ident = runtime_identity(e)
            texts = e['english'], e['german']
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
            ET.SubElement(root, runtime_identity(e)[2]).text = e['german']
        ET.indent(root, space='  ')
        content = ET.tostring(root, encoding='utf-8', xml_declaration=True, short_empty_elements=False)
        # Validate XML names, characters and exact text roundtripping before touching output.
        parsed = ET.fromstring(content)
        if [(n.tag, n.text) for n in parsed] != [(runtime_identity(e)[2], e['german']) for e in entries]:
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
    output = stage / 'German'
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


def run():
    expected, included, excluded = collect_expected(load_drafts())
    replace_runtime(expected, config.LANG)
    records = runtime_records(config.LANG)
    print(f'Build: ✓ | {len(included)} Drafts | {len(records)} Einträge | {len(expected)} XML-Dateien | {len(excluded)} unvollständige Drafts ausgeschlossen')
