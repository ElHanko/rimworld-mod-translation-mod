"""Create a distributable RimWorld mod from deterministic runtime output."""
import os
from pathlib import Path
import shutil
import tempfile

import config
from build import collect_expected
from common import load_drafts, runtime_records
from verify import runtime_errors


MOD_DIRECTORY = 'RimWorld-Mod-Translations'


def validate_build(drafts, language):
    expected, included, excluded = collect_expected(drafts, language)
    directory = config.language_dir(language)
    errors = runtime_errors(expected, directory)

    if errors:
        details = '; '.join(errors[:3])
        if len(errors) > 3:
            details += f'; ... ({len(errors)} Fehler insgesamt)'
        raise ValueError(
            f'Build {language} nicht exportierbar; '
            f'./rwgt build --language {language} ausführen. '
            f'{details}'
        )

    return expected, included, excluded


def create_export(plans, make_zip=False):
    dist = config.ROOT / 'dist'
    target = dist / MOD_DIRECTORY
    archive_target = dist / f'{MOD_DIRECTORY}.zip'

    if dist.is_symlink():
        raise ValueError('dist ist ein Symlink; keine Änderung vorgenommen')
    if target.is_symlink():
        raise ValueError(f'{target} ist ein Symlink; keine Änderung vorgenommen')
    if target.exists() and not target.is_dir():
        raise ValueError(f'{target} existiert und ist kein Verzeichnis')

    if make_zip:
        if archive_target.is_symlink():
            raise ValueError(
                f'{archive_target} ist ein Symlink; keine Änderung vorgenommen'
            )
        if archive_target.exists() and not archive_target.is_file():
            raise ValueError(
                f'{archive_target} existiert und ist keine Datei'
            )

    about = config.ROOT / 'About' / 'About.xml'
    license_file = config.ROOT / 'LICENSE'

    for source in (about, license_file):
        if (
            not source.is_file()
            or source.is_symlink()
        ):
            raise ValueError(
                f'Export-Metadatei fehlt oder ist ungültig: {source}'
            )

    dist.mkdir(parents=True, exist_ok=True)

    stage = Path(
        tempfile.mkdtemp(
            prefix='.rwgt-export-',
            dir=dist,
        )
    )
    output = stage / MOD_DIRECTORY
    backup = stage / 'previous'
    archive = None

    try:
        (output / 'About').mkdir(parents=True)
        shutil.copy2(about, output / 'About' / 'About.xml')
        shutil.copy2(license_file, output / 'LICENSE')

        for language, (expected, _, _) in plans.items():
            source = config.language_dir(language)
            destination = output / 'Languages' / language

            if source.is_symlink() or any(
                path.is_symlink()
                for path in source.rglob('*')
            ):
                raise ValueError(
                    f'Runtime-Bestand {language} enthält Symlinks'
                )

            shutil.copytree(source, destination)

            errors = runtime_errors(expected, destination)
            if errors:
                raise ValueError(
                    f'Export-Kopie {language} ist inkonsistent: '
                    + '; '.join(errors[:3])
                )

        if make_zip:
            archive = Path(
                shutil.make_archive(
                    str(stage / MOD_DIRECTORY),
                    'zip',
                    root_dir=stage,
                    base_dir=MOD_DIRECTORY,
                )
            )

        if target.exists():
            target.rename(backup)

        try:
            output.rename(target)
        except BaseException:
            if backup.exists():
                backup.rename(target)
            raise

        if make_zip:
            os.replace(archive, archive_target)

    finally:
        # Preserve recovery data only if rollback itself failed.
        if not backup.exists() or target.exists():
            shutil.rmtree(stage)

    return target, archive_target if make_zip else None


def run(language=None, make_zip=False):
    drafts = load_drafts()
    languages = config.selected_languages(language)

    # Validate every selected language before touching dist/.
    plans = {
        target_language: validate_build(
            drafts,
            target_language,
        )
        for target_language in languages
    }

    target, archive = create_export(
        plans,
        make_zip,
    )

    for target_language in languages:
        expected, included, excluded = plans[target_language]
        records = runtime_records(
            target / 'Languages' / target_language
        )
        print(
            f'Export {target_language}: ✓ | '
            f'{len(included)} Drafts | '
            f'{len(records)} Einträge | '
            f'{len(expected)} XML-Dateien | '
            f'{len(excluded)} unvollständige Drafts ausgeschlossen'
        )

    print(f'Export: ✓ | {target}')

    if archive:
        print(f'ZIP: ✓ | {archive}')
