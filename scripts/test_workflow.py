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


def target(text='', review=False, needed=True, **changes):
    return dict(text=text, review=review, needed=needed, **changes)


def keyed(key='Hello', **changes):
    e = {'type': 'keyed', 'key': key, 'english': 'Hello {name}',
         'translations': {'German': target()}}
    for field in ('text', 'review', 'previous_english', 'needed'):
        if field in changes:
            e['translations']['German'][field] = changes.pop(field)
    e.update(changes)
    return e


def definition(**changes):
    e = {'type': 'def', 'path': 'News.label', 'def_name': 'News',
         'def_type': 'HugsLib.UpdateFeatureDef', 'def_resolution': 'resolved',
         'english': 'News',
         'translations': {'German': target('Neuigkeiten')}}
    for field in ('text', 'review', 'previous_english', 'needed'):
        if field in changes:
            e['translations']['German'][field] = changes.pop(field)
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


class LanguageConfigTests(unittest.TestCase):
    def test_compatibility_default_and_explicit_languages(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rwgt.local.json'
            values = {k: directory for k in ('game', 'workshop', 'rimworld_home', 'report_dir')}
            common.write_json(path, values)
            self.assertEqual(config.load_config(path)['languages'], ['German'])
            values['languages'] = ['German', 'French', 'Italian']
            common.write_json(path, values)
            self.assertEqual(config.load_config(path)['languages'], values['languages'])

    def test_invalid_language_lists(self):
        for languages in (None, 'German', [], [''], [' '], ['German', 'German'],
                          ['German', 'german'], ['../French'], ['/French'], ['French/Keyed'],
                          ['French\\Keyed'], ['..'], [1]):
            with self.subTest(languages=languages), self.assertRaises(ValueError):
                config.validate_languages(languages)

    def test_explicit_selection_required_for_multiple_languages(self):
        with patch.object(config, 'LANGUAGES', ['German', 'French']):
            self.assertEqual(config.select_language('French'), 'French')
            with self.assertRaisesRegex(ValueError, '--language'):
                work.make_work([pair()])
            with self.assertRaisesRegex(ValueError, 'nicht konfiguriert'):
                config.select_language('Spanish')


class MigrationTests(unittest.TestCase):
    def old_draft(self):
        return payload([{'type': 'keyed', 'key': 'Hello', 'english': 'Hello {name}',
                         'needed': True, 'german': 'Hallo {name}', 'review': True,
                         'previous_english': 'Previous {name}'}])

    def test_legacy_migration_is_lossless_and_idempotent(self):
        old = self.old_draft()
        saved = deepcopy(old)
        migrated = common.migrate_draft(old)
        self.assertEqual(old, saved)
        entry = migrated['entries'][0]
        self.assertEqual(entry['translations'], {'German': target('Hallo {name}', True, previous_english='Previous {name}')})
        self.assertEqual(common.entry_identity(entry), common.entry_identity(old['entries'][0]))
        self.assertFalse({'german', 'review', 'previous_english'} & entry.keys())
        common.validate_draft(Path('test.mod.json'), migrated)
        self.assertEqual(common.migrate_draft(migrated), migrated)

    def test_mixed_or_invalid_migration_aborts_before_writes(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(config, 'TRANSLATIONS', Path(directory)):
            first = Path(directory) / 'first.json'
            second = Path(directory) / 'second.json'
            good = self.old_draft()
            good['package_id'] = 'first'
            common.write_json(first, good)
            for change in ({'translations': {'German': target('Other')}}, {'german': None}, {'review': None}):
                bad = self.old_draft()
                bad['package_id'] = 'second'
                bad['entries'][0].update(change)
                common.write_json(second, bad)
                before = {p: p.read_bytes() for p in (first, second)}
                with self.subTest(change=change), patch.object(
                    draft,
                    'load_status',
                    return_value={
                        'report': {'language': 'German'},
                        'mods': [],
                    },
                ), self.assertRaises(ValueError):
                    draft.run('--all')
                self.assertEqual({p: p.read_bytes() for p in (first, second)}, before)


class MultipleLanguageTests(unittest.TestCase):
    def setUp(self):
        languages = patch.object(config, 'LANGUAGES', ['German', 'French'])
        languages.start()
        self.addCleanup(languages.stop)

    def bilingual(
        self,
        german='',
        french='',
        german_needed=True,
        french_needed=True,
        **changes,
    ):
        return keyed(
            translations={
                'German': target(german, needed=german_needed),
                'French': target(french, needed=french_needed),
            },
            **changes,
        )

    def test_new_language_and_removed_language_preserve_states(self):
        original = keyed(
            text='Hallo {name}',
            review=True,
            previous_english='Old',
        )

        merged = draft.merge_entries(
            [keyed()],
            [original],
            'German',
        )[0]

        self.assertEqual(
            merged['translations']['German'],
            original['translations']['German'],
        )
        self.assertEqual(
            merged['translations']['French'],
            target(needed=None),
        )

        merged['translations']['French'] = target(
            'Bonjour {name}',
            needed=None,
        )

        with patch.object(config, 'LANGUAGES', ['French', 'Italian']):
            updated = draft.merge_entries(
                [keyed()],
                [merged],
                'French',
            )[0]

        self.assertEqual(
            updated['translations']['German'],
            original['translations']['German'],
        )
        self.assertEqual(
            updated['translations']['French'],
            target('Bonjour {name}', needed=True),
        )
        self.assertEqual(
            updated['translations']['Italian'],
            target(needed=None),
        )

    def test_source_change_marks_each_stored_language_for_review(self):
        original = self.bilingual('Hallo {name}', 'Bonjour {name}')
        original['translations']['Spanish'] = target('Hola {name}')
        changed = draft.merge_entries(
            [keyed(english='Welcome {name}')],
            [original],
            'German',
        )[0]
        for language, state in changed['translations'].items():
            self.assertTrue(state['review'])
            self.assertEqual(state['previous_english'], original['english'])
            self.assertEqual(state['text'], original['translations'][language]['text'])
        again = draft.merge_entries(
            [keyed(english='Bye {name}')],
            [changed],
            'German',
        )[0]
        self.assertEqual([s['previous_english'] for s in again['translations'].values()], [original['english']] * 3)

    def test_one_report_changes_only_its_language_needed_state(self):
        original = self.bilingual()

        changed = draft.merge_entries(
            [],
            [original],
            'German',
        )[0]

        self.assertFalse(
            changed['translations']['German']['needed']
        )
        self.assertTrue(
            changed['translations']['French']['needed']
        )

    def test_needed_sets_are_independent_per_language(self):
        # Erster Report: German benötigt nur OnlyGerman.
        entries = draft.merge_entries(
            [keyed('OnlyGerman')],
            [],
            'German',
        )

        by_key = {entry['key']: entry for entry in entries}

        self.assertTrue(
            by_key['OnlyGerman']['translations']['German']['needed']
        )
        self.assertIsNone(
            by_key['OnlyGerman']['translations']['French']['needed']
        )

        # Zweiter Report: French benötigt nur OnlyFrench.
        entries = draft.merge_entries(
            [keyed('OnlyFrench')],
            entries,
            'French',
        )

        by_key = {entry['key']: entry for entry in entries}

        self.assertTrue(
            by_key['OnlyGerman']['translations']['German']['needed']
        )
        self.assertFalse(
            by_key['OnlyGerman']['translations']['French']['needed']
        )
        self.assertIsNone(
            by_key['OnlyFrench']['translations']['German']['needed']
        )
        self.assertTrue(
            by_key['OnlyFrench']['translations']['French']['needed']
        )

        # German darf noch nicht bauen, solange OnlyFrench für German
        # noch nie durch einen German-Report klassifiziert wurde.
        with self.assertRaisesRegex(ValueError, 'unbekannt'):
            build.collect_expected(
                [pair(entries)],
                'German',
            )

        # Neuer German-Report bestätigt: OnlyFrench wird für German
        # nicht benötigt.
        entries = draft.merge_entries(
            [keyed('OnlyGerman')],
            entries,
            'German',
        )

        by_key = {entry['key']: entry for entry in entries}

        self.assertTrue(
            by_key['OnlyGerman']['translations']['German']['needed']
        )
        self.assertFalse(
            by_key['OnlyGerman']['translations']['French']['needed']
        )
        self.assertFalse(
            by_key['OnlyFrench']['translations']['German']['needed']
        )
        self.assertTrue(
            by_key['OnlyFrench']['translations']['French']['needed']
        )

        german_work = work.make_work(
            [pair(entries)],
            language='German',
        )
        french_work = work.make_work(
            [pair(entries)],
            language='French',
        )

        self.assertEqual(
            [entry['key'] for entry in german_work['entries']],
            ['OnlyGerman'],
        )
        self.assertEqual(
            [entry['key'] for entry in french_work['entries']],
            ['OnlyFrench'],
        )

        by_key['OnlyGerman']['translations']['German']['text'] = (
            'Hallo {name}'
        )
        by_key['OnlyFrench']['translations']['French']['text'] = (
            'Bonjour {name}'
        )

        german_files, included, excluded = build.collect_expected(
            [pair(entries)],
            'German',
        )
        self.assertEqual(included, ['test.mod'])
        self.assertFalse(excluded)

        french_files, included, excluded = build.collect_expected(
            [pair(entries)],
            'French',
        )
        self.assertEqual(included, ['test.mod'])
        self.assertFalse(excluded)

        german_xml = b''.join(german_files.values())
        french_xml = b''.join(french_files.values())

        self.assertIn(b'OnlyGerman', german_xml)
        self.assertNotIn(b'OnlyFrench', german_xml)
        self.assertIn(b'OnlyFrench', french_xml)
        self.assertNotIn(b'OnlyGerman', french_xml)


    def test_progress_and_next_are_language_specific(self):
        drafts = [pair([self.bilingual('Hallo {name}', '')], 'first'),
                  pair([self.bilingual('', 'Bonjour {name}')], 'second')]
        self.assertEqual(work.make_work(drafts, language='French')['package_id'], 'first')
        self.assertEqual(work.make_work(drafts, language='German')['package_id'], 'second')
        self.assertEqual(progress.state(drafts[0][1], 'German')['translated'], 1)
        self.assertEqual(progress.state(drafts[0][1], 'French')['open'], 1)
        with patch.object(progress, 'load_drafts', return_value=drafts), redirect_stdout(StringIO()) as output:
            progress.run()
        self.assertIn('Sprache: German', output.getvalue())
        self.assertIn('Sprache: French', output.getvalue())

    def test_work_files_coexist_and_replacement_is_language_local(self):
        drafts = [pair([self.bilingual()])]
        with tempfile.TemporaryDirectory() as directory, patch.object(config, 'DATA', Path(directory)), patch.object(work, 'load_drafts', return_value=drafts), redirect_stdout(StringIO()):
            work.run(language='German')
            work.run(language='French')
            german = Path(directory) / 'work/test.mod.German.work.json'
            french = Path(directory) / 'work/test.mod.French.work.json'
            before = german.read_bytes()
            work.run(language='French')
            self.assertEqual(german.read_bytes(), before)
            task = common.load_json(french)
            self.assertEqual(task['language'], 'French')
            self.assertFalse({'german', 'original_german', 'translations'} & task['entries'][0].keys())

    def test_apply_changes_only_requested_language_and_preserves_other_review(self):
        entry = self.bilingual('Hallo {name}', 'Bonjour {name}')
        for state in entry['translations'].values():
            state.update(review=True, previous_english='Old')
        for language in ('German', 'French'):
            with self.subTest(language=language):
                drafts = [pair([entry])]
                before = deepcopy(drafts)
                task = work.make_work(drafts, language=language)
                task['entries'][0]['translation'] = 'Edited {name}'
                _, updated, count = apply.apply_work(task, drafts)
                self.assertEqual(count, 1)
                self.assertEqual(drafts, before)
                other = 'French' if language == 'German' else 'German'
                self.assertEqual(updated['entries'][0]['translations'][other], entry['translations'][other])
                self.assertEqual(updated['entries'][0]['translations'][language], target('Edited {name}'))

    def test_concurrent_target_change_rejected_other_language_change_allowed(self):
        drafts = [pair([self.bilingual()])]
        task = work.make_work(drafts, language='French')
        task['entries'][0]['translation'] = 'Bonjour {name}'
        drafts[0][1]['entries'][0]['translations']['German']['text'] = 'Hallo {name}'
        _, updated, _ = apply.apply_work(task, drafts)
        self.assertEqual(updated['entries'][0]['translations']['German']['text'], 'Hallo {name}')
        drafts[0][1]['entries'][0]['translations']['French']['text'] = 'Concurrent {name}'
        with self.assertRaisesRegex(ValueError, 'inzwischen geändert'):
            apply.apply_work(task, drafts)
        task['language'] = 'Spanish'
        with self.assertRaisesRegex(ValueError, 'nicht konfiguriert'):
            apply.apply_work(task, drafts)

    def test_build_and_verify_language_package_isolation(self):
        drafts = [pair([self.bilingual('Hallo {name}', '')], 'first'),
                  pair([self.bilingual('Hallo {name}', 'Bonjour {name}')], 'second')]
        with tempfile.TemporaryDirectory() as directory, patch.object(config, 'LANG_ROOT', Path(directory)), patch.object(build, 'load_drafts', return_value=drafts), redirect_stdout(StringIO()):
            build.run()
            german, included, excluded = build.collect_expected(drafts, 'German')
            french, fi, fe = build.collect_expected(drafts, 'French')
            self.assertEqual(included, ['first', 'second'])
            self.assertEqual(excluded, [])
            self.assertEqual(fi, ['second'])
            self.assertEqual(fe, ['first'])
            self.assertFalse(verify.runtime_errors(german, config.language_dir('German')))
            self.assertFalse(verify.runtime_errors(french, config.language_dir('French')))
            gpath = config.language_dir('German') / 'Keyed/first.xml'
            fpath = config.language_dir('French') / 'Keyed/second.xml'
            fpath.write_bytes(gpath.read_bytes())
            self.assertTrue(verify.runtime_errors(french, config.language_dir('French')))
            self.assertFalse(verify.runtime_errors(german, config.language_dir('German')))

    def test_disabled_language_output_and_data_are_not_touched(self):
        drafts = [pair([self.bilingual('Hallo {name}', 'Bonjour {name}')])]
        with tempfile.TemporaryDirectory() as directory, patch.object(config, 'LANG_ROOT', Path(directory)), patch.object(build, 'load_drafts', return_value=drafts), redirect_stdout(StringIO()):
            build.run()
            before = (config.language_dir('German') / 'Keyed/test.mod.xml').read_bytes()
            with patch.object(config, 'LANGUAGES', ['French']):
                build.run()
            self.assertEqual((config.language_dir('German') / 'Keyed/test.mod.xml').read_bytes(), before)

    def test_runtime_evidence_never_crosses_language_boundary(self):
        records = {('keyed', '', 'Hello'): {'package_id': 'test.mod', 'text': 'Same text'}}
        status = {'report': {'language': 'German'}, 'runtime': {'test.mod': {'confirmed': True, 'sha256': common.semantic_hash(records)}}}
        self.assertTrue(verify.runtime_confirmed('test.mod', records, status, 'German'))
        self.assertFalse(verify.runtime_confirmed('test.mod', records, status, 'French'))
        status['report'].clear()
        self.assertFalse(verify.runtime_confirmed('test.mod', records, status, 'German'))

    def test_report_requires_exact_explicit_language_header(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'TranslationReport.txt'
            tail = '\n========== Missing keyed translations (0) ==========\n========== Def-injected translations missing (0) ==========\n'
            path.write_text('Translation report for French' + tail)
            self.assertEqual(refresh.report_metadata(path)[1]['language'], 'French')
            path.write_text('Translation report' + tail)
            with self.assertRaisesRegex(ValueError, 'Sprache'):
                refresh.report_metadata(path)


class RefreshDedupTests(unittest.TestCase):
    def test_identical_resolved_def_duplicates_are_deduplicated(self):
        entry = {
            'type': 'def',
            'package_id': 'test.mod',
            'def_type': 'VEF.Weapons.ExpandableProjectileDef',
            'def_name': 'TestProjectile',
            'path': 'TestProjectile.label',
            'english': 'projectile',
            'hint': None,
            'def_resolution': 'resolved',
        }

        result = refresh.dedupe_resolved_def_entries(
            [entry, dict(entry)]
        )

        self.assertEqual(result, [entry])

    def test_conflicting_resolved_def_duplicates_fail(self):
        entry = {
            'type': 'def',
            'package_id': 'test.mod',
            'def_type': 'VEF.Weapons.ExpandableProjectileDef',
            'def_name': 'TestProjectile',
            'path': 'TestProjectile.label',
            'english': 'projectile',
            'hint': None,
            'def_resolution': 'resolved',
        }
        conflict = dict(entry)
        conflict['english'] = 'different projectile'

        with self.assertRaisesRegex(
            ValueError,
            'Widersprüchliche aufgelöste Def-Einträge',
        ):
            refresh.dedupe_resolved_def_entries(
                [entry, conflict]
            )


class RuntimeEchoTests(unittest.TestCase):
    def test_refresh_marks_matching_generated_runtime_text_as_echo(self):
        entry = {
            'type': 'def',
            'package_id': 'test.mod',
            'def_type': 'VEF.Weapons.ExpandableProjectileDef',
            'def_name': 'TestProjectile',
            'path': 'TestProjectile.label',
            'english': 'Deutsche Runtime-Fassung',
            'hint': None,
            'def_resolution': 'resolved',
        }
        records = {
            (
                'def',
                'VEF.Weapons.ExpandableProjectileDef',
                'TestProjectile.label',
            ): {
                'text': 'Deutsche Runtime-Fassung',
                'package_id': 'test.mod',
            }
        }

        refresh.mark_runtime_echoes(
            [entry],
            'test.mod',
            records,
        )

        self.assertTrue(entry['runtime_echo'])

    def test_runtime_echo_preserves_source_english_without_review(self):
        previous = [{
            'type': 'def',
            'package_id': 'test.mod',
            'def_type': 'VEF.Weapons.ExpandableProjectileDef',
            'def_name': 'TestProjectile',
            'path': 'TestProjectile.label',
            'english': 'original english',
            'hint': None,
            'def_resolution': 'resolved',
            'translations': {
                'German': {
                    'text': 'Deutsche Runtime-Fassung',
                    'review': False,
                    'needed': True,
                }
            },
        }]

        current = [{
            'type': 'def',
            'package_id': 'test.mod',
            'def_type': 'VEF.Weapons.ExpandableProjectileDef',
            'def_name': 'TestProjectile',
            'path': 'TestProjectile.label',
            'english': 'Deutsche Runtime-Fassung',
            'hint': None,
            'def_resolution': 'resolved',
            'runtime_echo': True,
        }]

        result = draft.merge_entries(
            current,
            previous,
            language='German',
        )

        self.assertEqual(len(result), 1)

        entry = result[0]
        state = entry['translations']['German']

        self.assertEqual(entry['english'], 'original english')
        self.assertEqual(state['text'], 'Deutsche Runtime-Fassung')
        self.assertFalse(state['review'])
        self.assertNotIn('previous_english', state)
        self.assertNotIn('runtime_echo', entry)


class CanonicalMissingTests(unittest.TestCase):
    def test_runtime_echo_is_excluded_and_missing_is_package_scoped(self):
        rows = [
            {
                'package_id': 'test.mod',
                'entries': [
                    {
                        'type': 'keyed',
                        'key': 'Echo',
                        'english': 'Hallo',
                        'runtime_echo': True,
                    },
                    {
                        'type': 'keyed',
                        'key': 'ActuallyMissing',
                        'english': 'Missing',
                    },
                    {
                        'type': 'def',
                        'def_type': 'Namespace.TestDef',
                        'path': 'TestDef.label',
                        'english': 'Missing Def',
                    },
                ],
            },
            {
                'package_id': 'other.mod',
                'entries': [
                    {
                        'type': 'keyed',
                        'key': 'Echo',
                        'english': 'Other',
                    },
                ],
            },
        ]

        result = refresh.canonical_missing(rows)

        self.assertEqual(
            result['test.mod'],
            {
                'identities': [
                    ['keyed', '', 'ActuallyMissing'],
                    ['def', 'Namespace.TestDef', 'TestDef.label'],
                ],
                'def_paths': ['TestDef.label'],
            },
        )

        self.assertEqual(
            result['other.mod'],
            {
                'identities': [
                    ['keyed', '', 'Echo'],
                ],
                'def_paths': [],
            },
        )

    def test_runtime_echo_does_not_block_confirmation(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            config,
            'LANG_ROOT',
            Path(directory),
        ):
            root = config.language_dir('German') / 'Keyed'
            root.mkdir(parents=True)

            path = root / 'test.mod.xml'
            path.write_text(
                '<LanguageData><Echo>Hallo</Echo></LanguageData>'
            )

            records = common.runtime_records(
                config.language_dir('German')
            )

            report = {
                'language': 'German',
                'mtime_ns': path.stat().st_mtime_ns + 10,
                'sha256': 'report',
                'missing_identities': [
                    ['keyed', '', 'Echo'],
                ],
                'missing_def_paths': [],
                'canonical_missing': {
                    'test.mod': {
                        'identities': [],
                        'def_paths': [],
                    }
                },
            }

            active = [
                'test.mod',
                common.OWN_PACKAGE,
            ]

            result = refresh.runtime_snapshot(
                records,
                report,
                active,
                'config',
                0,
                {},
                [],
            )

            self.assertTrue(result['test.mod']['confirmed'])
            self.assertFalse(result['test.mod']['missing'])


class DraftTests(unittest.TestCase):
    def test_preserves_german_and_adds_new(self):
        old = keyed(text='Hallo {name}')
        merged = draft.merge_entries([keyed(), keyed('New')], [old])
        self.assertEqual(merged[0]['translations']['German']['text'], old['translations']['German']['text'])
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[1]['translations']['German']['text'], '')

    def test_translated_entry_stays_needed_when_missing_disappears(self):
        old = keyed(text='Hallo {name}')
        disappeared = draft.merge_entries([], [old])[0]
        self.assertEqual(disappeared, old)
        self.assertEqual(draft.merge_entries([], [disappeared]), [old])

    def test_untranslated_entry_becomes_unneeded(self):
        for german in ('', '  \n '):
            with self.subTest(text=german):
                old = keyed(text=german)
                disappeared = draft.merge_entries([], [old])[0]
                self.assertFalse(disappeared['translations']['German']['needed'])
                self.assertEqual(disappeared['translations']['German']['text'], german)

    def test_unneeded_entry_stays_unneeded(self):
        for german in ('', 'Hallo {name}'):
            with self.subTest(text=german):
                old = keyed(needed=False, text=german)
                self.assertEqual(draft.merge_entries([], [old]), [old])

    def test_unneeded_entry_reappears(self):
        old = keyed(needed=False, text='Hallo {name}')
        reappeared = draft.merge_entries([keyed()], [old])[0]
        self.assertTrue(reappeared['translations']['German']['needed'])
        self.assertEqual(reappeared['translations']['German']['text'], old['translations']['German']['text'])

    def test_translated_review_or_unresolved_entry_stays_needed(self):
        for old in (keyed(text='Hallo {name}', review=True, previous_english='Old'),
                    definition(def_resolution='missing')):
            with self.subTest(entry=old):
                self.assertEqual(draft.merge_entries([], [old]), [old])

    def test_changed_english_and_previous_survive_repeated_merge(self):
        old = keyed(text='Hallo {name}')
        current = keyed(english='Welcome {name}')
        changed = draft.merge_entries([current], [old])[0]
        self.assertTrue(changed['translations']['German']['review'])
        self.assertEqual(changed['translations']['German']['previous_english'], old['english'])
        self.assertEqual(changed['translations']['German']['text'], old['translations']['German']['text'])
        again = draft.merge_entries([current], [changed])[0]
        self.assertEqual(again, changed)
        third = draft.merge_entries([keyed(english='Goodbye {name}')], [again])[0]
        self.assertEqual(third['translations']['German']['previous_english'], old['english'])

    def test_namespace_is_not_identity(self):
        old = definition(def_type='UpdateFeatureDef')
        current = definition()
        merged = draft.merge_entries([current], [old])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]['translations']['German']['text'], old['translations']['German']['text'])
        self.assertEqual(common.entry_identity(old), common.entry_identity(current))

    def test_real_path_collision_and_later_disappearance(self):
        first = definition(identity_scope='ThingDef', def_type='ThingDef')
        second = definition(identity_scope='JobDef', def_type='JobDef')
        entries = draft.merge_entries([first, second], [])
        self.assertEqual(len(common.index_entries(entries)), 2)
        entries[0]['translations']['German']['text'] = 'Erste'
        disappeared = draft.merge_entries([definition(def_type=entries[0]['def_type'])], entries)
        self.assertEqual(sum(e['translations']['German']['needed'] is True for e in disappeared), 1)
        self.assertEqual(disappeared[0]['translations']['German']['text'], 'Erste')

    def test_duplicate_fails(self):
        with self.assertRaisesRegex(ValueError, 'Doppelter'):
            draft.merge_entries([keyed(), keyed()], [])

    def test_normalizes_preserved_news_type(self):
        old = payload([definition(def_type='UpdateFeatureDef')])
        updated = draft.updated_draft(old, mod(def_types={'News': ['HugsLib.UpdateFeatureDef']}))
        self.assertEqual(updated['entries'][0]['def_type'], 'HugsLib.UpdateFeatureDef')
        self.assertTrue(updated['entries'][0]['translations']['German']['needed'])


class WorkTests(unittest.TestCase):
    def test_selection_filters_needed_open_and_review(self):
        entries = [keyed('Open'), keyed('Done', text='Hallo {name}'),
                   keyed('Review', text='Hallo {name}', review=True), keyed('Retired', needed=False)]
        result = work.make_work([pair(entries)])
        self.assertEqual([e['key'] for e in result['entries']], ['Open', 'Review'])
        self.assertEqual(result['open_total'], 2)
        self.assertEqual(result['entries'][1]['original_translation'], 'Hallo {name}')

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
            path = Path(directory) / 'work/test.mod.German.work.json'
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
            e['translation'] = 'Hallo {name}'

    def reject(self, changed):
        original = self.path.read_bytes()
        with self.assertRaises(ValueError):
            apply.apply_work(changed, self.drafts)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.draft['entries'][0]['translations']['German']['text'], '')

    def test_wrong_package_or_draft(self):
        for field, value in (('package_id', 'wrong'), ('draft_file', '../test.mod.json'), ('draft_file', 'missing.json')):
            with self.subTest(field=field, value=value):
                changed = deepcopy(self.work)
                changed[field] = value
                self.reject(changed)

    def test_removed_or_changed_entry(self):
        for field, value in (('key', 'Removed'), ('english', 'Changed'), ('translation', 123), ('translation', 'Missing placeholder'), ('original_translation', 'New DE')):
            with self.subTest(field=field):
                changed = deepcopy(self.work)
                changed['entries'][1][field] = value
                self.reject(changed)

    def test_no_longer_needed(self):
        self.draft['entries'][1]['translations']['German']['needed'] = False
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
        self.assertEqual(updated['entries'][1]['translations']['German']['text'], 'Hallo {name}')
        self.assertFalse(updated['entries'][1]['translations']['German']['review'])
        self.assertNotIn('previous_english', updated['entries'][1]['translations']['German'])
        self.assertNotIn('runtime', updated['entries'][1])

    def test_empty_skipped_and_failed_replace_preserves_original(self):
        self.work['entries'][0]['translation'] = ''
        _, changed, count = apply.apply_work(self.work, self.drafts)
        self.assertEqual(count, 1)
        self.assertEqual(changed['entries'][0]['translations']['German']['text'], '')
        original = self.path.read_bytes()
        with patch('os.replace', side_effect=OSError('simulated')), self.assertRaises(OSError):
            common.write_json(self.path, changed)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.root.iterdir()), [self.path])


class BuildTests(unittest.TestCase):
    def test_complete_and_incomplete_and_review(self):
        drafts = [pair([keyed(text='Hallo {name}')], 'complete'), pair(package='empty'),
                  pair([keyed(text='Hallo {name}', review=True)], 'review')]
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
        entries = [keyed('Needed', text='Hallo {name}'),
                   keyed('Retired', text='Hallo {name}', needed=False),
                   keyed('RetiredReview', text='Hallo {name}', needed=False, review=True)]
        files, included, excluded = build.collect_expected([pair(entries)])
        self.assertEqual(included, ['test.mod'])
        self.assertFalse(excluded)
        self.assertEqual([n.tag for content in files.values() for n in ET.fromstring(content)], ['Needed'])
        files, _, _ = build.collect_expected([pair(entries[1:])])
        self.assertFalse(files)

    def test_stale_files_removed_and_deterministic(self):
        files, _, _ = build.collect_expected([pair([definition(), keyed(text='Hallo {name}')])])
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
        for factory in (lambda: keyed(text='Hallo {name}'), definition):
            with self.subTest(factory=factory):
                first = pair([factory()], 'first')
                second = pair([factory()], 'second')
                files, _, _ = build.collect_expected([first, second])
                self.assertEqual(sum(len(ET.fromstring(c)) for c in files.values()), 1)
                for field, value in (('text', 'Anders {name}' if factory != definition else 'Anders'), ('english', 'Other {name}' if factory != definition else 'Other')):
                    changed = deepcopy(second)
                    entry = changed[1]['entries'][0]
                    if field == 'text':
                        entry['translations']['German']['text'] = value
                    else:
                        entry[field] = value
                    with self.assertRaisesRegex(ValueError, 'Duplicate-Konflikt'):
                        build.collect_expected([first, changed])

    def test_invalid_xml_does_not_replace_output(self):
        with self.assertRaises(ET.ParseError):
            build.collect_expected([pair([keyed('bad key', text='Hallo {name}')])])


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
        self.assertTrue(verify.source_errors(
            [pair()],
            {
                'report': {'language': 'German'},
                'mods': [mod()],
            },
        ))
        self.assertTrue(verify.source_errors(
            [pair()],
            {
                'report': {'language': 'German'},
                'mods': [mod([keyed(english='New')])],
            },
        ))
        self.assertTrue(verify.source_errors(
            [pair([definition()])],
            {
                'report': {'language': 'German'},
                'mods': [
                    mod(
                        [definition()],
                        def_types={'News': ['Other.Def']},
                    )
                ],
            },
        ))
        self.assertFalse(verify.source_errors(
            [pair()],
            {
                'report': {'language': 'German'},
                'mods': [mod([keyed()])],
            },
        ))

    def test_structure_and_placeholders(self):
        for change in ({'needed': 1}, {'review': 'false'}, {'text': None}, {'runtime': None}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                common.validate_draft(*pair([keyed(**change)]))
        self.assertTrue(verify.source_errors(
            [pair([keyed(text='wrong')])],
            {
                'report': {'language': 'German'},
                'mods': [mod([keyed()])],
            },
        ))
        self.assertEqual(common.placeholders('{0} {1} {name} {name}'), {'{0}': 1, '{1}': 1, '{name}': 2})

    def test_duplicate_runtime_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'Keyed').mkdir()
            for name in ('a', 'b'):
                (root / 'Keyed' / (name + '.xml')).write_text('<LanguageData><Key>Text</Key></LanguageData>')
            self.assertTrue(any('Doppelter' in e for e in verify.runtime_errors({}, root)))

    def test_runtime_fingerprint_changes_invalidate_confirmation(self):
        records = {('keyed', '', 'Hello'): {'package_id': 'test.mod', 'text': 'Hallo'}}
        status = {'report': {'language': 'German'}, 'runtime': {'test.mod': {'confirmed': True, 'sha256': common.semantic_hash(records)}}}
        self.assertTrue(verify.runtime_confirmed('test.mod', records, status))
        records[('keyed', '', 'Hello')]['text'] = 'Anders'
        self.assertFalse(verify.runtime_confirmed('test.mod', records, status))

    def test_runtime_report_freshness_active_order_and_missing(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(config, 'LANG_ROOT', Path(directory)):
            root = config.language_dir('German') / 'Keyed'
            root.mkdir(parents=True)
            path = root / 'test.mod.xml'
            path.write_text('<LanguageData><Hello>Hallo</Hello></LanguageData>')
            records = common.runtime_records(config.language_dir('German'))
            report = {'language': 'German', 'mtime_ns': path.stat().st_mtime_ns + 10, 'sha256': 'report', 'missing_identities': [], 'missing_def_paths': []}
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
            patch = root / '1.6/Patches/add-def.xml'
            patch.parent.mkdir(parents=True, exist_ok=True)
            patch.write_text(
                '<Patch>'
                '<Operation Class="PatchOperationAdd">'
                '<xpath>Defs</xpath>'
                '<value>'
                '<ThingDef>'
                '<defName>PatchedThing</defName>'
                '</ThingDef>'
                '</value>'
                '</Operation>'
                '</Patch>'
            )

            old_patch = root / '1.5/Patches/add-old-def.xml'
            old_patch.parent.mkdir(parents=True, exist_ok=True)
            old_patch.write_text(
                '<Patch>'
                '<Operation Class="PatchOperationAdd">'
                '<xpath>Defs</xpath>'
                '<value>'
                '<OldDef>'
                '<defName>OldPatchedThing</defName>'
                '</OldDef>'
                '</value>'
                '</Operation>'
                '</Patch>'
            )

            wrong_target = root / '1.6/Patches/wrong-target.xml'
            wrong_target.write_text(
                '<Patch>'
                '<Operation Class="PatchOperationAdd">'
                '<xpath>Defs/ThingDef</xpath>'
                '<value>'
                '<ThingDef>'
                '<defName>WrongTarget</defName>'
                '</ThingDef>'
                '</value>'
                '</Operation>'
                '</Patch>'
            )

            self.assertEqual(
                sources.source_def_types(root),
                {
                    'Thing': {'ThingDef'},
                    'News': {'HugsLib.UpdateFeatureDef'},
                    'PatchedThing': {'ThingDef'},
                },
            )


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
        conf.write_text('<ModsConfigData><activeMods><li>test.mod</li><li>elhanko.rimworld.modtranslations</li></activeMods></ModsConfigData>')
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
        task = self.root / 'data/work/test.mod.German.work.json'
        data = common.load_json(task)
        for e in data['entries']:
            e['translation'] = 'Hallo {name}' if e['type'] == 'keyed' else 'Neuigkeiten'
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
        self.assertTrue(all(e['translations']['German']['needed'] is True and 'runtime' not in e for e in saved['entries']))
        self.assertEqual(
            progress.state(saved),
            {
                'needed': 2,
                'translated': 2,
                'open': 0,
                'review': 0,
                'retired': 0,
                'unknown': 0,
            },
        )
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
