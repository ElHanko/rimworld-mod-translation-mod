# RimWorld Mod Translations

A deterministic translation workflow and translation mod for RimWorld mods.

The repository keeps translations outside the original Workshop mods, generates standard RimWorld language files, and supports one or more target languages from the same durable translation data.

The translation mod uses the package ID:

`elhanko.rimworld.modtranslations`

It must be loaded **after the source mods** whose translations it overrides or supplements.

The current tooling targets RimWorld 1.6. It requires a POSIX shell and Python 3.9 or newer and uses only the Python standard library.

## Repository layout

| Path                    | Purpose                                                                                            | Versioned                        |
| ----------------------- | -------------------------------------------------------------------------------------------------- | -------------------------------- |
| `translations/*.json`   | Durable source of truth for source texts, target-language states, identities, and review state     | Yes                              |
| `Languages/<Language>/` | Deterministically generated RimWorld runtime translation files                                     | Yes                              |
| `data/status.json`      | Latest local scan, TranslationReport metadata, active mods, resolver results, and runtime evidence | No                               |
| `data/work/*.work.json` | Disposable translation work packages                                                               | No                               |
| `data/`                 | Reproducible local reports and analysis data                                                       | Only selected placeholders/files |
| `rwgt.local.json`       | Private local configuration                                                                        | No                               |
| `rwgt.example.json`     | Public configuration example                                                                       | Yes                              |
| `dist/`                 | Local distribution exports and optional ZIP archives                                                | No                               |

Do not manually maintain generated XML files in `Languages/`. Translation changes belong in the durable drafts or in temporary work packages and are then applied back to the drafts.

A build is reproducible from the versioned drafts alone. Local analysis data is not required to regenerate the runtime files.

## Configuration

Create a local configuration:

```bash
cp rwgt.example.json rwgt.local.json
```

Example:

```json
{
  "game": "/path/to/steam/steamapps/common/RimWorld",
  "workshop": "/path/to/steam/steamapps/workshop/content/294100",
  "rimworld_home": "/path/to/user/config/RimWorld",
  "report_dir": "/path/to/translation-reports",
  "languages": [
    "German"
  ]
}
```

The fields are:

* `game`: RimWorld installation directory.
* `workshop`: Steam Workshop directory for RimWorld app ID `294100`.
* `rimworld_home`: RimWorld user-data directory containing `Config/ModsConfig.xml`.
* `report_dir`: directory containing RimWorld `TranslationReport*.txt` files.
* `languages`: one or more RimWorld language directory names.

Use RimWorld language names directly, for example:

```json
{
  "languages": [
    "German",
    "French",
    "Spanish"
  ]
}
```

There is intentionally no ISO-language alias layer.

English is the source language used by the translation workflow. Target languages are configurable.

For compatibility with older local configurations, omitting `languages` defaults to:

```json
["German"]
```

## Install as a local RimWorld mod

The repository can be linked into the local RimWorld installation:

```bash
./rwgt install
```

The target is:

```text
game/Mods/ElHanko-Mod-Translations
```

`install` is conservative:

* an already correct symlink is accepted;
* an incorrect symlink causes an error;
* an existing real file or directory causes an error;
* it does not overwrite another mod.

Enable `RimWorld Mod Translations` in RimWorld and load it after the translated source mods.

## TranslationReports are language-specific

RimWorld generates a TranslationReport for the currently selected language.

The report must start with an explicit language header such as:

```text
Translation report for German
```

A refresh is therefore always associated with exactly one target language:

```bash
./rwgt refresh --language German
```

Only a report whose header matches the requested language is accepted.

This distinction is important in a multilingual repository: a German report says nothing about whether an entry is required in French, Spanish, or any other language.

## Single-language workflow

With exactly one configured language, most language arguments can be omitted:

```bash
./rwgt refresh
./rwgt status
./rwgt draft --all
./rwgt progress
./rwgt work --next --limit 25

# Edit the "translation" fields in the generated work file.

./rwgt apply data/work/PACKAGE-ID.German.work.json
./rwgt build
./rwgt verify
```

`work` without an explicit package behaves like `work --next`.

## Multilingual workflow

Each target language needs its own TranslationReport before the tool can reliably determine which entries that language requires.

For example:

```bash
./rwgt refresh --language German
./rwgt draft --all

./rwgt refresh --language French
./rwgt draft --all
```

The report language stored in `data/status.json` determines which target-language `needed` state `draft --all` updates.

Then inspect progress separately:

```bash
./rwgt progress --language German
./rwgt progress --language French
```

Create work for a specific language:

```bash
./rwgt work --language German --next --limit 25
./rwgt work --language French --next --limit 25
```

Work files can coexist:

```text
data/work/example.mod.German.work.json
data/work/example.mod.French.work.json
```

`apply` reads the target language from the work file itself:

```bash
./rwgt apply data/work/example.mod.German.work.json
```

Build every configured language:

```bash
./rwgt build
```

Or only one:

```bash
./rwgt build --language German
```

The same applies to verification:

```bash
./rwgt verify
./rwgt verify --language German
```

## Commands

| Command                                                                   | Purpose                                                                       |
| ------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| `./rwgt refresh [--language LANGUAGE]`                                    | Scan active mods and a matching TranslationReport and refresh local status    |
| `./rwgt status [--language LANGUAGE]`                                     | Display the saved status                                                      |
| `./rwgt draft PACKAGE-ID`                                                 | Update one durable draft from the current status                              |
| `./rwgt draft --all`                                                      | Update all known drafts and create new mapped drafts                          |
| `./rwgt progress [PACKAGE-ID] [--language LANGUAGE]`                      | Show translated, open, review, retired, and unknown counts                    |
| `./rwgt work [PACKAGE-ID] [--language LANGUAGE] [--limit N] [--offset N]` | Generate a disposable work package                                            |
| `./rwgt work --next ...`                                                  | Select the smallest currently open draft                                      |
| `./rwgt apply WORK-FILE`                                                  | Validate and atomically apply work back to a durable draft                    |
| `./rwgt build [--language LANGUAGE]`                                      | Regenerate runtime XML for one or all configured languages                    |
| `./rwgt export [--language LANGUAGE] [--zip]`                             | Package a current build as a distributable RimWorld mod                       |
| `./rwgt verify [--language LANGUAGE]`                                     | Verify drafts, generated output, source synchronization, and runtime evidence |
| `./rwgt validate [--language LANGUAGE]`                                   | Validate generated XML and runtime identities                                 |
| `./rwgt install`                                                          | Safely install the repository as a local RimWorld mod                         |

## Durable draft model

A source entry is stored once and contains one independent state per target language.

Example:

```json
{
  "type": "keyed",
  "key": "Example_Key",
  "english": "Hello {name}",
  "translations": {
    "German": {
      "text": "Hallo {name}",
      "review": false,
      "needed": true
    },
    "French": {
      "text": "",
      "review": false,
      "needed": null
    }
  }
}
```

The target-language fields are:

* `text`: translated text for that language.
* `review`: whether the translation must be reviewed because the English source changed.
* `needed`: whether this language currently requires the entry.

`needed` is deliberately tri-state:

```text
true
```

The TranslationReport for this language requires the entry, or an existing translated entry is retained because its own runtime translation may have caused it to disappear from a later missing-translation report.

```text
false
```

A TranslationReport for this language has established that the entry is no longer required.

```text
null
```

No reliable TranslationReport has yet classified this source for this language.

A newly configured target language therefore starts as unknown rather than incorrectly being treated as not required.

`work` and `build` fail safely when the selected language still contains unknown `needed` states. Run:

```bash
./rwgt refresh --language LANGUAGE
./rwgt draft --all
```

before translating or building that language.

Removing a language from the local configuration does not delete its durable translation state from the drafts.

## English source changes and review state

When the English source text changes, every stored target-language state for that source is marked for review.

The previous English text is retained in that target state as:

```json
"previous_english": "Old source text"
```

Repeated scans preserve the original pre-review English text until the translation is explicitly accepted through `apply`.

This allows German, French, or any other target language to be reviewed independently.

## Why translated entries can remain `needed=true`

RimWorld's TranslationReport is affected by this translation mod itself.

Consider this sequence:

1. RimWorld reports a missing German translation.
2. The repository adds the German translation.
3. The generated language mod is loaded.
4. RimWorld no longer reports the entry as missing.

The disappearance does not prove that the source entry was removed or that the upstream mod added an official translation. It may simply prove that our translation works.

For that reason, when a previously required entry disappears from a language-specific report:

* if it already has a translation and was previously needed, it remains needed;
* if it was required but still untranslated, the new report can retire it;
* an already retired entry remains retired;
* if it appears again in a later report, it becomes needed again.

This logic is evaluated independently for every target language.

## Work packages

Work files are disposable views of currently open translation work.

An entry contains fields such as:

```json
{
  "english": "Hello {name}",
  "translation": "",
  "original_translation": "",
  "review": false
}
```

Translate only the `translation` field and, where applicable, review the English source change.

`original_translation` protects against concurrent edits. If the durable target-language text changed after the work file was generated, `apply` refuses to overwrite it.

`apply` validates the complete work file before changing a draft, including:

* work-file language;
* package and draft identity;
* unique entry identity;
* current language-specific `needed=true`;
* unchanged English source;
* unchanged `original_translation`;
* translation string type;
* exact placeholder preservation.

Empty translations are skipped.

Successful entries are written to the selected target-language state, `review` becomes `false`, and `previous_english` is removed.

Generating a new work file for the same package and language replaces the previous disposable work file.

## Placeholder preservation

Placeholders must be preserved exactly.

For example:

```text
{name}
{0}
{1}
```

The validator compares placeholder counts, including repeated placeholders.

A translation that changes, removes, or adds placeholders is rejected.

This is intentionally a structural check rather than a complete RimWorld grammar parser.

## Keyed and DefInjected identities

Keyed translations use the RimWorld translation key as their runtime identity.

DefInjected translations use the Def path together with type information.

Generated output is placed under:

```text
Languages/<Language>/Keyed/PACKAGE-ID.xml
```

and:

```text
Languages/<Language>/DefInjected/FULL.DEF.TYPE/PACKAGE-ID.xml
```

Fully qualified Def types are preserved, including types such as:

```text
HugsLib.UpdateFeatureDef
ModSettingsFramework.ModOptionCategoryDef
VEF.Weapons.ExpandableProjectileDef
```

When the same Def path can legitimately occur under different Def classes, an `identity_scope` derived from the short Def class name keeps the durable identities distinct.

Ambiguous migrations abort instead of guessing.

## Def type resolution

The resolver statically inspects active source mods.

It uses normal Def XML sources from the relevant current RimWorld content and also conservatively recognizes Defs introduced by current-version patches when all of the following are true:

* the operation is `PatchOperationAdd`;
* the direct `<xpath>` is exactly `Defs`;
* the added direct `<value>` children contain a `defName`.

This allows simple patch-created Defs to resolve correctly without pretending to implement RimWorld's complete patch engine.

Older version directories, language output, and unrelated patch operations are excluded from that inference.

The resolver records states such as:

```text
resolved
ambiguous
missing
```

Unresolved or ambiguous Def types prevent the containing draft from being built.

## Deterministic build

A draft is build-ready for a target language when all entries required by that language:

* contain non-empty translated text;
* have no pending review;
* preserve placeholders exactly;
* have resolved Def types where applicable.

An incomplete draft is excluded as a whole.

Only required and ready entries from included drafts are emitted.

Before replacing any language output, a multi-language build computes and validates the plans for all selected languages. If one selected language is invalid or still has unknown requirements, no selected language output is replaced.

Output is generated in a temporary directory below `Languages/` and then swapped into place.

A failed directory exchange attempts to restore the previous output.

Stale generated files therefore do not survive a successful rebuild.

Byte-identical output is not rewritten unnecessarily.

## Distribution export

A current deterministic build can be packaged as a standalone RimWorld mod:

    ./rwgt export

The export is written to:

    dist/RimWorld-Mod-Translations/
    ├── About/
    │   └── About.xml
    ├── LICENSE
    ├── SUPPORTED-MODS.txt
    └── Languages/
        └── <Language>/

`SUPPORTED-MODS.txt` is generated deterministically from the durable drafts
and the actual export build plan. It lists only mods whose translations are
complete and therefore included in at least one selected export language,
including name, Workshop ID and URL when known, package ID, and included
languages. Local installation state does not affect the list.

Only distribution files are included. Development data such as `scripts/`,
`translations/`, `data/`, local configuration, work files, and Git metadata
are not copied.

Export only one configured language:

    ./rwgt export --language German

Create the directory export plus a ZIP archive:

    ./rwgt export --zip

The archive is written to:

    dist/RimWorld-Mod-Translations.zip

`export` does not modify drafts or rebuild `Languages/`. It recomputes the
deterministic expected output from the durable drafts and requires the existing
runtime tree to match it exactly. Missing, stale, unexpected, or changed
runtime files abort the export; run `./rwgt build` first in that case.

A current TranslationReport or runtime confirmation is deliberately not
required for export. Supported mods therefore do not need to be installed or
active when a distribution package is created. Known build-ready translations
remain part of the translation mod, while unrelated or unknown mods are not
added automatically.

The resulting directory or ZIP can be used for private distribution, release
packaging, or as the content basis for a Steam Workshop item.

## Duplicate runtime identities

Global duplicate Keyed or DefInjected runtime identities are allowed only when their English source and target translation are identical.

Conflicting duplicates abort the build before output is changed.

Duplicate identities inside a single draft are always an error.

## Refresh and source analysis

`refresh`:

1. selects a TranslationReport matching the requested language;
2. reads the active RimWorld mod configuration;
3. maps missing Keyed and DefInjected entries to source packages;
4. resolves Def types from active source mods;
5. records local runtime evidence;
6. writes the canonical local `data/status.json`.

Additional analysis artifacts may include files such as:

```text
data/report-summary.txt
data/report-mapped.jsonl
data/report-ambiguous.txt
data/report-unmapped.txt
data/analyzer.log
```

Source mods and Workshop files are read only.

The optional language inventory remains available as:

```bash
python3 scripts/inventory-languages.py
```

## Runtime verification

Local consistency and RimWorld runtime confirmation are separate concepts.

A build can be locally correct while runtime evidence is still reported as pending.

After generating new language files:

1. start RimWorld with the source mods and `RimWorld Mod Translations`;
2. select the target language;
3. generate a new TranslationReport;
4. run:

```bash
./rwgt refresh --language LANGUAGE
./rwgt verify --language LANGUAGE
```

Runtime evidence is language-specific.

A German TranslationReport cannot confirm French runtime output, even when both translations happen to contain identical text.

The runtime snapshot also depends on the active mod configuration and semantic hashes of generated entries.

Changed translations, keys, Def locations, or relevant mod configuration invalidate previous confirmation.

RimWorld is never started automatically by the tooling.

## Update cycle

After RimWorld or Workshop updates, refresh every target language that you actively maintain.

For one language:

```bash
./rwgt refresh --language German
./rwgt draft --all
./rwgt progress --language German
./rwgt verify --language German
```

For multiple languages:

```bash
./rwgt refresh --language German
./rwgt draft --all

./rwgt refresh --language French
./rwgt draft --all

./rwgt progress
./rwgt build
./rwgt verify
```

For new translation work:

```bash
./rwgt work --language German --next --limit 25
# Edit "translation" in the generated work file.
./rwgt apply data/work/PACKAGE-ID.German.work.json
./rwgt progress --language German
./rwgt build --language German
./rwgt verify --language German
```

## Compatibility with the earlier German-only format

Earlier repository versions stored German translation state directly on each entry using fields such as:

```text
german
needed
review
previous_english
```

The current workflow can migrate that historical format, as well as the intermediate multilingual format that still used a global `needed` flag.

Existing German text and review state are preserved during migration.

The compatibility path is intentionally limited to the historical German format; new target languages use the generic per-language structure.

## Limitations

* The static resolver does not implement RimWorld's complete load-folder, inheritance, or patch execution semantics.
* Runtime-generated Defs may not be statically resolvable.
* Some source mappings can remain ambiguous.
* A missing entry disappearing from a TranslationReport does not by itself prove why it disappeared.
* English reviews can only react to source text that is visible in the available report/source analysis.
* Hard-coded C# strings without a translation key cannot be translated by this workflow.
* Concurrent write operations from multiple CLI processes are not supported.
* Runtime confirmation is evidence from a saved report and local mod configuration, not a live query to a running RimWorld process.

## Tests

Run the complete test suite with:

```bash
python3 scripts/test_workflow.py
```

Additional checks:

```bash
python3 -m py_compile scripts/*.py
git diff --check
```

The tests use temporary directories and do not modify the Steam Workshop installation.

They cover configuration, migration, language-specific `needed` state, draft merging, source changes, work selection, atomic apply behavior, placeholder validation, Def resolution, multilingual build isolation, rollback, verification, and runtime evidence boundaries.

## License

The repository's own code and translations are licensed under the [MIT License](LICENSE).

RimWorld, translated mods, and their original content remain subject to the rights and licenses of their respective authors.
