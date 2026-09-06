"""Isolated standard-library regression tests; never touch Steam/game files."""
from copy import deepcopy
from contextlib import redirect_stdout
from io import StringIO
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import apply
import build
import common
import config
import draft
import progress
import refresh
import sources
import verify
import work


def keyed(key='Hello', **changes):
    e = {'type': 'keyed', 'key': key, 'english': 'Hello {name}', 'german': '',
         'needed': True, 'review': False}
    e.update(changes)
    return e


def definition(**changes):
    e = {'type': 'def', 'path': 'News.label', 'def_name': 'News',
         'def_type': 'HugsLib.UpdateFeatureDef', 'def_resolution': 'resolved',
         'english': 'News', 'german': 'Neuigkeiten', 'needed': True,
         'review': False}
    e.update(changes)
    return e


def payload(entries=None, package='test.mod'):
    return {'package_id': package, 'name': 'Test', 'entries': entries if entries is not None else [keyed()]}


def pair(entries=None, package='test.mod'):
    return Path(package + '.json'), payload(entries, package)


def mod(entries=None, package='test.mod', def_types=None):
    return {'package_id': package, 'name': 'Test', 'entries': entries or [], 'def_types': def_types or {}}


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'rwgt.local.json'
        self.values = {key: self.temp.name for key in ('game', 'workshop', 'rimworld_home', 'report_dir')}

    def test_valid_and_derived_paths(self):
        self.path.write_text(json.dumps(self.values))
        self.assertEqual(config.load_config(self.path)['game'], Path(self.temp.name))
        with patch.object(config, 'ROOT', self.path.parent):
            config.configure()
            self.assertEqual(config.LOCAL_MODS, Path(self.temp.name) / 'Mods')
            self.assertEqual(config.MODS_CONFIG, Path(self.temp.name) / 'Config/ModsConfig.xml')

    def test_missing(self):
        with self.assertRaisesRegex(ValueError, 'rwgt.example.json'):
            config.load_config(self.path)

    def test_invalid_json(self):
        self.path.write_text('{')
        with self.assertRaisesRegex(ValueError, 'rwgt.example.json'):
            config.load_config(self.path)

    def test_missing_or_invalid_value(self):
        for value in (None, '', 2, [], 'relative/path'):
            with self.subTest(value=value):
                self.path.write_text(json.dumps(dict(self.values, game=value)))
                with self.assertRaisesRegex(ValueError, 'rwgt.example.json'):
                    config.load_config(self.path)

    def test_non_object(self):
        self.path.write_text('[]')
        with self.assertRaisesRegex(ValueError, 'Objekt'):
            config.load_config(self.path)


class DraftTests(unittest.TestCase):
    def test_preserves_german_and_adds_new(self):
        old = keyed(german='Hallo {name}')
        merged = draft.merge_entries([keyed(), keyed('New')], [old])
        self.assertEqual(merged[0]['german'], old['german'])
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[1]['german'], '')

    def test_translated_entry_stays_needed_when_missing_disappears(self):
        old = keyed(german='Hallo {name}')
        disappeared = draft.merge_entries([], [old])[0]
        self.assertEqual(disappeared, old)
        self.assertEqual(draft.merge_entries([], [disappeared]), [old])

    def test_untranslated_entry_becomes_unneeded(self):
        for german in ('', '  \n '):
            with self.subTest(german=german):
                old = keyed(german=german)
                disappeared = draft.merge_entries([], [old])[0]
                self.assertFalse(disappeared['needed'])
                self.assertEqual(disappeared['german'], german)

    def test_unneeded_entry_stays_unneeded(self):
        for german in ('', 'Hallo {name}'):
            with self.subTest(german=german):
                old = keyed(needed=False, german=german)
                self.assertEqual(draft.merge_entries([], [old]), [old])

    def test_unneeded_entry_reappears(self):
        old = keyed(needed=False, german='Hallo {name}')
        reappeared = draft.merge_entries([keyed()], [old])[0]
        self.assertTrue(reappeared['needed'])
        self.assertEqual(reappeared['german'], old['german'])

    def test_translated_review_or_unresolved_entry_stays_needed(self):
        for old in (keyed(german='Hallo {name}', review=True, previous_english='Old'),
                    definition(def_resolution='missing')):
            with self.subTest(entry=old):
                self.assertEqual(draft.merge_entries([], [old]), [old])

    def test_changed_english_and_previous_survive_repeated_merge(self):
        old = keyed(german='Hallo {name}')
        current = keyed(english='Welcome {name}')
        changed = draft.merge_entries([current], [old])[0]
        self.assertTrue(changed['review'])
        self.assertEqual(changed['previous_english'], old['english'])
        self.assertEqual(changed['german'], old['german'])
        again = draft.merge_entries([current], [changed])[0]
        self.assertEqual(again, changed)
        third = draft.merge_entries([keyed(english='Goodbye {name}')], [again])[0]
        self.assertEqual(third['previous_english'], old['english'])

    def test_namespace_is_not_identity(self):
        old = definition(def_type='UpdateFeatureDef')
        current = definition()
        merged = draft.merge_entries([current], [old])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]['german'], old['german'])
        self.assertEqual(common.entry_identity(old), common.entry_identity(current))

    def test_real_path_collision_and_later_disappearance(self):
        first = definition(identity_scope='ThingDef', def_type='ThingDef')
        second = definition(identity_scope='JobDef', def_type='JobDef')
        entries = draft.merge_entries([first, second], [])
        self.assertEqual(len(common.index_entries(entries)), 2)
        entries[0]['german'] = 'Erste'
        disappeared = draft.merge_entries([definition(def_type=entries[0]['def_type'])], entries)
        self.assertEqual(sum(e['needed'] for e in disappeared), 1)
        self.assertEqual(disappeared[0]['german'], 'Erste')

    def test_duplicate_fails(self):
        with self.assertRaisesRegex(ValueError, 'Doppelter'):
            draft.merge_entries([keyed(), keyed()], [])

    def test_normalizes_preserved_news_type(self):
        old = payload([definition(def_type='UpdateFeatureDef')])
        updated = draft.updated_draft(old, mod(def_types={'News': ['HugsLib.UpdateFeatureDef']}))
        self.assertEqual(updated['entries'][0]['def_type'], 'HugsLib.UpdateFeatureDef')
        self.assertTrue(updated['entries'][0]['needed'])


class WorkTests(unittest.TestCase):
    def test_selection_filters_needed_open_and_review(self):
        entries = [keyed('Open'), keyed('Done', german='Hallo {name}'),
                   keyed('Review', german='Hallo {name}', review=True), keyed('Retired', needed=False)]
        result = work.make_work([pair(entries)])
        self.assertEqual([e['key'] for e in result['entries']], ['Open', 'Review'])
        self.assertEqual(result['open_total'], 2)
        self.assertEqual(result['entries'][1]['original_german'], 'Hallo {name}')

    def test_next_selects_smallest(self):
        result = work.make_work([pair([keyed('a'), keyed('b')], 'large'), pair([keyed()], 'small')])
        self.assertEqual(result['package_id'], 'small')

    def test_limit_offset_and_explicit_package(self):
        items = [pair([keyed(str(i)) for i in range(40)], 'large'), pair([keyed()], 'small')]
        result = work.make_work(items, 'large', 3, 25)
        self.assertEqual([e['key'] for e in result['entries']], ['25', '26', '27'])
        self.assertEqual(len(work.make_work(items, 'large')['entries']), 25)

    def test_invalid_limits(self):
        for limit, offset in ((0, 0), (2, -1), (1, 20)):
            with self.subTest(limit=limit, offset=offset), self.assertRaises(ValueError):
                work.make_work([pair()], limit=limit, offset=offset)

    def test_existing_work_is_replaced(self):
        drafts = [
            [pair([keyed('First')])],
            [pair([keyed('Second')])],
        ]
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(config, 'DATA', Path(directory)), \
                patch.object(work, 'load_drafts', side_effect=drafts), \
                redirect_stdout(StringIO()):
            work.run()
            path = Path(directory) / 'work/test.mod.work.json'
            self.assertEqual(common.load_json(path)['entries'][0]['key'], 'First')

            work.run()

            self.assertEqual(common.load_json(path)['entries'][0]['key'], 'Second')


class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'test.mod.json'
        self.draft = payload([keyed(), keyed('Second', review=True, previous_english='Old')])
        common.write_json(self.path, self.draft)
        self.drafts = [(self.path, self.draft)]
        self.work = work.make_work(self.drafts)
        for e in self.work['entries']:
            e['german'] = 'Hallo {name}'

    def reject(self, changed):
        original = self.path.read_bytes()
        with self.assertRaises(ValueError):
            apply.apply_work(changed, self.drafts)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.draft['entries'][0]['german'], '')

    def test_wrong_package_or_draft(self):
        for field, value in (('package_id', 'wrong'), ('draft_file', '../test.mod.json'), ('draft_file', 'missing.json')):
            with self.subTest(field=field, value=value):
                changed = deepcopy(self.work)
                changed[field] = value
                self.reject(changed)

    def test_removed_or_changed_entry(self):
        for field, value in (('key', 'Removed'), ('english', 'Changed'), ('german', 123), ('german', 'Missing placeholder'), ('original_german', 'New DE')):
            with self.subTest(field=field):
                changed = deepcopy(self.work)
                changed['entries'][1][field] = value
                self.reject(changed)

    def test_no_longer_needed(self):
        self.draft['entries'][1]['needed'] = False
        self.reject(self.work)

    def test_duplicate_work_entry(self):
        self.work['entries'].append(self.work['entries'][0])
        self.reject(self.work)

    def test_success_atomic_apply(self):
        workpath = self.root / 'task.work.json'
        common.write_json(workpath, self.work)
        before = self.path.read_bytes()
        real_replace = os.replace
        def observe(src, dst):
            self.assertEqual(self.path.read_bytes(), before)
            return real_replace(src, dst)
        with patch.object(apply, 'load_drafts', return_value=self.drafts), patch('os.replace', side_effect=observe) as replace, redirect_stdout(StringIO()):
            apply.run(str(workpath))
        self.assertEqual(replace.call_count, 1)
        updated = common.load_json(self.path)
        self.assertEqual(updated['entries'][1]['german'], 'Hallo {name}')
        self.assertFalse(updated['entries'][1]['review'])
        self.assertNotIn('previous_english', updated['entries'][1])
        self.assertNotIn('runtime', updated['entries'][1])

    def test_empty_skipped_and_failed_replace_preserves_original(self):
        self.work['entries'][0]['german'] = ''
        _, changed, count = apply.apply_work(self.work, self.drafts)
        self.assertEqual(count, 1)
        self.assertEqual(changed['entries'][0]['german'], '')
        original = self.path.read_bytes()
        with patch('os.replace', side_effect=OSError('simulated')), self.assertRaises(OSError):
            common.write_json(self.path, changed)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.root.iterdir()), [self.path])


class BuildTests(unittest.TestCase):
    def test_complete_and_incomplete_and_review(self):
        drafts = [pair([keyed(german='Hallo {name}')], 'complete'), pair(package='empty'),
                  pair([keyed(german='Hallo {name}', review=True)], 'review')]
        files, included, excluded = build.collect_expected(drafts)
        self.assertEqual(included, ['complete'])
        self.assertEqual(excluded, ['empty', 'review'])
        self.assertEqual(set(files), {Path('Keyed/complete.xml')})

    def test_full_type_folder(self):
        files, _, _ = build.collect_expected([pair([definition()])])
        self.assertIn(Path('DefInjected/HugsLib.UpdateFeatureDef/test.mod.xml'), files)

    def test_missing_and_ambiguous_types_exclude_draft(self):
        for resolution in ('missing', 'ambiguous'):
            with self.subTest(resolution=resolution):
                files, included, excluded = build.collect_expected([pair([definition(def_resolution=resolution)])])
                self.assertEqual(files, {})
                self.assertEqual(excluded, ['test.mod'])

    def test_only_needed_ready_entries_are_built(self):
        entries = [keyed('Needed', german='Hallo {name}'),
                   keyed('Retired', german='Hallo {name}', needed=False),
                   keyed('RetiredReview', german='Hallo {name}', needed=False, review=True)]
        files, included, excluded = build.collect_expected([pair(entries)])
        self.assertEqual(included, ['test.mod'])
        self.assertFalse(excluded)
        self.assertEqual([n.tag for content in files.values() for n in ET.fromstring(content)], ['Needed'])
        files, _, _ = build.collect_expected([pair(entries[1:])])
        self.assertFalse(files)

    def test_stale_files_removed_and_deterministic(self):
        files, _, _ = build.collect_expected([pair([definition(), keyed(german='Hallo {name}')])])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'German'
            root.mkdir()
            (root / 'stale.xml').write_text('old')
            build.replace_runtime(files, root)
            before = {p.relative_to(root): (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob('*.xml')}
            build.replace_runtime(files, root)
            after = {p.relative_to(root): (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob('*.xml')}
            self.assertEqual(before, after)
            self.assertFalse((root / 'stale.xml').exists())

    def test_swap_failure_rolls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'German'
            root.mkdir()
            old = root / 'original.xml'
            old.write_text('preserve')
            original_rename = Path.rename
            def fail_output(path, target):
                if path.name == 'German' and path.parent.name.startswith('.rwgt-build-'):
                    raise OSError('simulated swap failure')
                return original_rename(path, target)
            with patch.object(Path, 'rename', fail_output), self.assertRaises(OSError):
                build.replace_runtime({}, root)
            self.assertEqual(old.read_text(), 'preserve')

    def test_duplicate_conflicts_and_identical_dedupe(self):
        for factory in (lambda: keyed(german='Hallo {name}'), definition):
            with self.subTest(factory=factory):
                first = pair([factory()], 'first')
                second = pair([factory()], 'second')
                files, _, _ = build.collect_expected([first, second])
                self.assertEqual(sum(len(ET.fromstring(c)) for c in files.values()), 1)
                for field, value in (('german', 'Anders {name}' if factory != definition else 'Anders'), ('english', 'Other {name}' if factory != definition else 'Other')):
                    changed = deepcopy(second)
                    changed[1]['entries'][0][field] = value
                    with self.assertRaisesRegex(ValueError, 'Duplicate-Konflikt'):
                        build.collect_expected([first, changed])

    def test_invalid_xml_does_not_replace_output(self):
        with self.assertRaises(ET.ParseError):
            build.collect_expected([pair([keyed('bad key', german='Hallo {name}')])])


class VerifyTests(unittest.TestCase):
    def test_missing_unexpected_changed_and_wrong_folder(self):
        expected, _, _ = build.collect_expected([pair([definition()])])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertTrue(any('fehlt' in e for e in verify.runtime_errors(expected, root)))
            build.replace_runtime(expected, root)
            extra = root / 'Keyed/stale.xml'
            extra.parent.mkdir()
            extra.write_text('<LanguageData><Extra>Extra</Extra></LanguageData>')
            self.assertTrue(any('Unerwartete' in e for e in verify.runtime_errors(expected, root)))
            extra.unlink()
            target = next(root.rglob('*.xml'))
            target.write_text(target.read_text().replace('Neuigkeiten', 'Anders'))
            self.assertTrue(any('abweichend' in e for e in verify.runtime_errors(expected, root)))
            target.parent.rename(target.parent.with_name('UpdateFeatureDef'))
            errors = verify.runtime_errors(expected, root)
            self.assertTrue(any('fehlt' in e for e in errors))
            self.assertTrue(any('Unerwartete' in e for e in errors))

    def test_source_sync_new_stale_english_and_def_resolution(self):
        self.assertTrue(verify.source_errors([], {'mods': [mod([keyed()])]}))
        self.assertTrue(verify.source_errors([pair()], {'mods': [mod()]}))
        self.assertTrue(verify.source_errors([pair()], {'mods': [mod([keyed(english='New')])]}))
        self.assertTrue(verify.source_errors([pair([definition()])], {'mods': [mod([definition()], def_types={'News': ['Other.Def']})]}))
        self.assertFalse(verify.source_errors([pair()], {'mods': [mod([keyed()])]}))

    def test_structure_and_placeholders(self):
        for change in ({'needed': 1}, {'review': 'false'}, {'german': None}, {'runtime': None}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                common.validate_draft(*pair([keyed(**change)]))
        self.assertTrue(verify.source_errors([pair([keyed(german='wrong')])], {'mods': [mod([keyed()])]}))
        self.assertEqual(common.placeholders('{0} {1} {name} {name}'), {'{0}': 1, '{1}': 1, '{name}': 2})

    def test_duplicate_runtime_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'Keyed').mkdir()
            for name in ('a', 'b'):
                (root / 'Keyed' / (name + '.xml')).write_text('<LanguageData><Key>Text</Key></LanguageData>')
            self.assertTrue(any('Doppelter' in e for e in verify.runtime_errors({}, root)))

    def test_runtime_fingerprint_changes_invalidate_confirmation(self):
        records = {('keyed', '', 'Hello'): {'package_id': 'test.mod', 'german': 'Hallo'}}
        status = {'runtime': {'test.mod': {'confirmed': True, 'sha256': common.semantic_hash(records)}}}
        self.assertTrue(verify.runtime_confirmed('test.mod', records, status))
        records[('keyed', '', 'Hello')]['german'] = 'Anders'
        self.assertFalse(verify.runtime_confirmed('test.mod', records, status))

    def test_runtime_report_freshness_active_order_and_missing(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(config, 'LANG', Path(directory)):
            root = config.LANG / 'Keyed'
            root.mkdir()
            path = root / 'test.mod.xml'
            path.write_text('<LanguageData><Hello>Hallo</Hello></LanguageData>')
            records = common.runtime_records(config.LANG)
            report = {'mtime_ns': path.stat().st_mtime_ns + 10, 'sha256': 'report', 'missing_identities': [], 'missing_def_paths': []}
            active = ['test.mod', common.OWN_PACKAGE]
            result = refresh.runtime_snapshot(records, report, active, 'config', 0, {}, [])
            self.assertTrue(result['test.mod']['confirmed'])
            previous = {'runtime': result, 'report': report.copy(), 'mods_config_sha256': 'config'}
            os.utime(path, ns=(report['mtime_ns'] + 100, report['mtime_ns'] + 100))
            self.assertFalse(refresh.runtime_snapshot(records, report, active, 'config', 0, {}, [])['test.mod']['confirmed'])
            self.assertTrue(refresh.runtime_snapshot(records, report, active, 'config', 0, previous, [])['test.mod']['confirmed'])
            for order in ([], list(reversed(active))):
                self.assertFalse(refresh.runtime_snapshot(records, report, order, 'config', 0, previous, [])['test.mod']['confirmed'])
            report['missing_identities'] = [['keyed', '', 'Hello']]
            self.assertFalse(refresh.runtime_snapshot(records, report, active, 'config', 0, previous, [])['test.mod']['confirmed'])


class ResolverTests(unittest.TestCase):
    def test_defs_news_namespaces_and_old_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative, tag, name in [('Defs/current.xml', 'ThingDef', 'Thing'), ('1.6/News/news.xml', 'HugsLib.UpdateFeatureDef', 'News'),
                                        ('1.5/Defs/old.xml', 'OldDef', 'Old'), ('Patches/patch.xml', 'PatchDef', 'Patch'),
                                        ('Languages/English/Defs/lang.xml', 'LanguageDef', 'Lang')]:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f'<Defs><{tag}><defName>{name}</defName></{tag}></Defs>')
            self.assertEqual(sources.source_def_types(root), {'Thing': {'ThingDef'}, 'News': {'HugsLib.UpdateFeatureDef'}})


class RepositoryDraftTests(unittest.TestCase):
    def test_no_runtime_state_in_durable_drafts(self):
        directory = Path(__file__).resolve().parent.parent / 'translations'
        paths = sorted(directory.glob('*.json'))
        self.assertTrue(paths)
        for path in paths:
            with self.subTest(draft=path.name):
                saved = common.load_json(path)
                for entry in saved['entries']:
                    self.assertNotIn('runtime', entry)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(Path(__file__).parent, self.root / 'scripts', ignore=shutil.ignore_patterns('__pycache__'))
        self.paths = {key: self.root / key for key in ('game', 'workshop', 'rimworld_home', 'report_dir')}
        for p in self.paths.values():
            p.mkdir()
        self.config_path = self.root / 'rwgt.local.json'
        common.write_json(self.config_path, {k: str(v) for k, v in self.paths.items()})
        source = self.paths['workshop'] / '123'
        for directory in ('About', 'Languages/English/Keyed', 'News'):
            (source / directory).mkdir(parents=True)
        (source / 'About/About.xml').write_text('<ModMetaData><packageId>test.mod</packageId><name>Test</name></ModMetaData>')
        (source / 'Languages/English/Keyed/Test.xml').write_text('<LanguageData><Hello>Hello {name}</Hello></LanguageData>')
        (source / 'News/News.xml').write_text('<Defs><HugsLib.UpdateFeatureDef><defName>News</defName><label>News</label></HugsLib.UpdateFeatureDef></Defs>')
        conf = self.paths['rimworld_home'] / 'Config/ModsConfig.xml'
        conf.parent.mkdir()
        conf.write_text('<ModsConfigData><activeMods><li>test.mod</li><li>elhanko.rimworld.germantranslations</li></activeMods></ModsConfigData>')
        self.report = self.paths['report_dir'] / 'TranslationReport.txt'
        self.write_report(True)
        (self.root / 'data').mkdir()
        (self.root / 'data/TranslationReport.txt').symlink_to(self.report)

    def write_report(self, missing):
        text = "Translation report for German\n\n========== Missing keyed translations (COUNT) ==========\nKEYED\n========== Def-injected translations missing (COUNT) ==========\nDEFS\n"
        text = text.replace('COUNT', '1' if missing else '0')
        text = text.replace('KEYED', "Hello 'Hello {name}' (English file: Test.xml:1)" if missing else '')
        text = text.replace('DEFS', "UpdateFeatureDef: News.label 'News'" if missing else '')
        self.report.write_text(text)

    def cli(self, *args, success=True):
        result = subprocess.run([sys.executable, str(self.root / 'scripts/rwgt.py'), *args], cwd=self.root, text=True, capture_output=True)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn('Traceback', result.stderr)
        return result.stdout + result.stderr

    def test_full_workflow_and_runtime_transition(self):
        source_before = {p: p.read_bytes() for base in self.paths.values() for p in base.rglob('*') if p.is_file()}
        self.cli('refresh')
        self.assertFalse((self.root / 'data/TranslationReport.txt').is_symlink())
        self.cli('status')
        self.cli('draft', '--all')
        self.cli('progress')
        self.cli('work', '--next', '--limit', '25')
        task = self.root / 'data/work/test.mod.work.json'
        data = common.load_json(task)
        for e in data['entries']:
            e['german'] = 'Hallo {name}' if e['type'] == 'keyed' else 'Neuigkeiten'
        common.write_json(task, data)
        self.cli('apply', str(task))
        self.cli('build')
        self.assertIn('Runtime: ausstehend', self.cli('verify'))
        for p, before in source_before.items():
            self.assertEqual(p.read_bytes(), before)
        self.write_report(False)
        self.cli('refresh')
        self.assertIn('Runtime: ✓', self.cli('verify'))
        self.cli('draft', '--all')
        saved = common.load_json(self.root / 'translations/test.mod.json')
        self.assertTrue(all(e['needed'] and 'runtime' not in e for e in saved['entries']))
        self.assertEqual(progress.state(saved), {'needed': 2, 'translated': 2, 'open': 0, 'review': 0, 'retired': 0})
        self.cli('build')
        self.assertIn('lokal konsistent', self.cli('verify'))
        self.assertEqual(len(common.runtime_records(self.root / 'Languages/German')), 2)
        self.cli('draft', 'test.mod')
        self.cli('progress', 'test.mod')
        self.cli('work', 'test.mod', '--offset', '-1', success=False)
        self.cli('work', '--next', 'test.mod', success=False)

    def test_cli_config_errors_and_missing_status(self):
        self.assertIn('refresh', self.cli('status', success=False))
        for content in (None, '{', '{}', '[]'):
            if content is None:
                self.config_path.unlink()
            else:
                self.config_path.write_text(content)
            self.assertIn('rwgt.example.json', self.cli('build', success=False))


if __name__ == '__main__':
    unittest.main()
