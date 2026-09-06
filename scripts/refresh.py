"""Analyze a local copy of the newest RimWorld TranslationReport."""
from collections import Counter, defaultdict
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
import re

import config
from common import OWN_PACKAGE, atomic_write, load_json, runtime_records, semantic_hash, write_json
from sources import source_def_types


def report_metadata(path):
    content = path.read_bytes()
    text = content.decode('utf-8-sig')
    heading = re.fullmatch(r'Translation report for (.+)', text.splitlines()[0] if text else '')
    if not heading:
        raise ValueError('Report-Sprache nicht eindeutig angegeben')
    language = heading[1]
    config.validate_languages([language])
    for title in ('Missing keyed translations', 'Def-injected translations missing'):
        if not re.search(r'^========== ' + title + r' \(\d+\)', text, re.M):
            raise ValueError(f'Report-Abschnitt fehlt: {title}')
    return content, {'language': language, 'source': str(path), 'mtime_ns': path.stat().st_mtime_ns,
                     'sha256': hashlib.sha256(content).hexdigest()}


def dedupe_resolved_def_entries(entries):
    """Collapse identical Def report entries after concrete type resolution.

    RimWorld can report the same DefInjected path both through a base Def type
    and through its concrete Def type.  Once source resolution maps both to the
    same concrete type they represent one translation identity.

    Conflicting records for the same resolved identity remain a hard error.
    """
    result = []
    seen = {}

    for entry in entries:
        if entry['type'] != 'def':
            result.append(entry)
            continue

        ident = (entry['def_type'], entry['path'])
        previous = seen.get(ident)

        if previous is None:
            seen[ident] = entry
            result.append(entry)
            continue

        if previous != entry:
            raise ValueError(
                f'Widersprüchliche aufgelöste Def-Einträge: {ident}'
            )

    return result


def mark_runtime_echoes(entries, package_id, records):
    for entry in entries:
        if entry['type'] == 'keyed':
            ident = ('keyed', '', entry['key'])
        elif entry.get('def_resolution') == 'resolved':
            ident = ('def', entry['def_type'], entry['path'])
        else:
            continue

        runtime = records.get(ident)
        if (
            runtime
            and runtime['package_id'] == package_id
            and runtime['text'] == entry['english']
        ):
            entry['runtime_echo'] = True


def canonical_missing(rows):
    result = {}

    for row in rows:
        identities = []
        def_paths = set()

        for entry in row['entries']:
            if entry.get('runtime_echo'):
                continue

            if entry['type'] == 'keyed':
                identities.append(['keyed', '', entry['key']])
            else:
                identities.append(
                    ['def', entry['def_type'], entry['path']]
                )
                def_paths.add(entry['path'])

        result[row['package_id']] = {
            'identities': identities,
            'def_paths': sorted(def_paths),
        }

    return result


def runtime_snapshot(records, report, active, config_hash, config_mtime, previous, errors):
    result = {}
    order_ok = OWN_PACKAGE in active
    own_position = active.index(OWN_PACKAGE) if order_ok else -1
    for package in sorted({v['package_id'] for v in records.values()}):
        subset = {k: v for k, v in records.items() if v['package_id'] == package}
        digest = semantic_hash(subset)
        files = [p for p in config.language_dir(report['language']).rglob('*.xml') if p.stem == package]
        last_write = max(p.stat().st_mtime_ns for p in files)
        old = previous.get('runtime', {}).get(package, {})
        # An untagged old snapshot can be bound to this language only through
        # the identical report bytes (SHA256), whose header we just validated.
        same_evidence = (previous.get('report', {}).get('language') in (None, report['language'])
                         and old.get('confirmed') and old.get('sha256') == digest
                         and previous.get('report', {}).get('sha256') == report['sha256']
                         and previous.get('mods_config_sha256') == config_hash)
        fresh = report['mtime_ns'] >= max(last_write, config_mtime) or bool(same_evidence)
        canonical = report.get('canonical_missing')

        if canonical is None:
            # Compatibility with older status/report structures.
            absent = not any(
                list(k) in report['missing_identities']
                for k in subset
            )
            # Report Def types can be short; compare paths as well.
            absent = absent and not any(
                k[0] == 'def'
                and k[2] in report['missing_def_paths']
                for k in subset
            )
        else:
            missing = canonical.get(
                package,
                {'identities': [], 'def_paths': []},
            )
            identities = {
                tuple(value)
                for value in missing['identities']
            }
            def_paths = set(missing['def_paths'])

            absent = not any(
                key in identities
                or (
                    key[0] == 'def'
                    and key[2] in def_paths
                )
                for key in subset
            )
        no_errors = not any(k[2] in line for k in subset for line in errors)
        enabled = order_ok and package in active and active.index(package) < own_position
        result[package] = {'sha256': digest, 'confirmed': bool(fresh and absent and enabled and no_errors),
                           'fresh': fresh, 'missing': not absent, 'load_errors': not no_errors,
                           'active_in_order': enabled, 'entries': len(subset)}
    return result


def run(language=None):
    language = config.select_language(language)
    reports = [p for p in config.REPORT_DIR.iterdir()
               if p.is_file() and re.fullmatch(r'translationreport.*\.txt', p.name, re.I)]
    if not reports:
        raise ValueError(f'Kein TranslationReport unter {config.REPORT_DIR}')
    matching = []
    for path in reports:
        with path.open(encoding='utf-8-sig') as stream:
            heading = stream.readline().rstrip('\r\n')
        if heading == f'Translation report for {language}':
            matching.append(path)
    if not matching:
        raise ValueError(f'Kein Report mit expliziter Sprache {language!r} unter {config.REPORT_DIR}')
    latest = max(matching, key=lambda p: (p.stat().st_mtime_ns, p.name))
    content, report = report_metadata(latest)
    previous_path = config.DATA / 'status.json'
    previous = load_json(previous_path) if previous_path.exists() else {}
    # Replace even an old report symlink; the external report remains read-only.
    atomic_write(config.DATA / 'TranslationReport.txt', content)
    spec = importlib.util.spec_from_file_location('rw_analyzer', config.ROOT / 'scripts/analyze-report.py')
    analyzer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(analyzer)
    with redirect_stdout(io.StringIO()) as output:
        analysis = analyzer.main()
    atomic_write(config.DATA / 'analyzer.log', output.getvalue().encode())
    text = content.decode('utf-8-sig')
    for title, entries in (('Missing keyed translations', analysis['keyed']), ('Def-injected translations missing', analysis['defs'])):
        count = int(re.search(r'^========== ' + title + r' \((\d+)\)', text, re.M)[1])
        if len(entries) != count:
            raise ValueError(f'Report unvollständig geparst: {title}: {len(entries)}/{count}; Status nicht ersetzt')
    active = analysis['active']
    mod_config_bytes = config.MODS_CONFIG.read_bytes()
    config_hash = hashlib.sha256(mod_config_bytes).hexdigest()
    by_package = {}
    for mod in analysis['mods']:
        if mod['package_id'] in by_package:
            raise ValueError(f'Mehrere Installationen derselben Package-ID: {mod["package_id"]}; Status nicht ersetzt')
        by_package[mod['package_id']] = mod
    records = runtime_records(config.language_dir(language))
    rows = []
    resolver = Counter()
    for package in active:
        source = by_package.get(package)
        index = source_def_types(source['root']) if source else {}
        entries = [dict(e) for e in analysis['mapped'] if e['package_id'] == package]
        for e in entries:
            if e['type'] != 'def':
                continue
            candidates = index.get(e['def_name'], set())
            matching = [t for t in candidates if t == e['def_type'] or t.endswith('.' + e['def_type'])]
            full = next(iter(candidates)) if len(candidates) == 1 else matching[0] if len(matching) == 1 else None
            e['def_resolution'] = 'resolved' if full else 'ambiguous' if candidates else 'missing'
            if full:
                e['def_type'] = full

        entries = dedupe_resolved_def_entries(entries)
        resolver.update(
            e['def_resolution']
            for e in entries
            if e['type'] == 'def'
        )
        mark_runtime_echoes(entries, package, records)

        paths = defaultdict(list)
        for e in entries:
            if e['type'] == 'def':
                paths[e['path']].append(e)
        for group in paths.values():
            if len(group) > 1:
                for e in group:
                    e['identity_scope'] = e['def_type'].rsplit('.', 1)[-1]
        counts = Counter(e['type'] for e in entries)
        rows.append({'package_id': package, 'name': source['name'] if source else package,
                     'workshop_id': (
                         source['source']
                         if source and str(source.get('source', '')).isdigit()
                         else None
                     ),
                     'source_found': bool(source), 'entries': entries,
                     'counts': {'open': len(entries), 'keyed': counts['keyed'], 'def': counts['def']},
                     'def_types': {key: sorted(value) for key, value in sorted(index.items())}})
    report['missing_identities'] = [['keyed', '', e[0]] for e in analysis['keyed']]
    report['missing_identities'] += [['def', e[0], e[2]] for e in analysis['defs']]
    report['missing_def_paths'] = sorted({e[2] for e in analysis['defs']})
    report['canonical_missing'] = canonical_missing(rows)
    errors = analyzer.extract_section(text.splitlines(), 'Def-injected translations load errors')
    errors += analyzer.extract_section(text.splitlines(), 'General load errors')
    runtime = runtime_snapshot(records, report, active, config_hash,
                               config.MODS_CONFIG.stat().st_mtime_ns, previous, errors)
    mapped_count = sum(len(row['entries']) for row in rows)
    status = {'schema': 1, 'report': report, 'mods_config_sha256': config_hash,
              'counts': {'keyed': len(analysis['keyed']), 'def': len(analysis['defs']),
                         'mapped': mapped_count, 'ambiguous': len(analysis['ambiguous']),
                         'unmapped': len(analysis['unmapped'])},
              'resolver': dict(resolver), 'active_mods': active, 'mods': rows, 'runtime': runtime}
    write_json(previous_path, status)
    # Preserve the existing analyzer's resolved JSONL interface as well.
    atomic_write(config.DATA / 'report-mapped.jsonl', ''.join(
        json.dumps(e, ensure_ascii=False, sort_keys=True) + '\n'
        for m in rows for e in m['entries']).encode())
    print(f'Report {language}: {latest.name} | Keyed: {len(analysis["keyed"])} | DefInjected: {len(analysis["defs"])}')
    print(f'Aktiv: {len(active)} | Zugeordnet: {mapped_count} | Mehrdeutig: {len(analysis["ambiguous"])} | Unmapped: {len(analysis["unmapped"])}')
    print(f'Def-Resolver: {dict(resolver)} | Status: {previous_path}')
