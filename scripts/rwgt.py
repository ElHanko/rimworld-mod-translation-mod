#!/usr/bin/env python3

from collections import Counter
from pathlib import Path
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LANG = ROOT / "Languages" / "German"
TRANSLATIONS = ROOT / "translations"

REPORT_LINK = DATA / "TranslationReport.txt"
DESKTOP = Path.home() / "Desktop"

STEAM_MODS = Path(
    "/mnt/OBS-Archive-DISK/steam/steamapps/common/RimWorld/Mods"
)

WORKSHOP = Path(
    "/mnt/OBS-Archive-DISK/steam/steamapps/workshop/content/294100"
)

MODS_CONFIG = (
    Path.home()
    / ".config/unity3d/Ludeon Studios/"
      "RimWorld by Ludeon Studios/Config/ModsConfig.xml"
)

STEAM_LINK = STEAM_MODS / "ElHanko-German-Translations"


def die(msg):
    print(f"FEHLER: {msg}", file=sys.stderr)
    raise SystemExit(1)


def find_latest_report():
    candidates = []

    for pattern in (
        "TranslationReport*.txt",
        "translationreport*.txt",
    ):
        candidates.extend(DESKTOP.glob(pattern))

    candidates = [
        p for p in candidates
        if p.is_file()
    ]

    if not candidates:
        die(f"Kein TranslationReport unter {DESKTOP} gefunden.")

    return max(
        candidates,
        key=lambda p: p.stat().st_mtime,
    )


def refresh_report():
    DATA.mkdir(parents=True, exist_ok=True)

    latest = find_latest_report()

    if REPORT_LINK.is_symlink() or REPORT_LINK.exists():
        REPORT_LINK.unlink()

    REPORT_LINK.symlink_to(latest)

    print("Translation Report:")
    print(f"  Quelle: {latest}")
    print(f"  Link:   {REPORT_LINK}")
    print()


def run_analyzer():
    analyzer = ROOT / "scripts" / "analyze-report.py"

    if not analyzer.exists():
        die(f"{analyzer} fehlt.")

    subprocess.run(
        [sys.executable, str(analyzer)],
        cwd=ROOT,
        check=True,
    )



def active_package_ids():
    if not MODS_CONFIG.exists():
        die(f"ModsConfig fehlt: {MODS_CONFIG}")

    root = ET.parse(MODS_CONFIG).getroot()

    return {
        node.text.strip()
        for node in root.findall(".//activeMods/li")
        if node.text and node.text.strip()
    }


def package_id_from_mod_root(mod_root):
    about = mod_root / "About" / "About.xml"

    if not about.exists():
        return None

    try:
        root = ET.parse(about).getroot()
    except ET.ParseError:
        return None

    node = root.find("packageId")

    if node is None or not node.text:
        return None

    return node.text.strip()


def discover_active_mod_roots():
    # ModsConfig und About.xml behandeln packageIds effektiv
    # case-insensitiv. Als kanonischen Namen behalten wir die
    # Schreibweise aus ModsConfig.xml bei.
    active = {
        package_id.casefold(): package_id
        for package_id in active_package_ids()
    }

    own_package = (
        "elhanko.rimworld.germantranslations"
        .casefold()
    )

    result = {}

    for parent in (WORKSHOP, STEAM_MODS):
        if not parent.exists():
            continue

        for mod_root in parent.iterdir():
            if not mod_root.is_dir():
                continue

            source_package_id = (
                package_id_from_mod_root(mod_root)
            )

            if not source_package_id:
                continue

            folded = source_package_id.casefold()

            if folded == own_package:
                continue

            canonical = active.get(folded)

            if canonical is not None:
                result[canonical] = mod_root

    return result


_VERSION_DIR = re.compile(r"^\d+\.\d+$")


def current_def_xml_files(mod_root):
    """
    Liefert nur Def-Dateien für den aktuellen 1.6-Stand.

    Alte Versionsordner wie 1.4/ oder 1.5/ werden ignoriert.
    Languages, About und Patches werden ebenfalls nicht als
    Def-Quelle verwendet.
    """

    for path in mod_root.rglob("*.xml"):
        try:
            rel = path.relative_to(mod_root)
        except ValueError:
            continue

        parts = rel.parts

        if (
            "Languages" in parts
            or "About" in parts
            or "Patches" in parts
        ):
            continue

        if "Defs" not in parts:
            continue

        old_version = any(
            _VERSION_DIR.match(part)
            and part != "1.6"
            for part in parts
        )

        if old_version:
            continue

        yield path


def source_def_types(mod_root):
    """
    Mappt:
        defName -> Menge vollständiger XML-Tags

    Beispiel:
        VTE_General
          -> ModSettingsFramework.ModOptionCategoryDef
    """

    result = {}

    for path in current_def_xml_files(mod_root):
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError:
            continue

        for element in root.iter():
            defname_node = element.find("defName")

            if (
                defname_node is None
                or not defname_node.text
            ):
                continue

            defname = defname_node.text.strip()

            tag = element.tag

            # Falls tatsächlich ein XML-Namespace vorkommt:
            if "}" in tag:
                tag = tag.rsplit("}", 1)[1]

            result.setdefault(
                defname,
                set(),
            ).add(tag)

    return result


def resolve_mapped_def_types():
    """
    report-mapped.jsonl enthält zunächst den vom Translation
    Report angegebenen Kurztyp.

    Für benutzerdefinierte Def-Klassen kann RimWorld dort z.B.
    ModOptionCategoryDef melden, während der für DefInjected
    erforderliche Ordner tatsächlich

        ModSettingsFramework.ModOptionCategoryDef

    heißt.

    Deshalb wird der Typ anhand der echten Quell-Defs ersetzt.
    """

    mapped_path = DATA / "report-mapped.jsonl"

    if not mapped_path.exists():
        die(
            "report-mapped.jsonl fehlt nach Analyzer-Lauf."
        )

    records = []

    for line in mapped_path.read_text(
        encoding="utf-8",
        errors="replace",
    ).splitlines():

        if line.strip():
            records.append(json.loads(line))

    needed_packages = {
        record["package_id"]
        for record in records
        if record.get("type") == "def"
    }

    mod_roots = discover_active_mod_roots()

    indexes = {}

    resolved = 0
    unchanged = 0
    ambiguous = 0
    missing = 0

    for package_id in sorted(needed_packages):
        mod_root = mod_roots.get(package_id)

        if mod_root is None:
            continue

        indexes[package_id] = source_def_types(
            mod_root
        )

    for record in records:
        if record.get("type") != "def":
            continue

        package_id = record["package_id"]
        def_name = record["def_name"]
        short_type = record["def_type"]

        candidates = (
            indexes
            .get(package_id, {})
            .get(def_name, set())
        )

        if not candidates:
            missing += 1
            continue

        if len(candidates) == 1:
            full_type = next(iter(candidates))

        else:
            matching = {
                candidate
                for candidate in candidates
                if (
                    candidate == short_type
                    or candidate.endswith(
                        "." + short_type
                    )
                )
            }

            if len(matching) == 1:
                full_type = next(iter(matching))
            else:
                ambiguous += 1
                continue

        if full_type != short_type:
            record["def_type"] = full_type
            resolved += 1
        else:
            unchanged += 1

    mapped_path.write_text(
        "".join(
            json.dumps(
                record,
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
            for record in records
        ),
        encoding="utf-8",
    )

    print()
    print("Def-Typ-Auflösung:")
    print(f"  Volltyp ergänzt: {resolved}")
    print(f"  Bereits korrekt: {unchanged}")
    print(f"  Mehrdeutig:      {ambiguous}")
    print(f"  Nicht gefunden:  {missing}")

def parse_summary():
    path = DATA / "report-summary.txt"

    if not path.exists():
        die(
            "report-summary.txt fehlt. "
            "Zuerst './rwgt refresh' ausführen."
        )

    rows = []

    for line in path.read_text(
        encoding="utf-8",
        errors="replace",
    ).splitlines():

        parts = line.split(None, 4)

        if len(parts) != 5:
            continue

        try:
            total = int(parts[0])
            keyed = int(parts[1])
            defs = int(parts[2])
        except ValueError:
            continue

        package_id = parts[3]
        name = parts[4]

        rows.append(
            {
                "package_id": package_id,
                "name": name,
                "missing": total,
                "keyed": keyed,
                "defs": defs,
            }
        )

    return rows


def count_our_keyed():
    result = {}

    directory = LANG / "Keyed"

    if not directory.exists():
        return result

    for path in directory.glob("*.xml"):
        package_id = path.stem

        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as exc:
            print(
                f"WARNUNG: ungültiges XML: "
                f"{path}: {exc}"
            )
            continue

        result[package_id] = len(list(root))

    return result


def count_our_defs():
    result = {}

    directory = LANG / "DefInjected"

    if not directory.exists():
        return result

    for def_dir in directory.iterdir():
        if not def_dir.is_dir():
            continue

        for path in def_dir.glob("*.xml"):
            package_id = path.stem

            try:
                root = ET.parse(path).getroot()
            except ET.ParseError as exc:
                print(
                    f"WARNUNG: ungültiges XML: "
                    f"{path}: {exc}"
                )
                continue

            result[package_id] = (
                result.get(package_id, 0)
                + len(list(root))
            )

    return result


def status():
    rows = parse_summary()

    ours_keyed = count_our_keyed()
    ours_defs = count_our_defs()

    known = {
        row["package_id"]
        for row in rows
    }

    known |= set(ours_keyed)
    known |= set(ours_defs)

    by_id = {
        row["package_id"]: row
        for row in rows
    }

    result = []

    for package_id in known:
        row = by_id.get(
            package_id,
            {
                "package_id": package_id,
                "name": package_id,
                "missing": 0,
                "keyed": 0,
                "defs": 0,
            },
        )

        translated = (
            ours_keyed.get(package_id, 0)
            + ours_defs.get(package_id, 0)
        )

        total = row["missing"] + translated

        result.append(
            (
                row["missing"],
                package_id,
                row["name"],
                row["keyed"],
                row["defs"],
                translated,
                total,
            )
        )

    result.sort(reverse=True)

    print()
    print(
        f"{'OFFEN':>6} "
        f"{'KEYED':>6} "
        f"{'DEF':>6} "
        f"{'UNSERE':>6} "
        f"{'GESAMT':>6}  "
        f"{'PACKAGE-ID':45} NAME"
    )

    print("-" * 130)

    for (
        missing,
        package_id,
        name,
        keyed,
        defs,
        translated,
        total,
    ) in result:

        marker = "✓" if missing == 0 else " "

        print(
            f"{missing:6} "
            f"{keyed:6} "
            f"{defs:6} "
            f"{translated:6} "
            f"{total:6} {marker} "
            f"{package_id:45} "
            f"{name}"
        )


def validate():
    errors = 0
    files = list(LANG.rglob("*.xml"))

    seen_keyed = {}

    for path in files:
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as exc:
            print(f"FEHLER XML: {path}: {exc}")
            errors += 1
            continue

        if root.tag != "LanguageData":
            print(
                f"FEHLER ROOT: {path}: "
                f"{root.tag!r} statt 'LanguageData'"
            )
            errors += 1

        if path.parent.name == "Keyed":
            for child in root:
                key = child.tag

                if key in seen_keyed:
                    print(
                        f"DOPPELTER KEY: {key}\n"
                        f"  {seen_keyed[key]}\n"
                        f"  {path}"
                    )
                    errors += 1
                else:
                    seen_keyed[key] = path

    print()
    print(f"XML-Dateien: {len(files)}")
    print(f"Keyed-Einträge: {len(seen_keyed)}")
    print(f"Fehler: {errors}")

    if errors:
        raise SystemExit(1)

    print("Validierung: OK")


def install():
    expected = ROOT.resolve()

    if STEAM_LINK.is_symlink():
        actual = STEAM_LINK.resolve()

        if actual == expected:
            print(f"Symlink bereits korrekt: {STEAM_LINK}")
            return

        die(
            f"{STEAM_LINK} zeigt auf {actual}, "
            f"erwartet wird {expected}."
        )

    if STEAM_LINK.exists():
        die(
            f"{STEAM_LINK} existiert bereits "
            "und ist kein Symlink. Keine Änderung vorgenommen."
        )

    STEAM_LINK.symlink_to(expected)

    print(f"Symlink angelegt:")
    print(f"  {STEAM_LINK}")
    print(f"  -> {expected}")


def show_work(package_id):
    rows = parse_summary()

    row = next(
        (
            r for r in rows
            if r["package_id"] == package_id
        ),
        None,
    )

    mapped_path = DATA / "report-mapped.jsonl"

    if not mapped_path.exists():
        die(
            "report-mapped.jsonl fehlt. "
            "Zuerst './rwgt refresh' ausführen."
        )

    records = []

    for line in mapped_path.read_text(
        encoding="utf-8",
        errors="replace",
    ).splitlines():
        if not line.strip():
            continue

        record = json.loads(line)

        if record.get("package_id") == package_id:
            records.append(record)

    if row is None and not records:
        name = package_id

        draft_path = (
            TRANSLATIONS
            / f"{package_id}.json"
        )

        if draft_path.exists():
            try:
                existing = json.loads(
                    draft_path.read_text(
                        encoding="utf-8"
                    )
                )
                name = existing.get(
                    "name",
                    package_id,
                )
            except (
                OSError,
                json.JSONDecodeError,
            ):
                pass

        work_dir = DATA / "work"
        work_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        out = work_dir / f"{package_id}.json"

        out.write_text(
            json.dumps(
                {
                    "package_id": package_id,
                    "name": name,
                    "counts": {
                        "keyed": 0,
                        "def_injected": 0,
                        "total": 0,
                    },
                    "entries": [],
                },
                ensure_ascii=False,
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )

        print(
            f"{package_id}: aktuell keine eindeutig "
            "zugeordneten fehlenden Übersetzungen."
        )

        print()
        print(f"Arbeitsdatei: {out}")
        return

    name = (
        row["name"]
        if row is not None
        else package_id
    )

    keyed = sum(
        1 for record in records
        if record["type"] == "keyed"
    )

    defs = sum(
        1 for record in records
        if record["type"] == "def"
    )

    work_dir = DATA / "work"
    work_dir.mkdir(parents=True, exist_ok=True)

    out = work_dir / f"{package_id}.json"

    payload = {
        "package_id": package_id,
        "name": name,
        "counts": {
            "keyed": keyed,
            "def_injected": defs,
            "total": len(records),
        },
        "entries": records,
    }

    out.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    print(name)
    print(f"Package:     {package_id}")
    print(f"Keyed:       {keyed}")
    print(f"DefInjected: {defs}")
    print(f"Gesamt:      {len(records)}")
    print()
    print(f"Arbeitsdatei: {out}")

    if row is not None and len(records) != row["missing"]:
        print()
        print(
            "WARNUNG: Anzahl der Arbeitsdatensätze "
            f"({len(records)}) weicht vom Summary "
            f"({row['missing']}) ab."
        )




def normalize_entry_def_types(package_id, entries):
    """
    Normalisiert Def-Typen anhand der tatsächlich geladenen
    Quellmod.

    Beispiel:
        ModOptionCategoryDef
    wird zu:
        ModSettingsFramework.ModOptionCategoryDef

    Vorhandene Übersetzungen werden dabei nicht verändert.
    """

    mod_root = discover_active_mod_roots().get(package_id)

    if mod_root is None:
        unresolved = [
            entry.get("path", "?")
            for entry in entries
            if entry.get("type") == "def"
        ]

        return 0, unresolved

    index = source_def_types(mod_root)

    changed = 0
    unresolved = []

    for entry in entries:
        if entry.get("type") != "def":
            continue

        def_name = entry.get("def_name")
        current_type = entry.get("def_type")

        if not def_name:
            unresolved.append(
                entry.get("path", "?")
            )
            continue

        candidates = index.get(
            def_name,
            set(),
        )

        if not candidates:
            unresolved.append(
                entry.get("path", def_name)
            )
            continue

        if len(candidates) == 1:
            full_type = next(iter(candidates))

        else:
            matching = {
                candidate
                for candidate in candidates
                if (
                    candidate == current_type
                    or (
                        current_type
                        and candidate.endswith(
                            "." + current_type
                        )
                    )
                )
            }

            if len(matching) != 1:
                unresolved.append(
                    entry.get("path", def_name)
                )
                continue

            full_type = next(iter(matching))

        if full_type != current_type:
            entry["def_type"] = full_type
            changed += 1

    return changed, unresolved

def entry_identity(entry):
    if entry["type"] == "keyed":
        return (
            "keyed",
            entry["key"],
        )

    if entry["type"] == "def":
        # Der Def-Typ ist Metadatum und kann durch eine bessere
        # Quellauflösung präzisiert werden. Der stabile Identifier
        # innerhalb eines Package-Drafts ist der Def-Pfad.
        return (
            "def",
            entry["path"],
        )

    raise ValueError(
        f"Unbekannter Eintragstyp: {entry.get('type')!r}"
    )


def make_draft(package_id):
    # Arbeitsdatei immer aus dem aktuellen Report neu erzeugen.
    show_work(package_id)

    work_path = DATA / "work" / f"{package_id}.json"

    if not work_path.exists():
        die(f"Arbeitsdatei fehlt: {work_path}")

    work = json.loads(
        work_path.read_text(encoding="utf-8")
    )

    TRANSLATIONS.mkdir(
        parents=True,
        exist_ok=True,
    )

    draft_path = TRANSLATIONS / f"{package_id}.json"

    old_entries = {}

    if draft_path.exists():
        old = json.loads(
            draft_path.read_text(encoding="utf-8")
        )

        for entry in old.get("entries", []):
            old_entries[entry_identity(entry)] = entry

    # Bestehende Einträge grundsätzlich behalten.
    merged = dict(old_entries)

    added = 0
    preserved = 0
    changed = 0

    for source in work["entries"]:
        ident = entry_identity(source)
        previous = old_entries.get(ident)

        entry = dict(source)

        if previous is None:
            entry["german"] = ""
            entry["review"] = False
            added += 1

        else:
            entry["german"] = previous.get(
                "german",
                "",
            )

            old_english = previous.get(
                "english",
                "",
            )

            if old_english != source.get("english", ""):
                entry["review"] = True
                entry["previous_english"] = old_english
                changed += 1
            else:
                entry["review"] = previous.get(
                    "review",
                    False,
                )
                preserved += 1

        merged[ident] = entry

    entries = list(merged.values())

    normalized_defs, unresolved_defs = (
        normalize_entry_def_types(
            package_id,
            entries,
        )
    )

    # Stabile Reihenfolge.
    entries.sort(
        key=lambda e: (
            e["type"],
            e.get("source") or "",
            e.get("key")
            or e.get("path")
            or "",
        )
    )

    payload = {
        "package_id": package_id,
        "name": work["name"],
        "entries": entries,
    }

    draft_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    translated = sum(
        bool(e.get("german"))
        for e in entries
    )

    review = sum(
        bool(e.get("review"))
        for e in entries
    )

    print()
    print(f"Draft:       {draft_path}")
    print(f"Einträge:    {len(entries)}")
    print(f"Neu:         {added}")
    print(f"Beibehalten: {preserved}")
    print(f"Geändert:    {changed}")
    print(f"Übersetzt:   {translated}")
    print(f"Review:      {review}")
    print(
        f"Def-Typen korrigiert: "
        f"{normalized_defs}"
    )

    if unresolved_defs:
        print(
            f"Def-Typen ungeklärt:   "
            f"{len(unresolved_defs)}"
        )

        for ident in unresolved_defs[:10]:
            print(f"  - {ident}")

        if len(unresolved_defs) > 10:
            print(
                f"  ... und "
                f"{len(unresolved_defs) - 10} weitere"
            )


_SIMPLE_PLACEHOLDER = re.compile(
    r"\{(?:\d+|[A-Za-z_][A-Za-z0-9_]*)\}"
)


def placeholders(text):
    return Counter(
        _SIMPLE_PLACEHOLDER.findall(text or "")
    )


def build_translation(package_id):
    draft_path = TRANSLATIONS / f"{package_id}.json"

    if not draft_path.exists():
        die(
            f"{draft_path} fehlt. "
            f"Zuerst './rwgt draft {package_id}' ausführen."
        )

    data = json.loads(
        draft_path.read_text(encoding="utf-8")
    )

    entries = data.get("entries", [])

    normalized_defs, unresolved_defs = (
        normalize_entry_def_types(
            package_id,
            entries,
        )
    )

    if normalized_defs:
        draft_path.write_text(
            json.dumps(
                data,
                ensure_ascii=False,
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )

        print(
            f"Def-Typen vor Build korrigiert: "
            f"{normalized_defs}"
        )

    if unresolved_defs:
        print(
            "FEHLER: Def-Typ konnte für "
            f"{len(unresolved_defs)} Einträge "
            "nicht eindeutig bestimmt werden."
        )

        for ident in unresolved_defs[:20]:
            print(f"  - {ident}")

        raise SystemExit(1)

    empty = []
    reviews = []
    placeholder_errors = []

    for entry in entries:
        german = entry.get("german", "")

        ident = (
            entry.get("key")
            or entry.get("path")
            or "?"
        )

        if not german:
            empty.append(ident)
            continue

        if entry.get("review"):
            reviews.append(ident)

        source_ph = placeholders(
            entry.get("english", "")
        )

        german_ph = placeholders(german)

        if source_ph != german_ph:
            placeholder_errors.append(
                (
                    ident,
                    source_ph,
                    german_ph,
                )
            )

    if empty:
        print(
            f"FEHLER: {len(empty)} Übersetzungen fehlen."
        )

        for ident in empty[:20]:
            print(f"  - {ident}")

        if len(empty) > 20:
            print(
                f"  ... und {len(empty) - 20} weitere"
            )

        raise SystemExit(1)

    if reviews:
        print(
            f"FEHLER: {len(reviews)} Einträge "
            "sind noch als Review markiert."
        )

        for ident in reviews[:20]:
            print(f"  - {ident}")

        raise SystemExit(1)

    if placeholder_errors:
        print(
            f"FEHLER: {len(placeholder_errors)} "
            "Placeholder-Abweichungen."
        )

        for ident, source_ph, german_ph in placeholder_errors:
            print(f"  {ident}")
            print(f"    Englisch: {dict(source_ph)}")
            print(f"    Deutsch:  {dict(german_ph)}")

        raise SystemExit(1)

    keyed = [
        e for e in entries
        if e["type"] == "keyed"
    ]

    defs = {}

    for entry in entries:
        if entry["type"] != "def":
            continue

        defs.setdefault(
            entry["def_type"],
            [],
        ).append(entry)

    # Keyed
    keyed_dir = LANG / "Keyed"
    keyed_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    keyed_path = keyed_dir / f"{package_id}.xml"

    if keyed:
        root = ET.Element("LanguageData")

        for entry in keyed:
            node = ET.SubElement(
                root,
                entry["key"],
            )
            node.text = entry["german"]

        ET.indent(root, space="  ")

        ET.ElementTree(root).write(
            keyed_path,
            encoding="utf-8",
            xml_declaration=True,
            short_empty_elements=False,
        )

    elif keyed_path.exists():
        keyed_path.unlink()

    # DefInjected
    def_root = LANG / "DefInjected"

    # Alte von uns erzeugte Dateien dieser Package-ID entfernen,
    # bevor die aktuellen Def-Typen geschrieben werden.
    if def_root.exists():
        for old_path in def_root.glob(
            f"*/{package_id}.xml"
        ):
            old_path.unlink()

    for def_type, def_entries in sorted(defs.items()):
        directory = def_root / def_type

        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        path = directory / f"{package_id}.xml"

        root = ET.Element("LanguageData")

        for entry in def_entries:
            node = ET.SubElement(
                root,
                entry["path"],
            )
            node.text = entry["german"]

        ET.indent(root, space="  ")

        ET.ElementTree(root).write(
            path,
            encoding="utf-8",
            xml_declaration=True,
            short_empty_elements=False,
        )

    print(f"Build: {package_id}")
    print(f"  Keyed:       {len(keyed)}")
    print(
        f"  DefInjected: "
        f"{sum(len(x) for x in defs.values())}"
    )

    validate()


def draft_status(package_id):
    path = TRANSLATIONS / f"{package_id}.json"

    if not path.exists():
        die(
            f"{path} fehlt. "
            f"Zuerst './rwgt draft {package_id}' ausführen."
        )

    data = json.loads(
        path.read_text(encoding="utf-8")
    )

    entries = data.get("entries", [])

    done = sum(
        bool(e.get("german"))
        for e in entries
    )

    review = sum(
        bool(e.get("review"))
        for e in entries
    )

    total = len(entries)

    print(data.get("name", package_id))
    print(f"Package:    {package_id}")
    print(f"Gesamt:     {total}")
    print(f"Übersetzt:  {done}")
    print(f"Offen:      {total - done}")
    print(f"Review:     {review}")



def verify_translation(package_id):
    rows = parse_summary()

    row = next(
        (
            r for r in rows
            if r["package_id"] == package_id
        ),
        None,
    )

    missing = row["missing"] if row else 0
    missing_keyed = row["keyed"] if row else 0
    missing_defs = row["defs"] if row else 0

    draft_path = TRANSLATIONS / f"{package_id}.json"

    expected = None
    name = package_id

    if draft_path.exists():
        data = json.loads(
            draft_path.read_text(encoding="utf-8")
        )

        name = data.get("name", package_id)
        expected = len(data.get("entries", []))

    built_keyed = 0

    keyed_path = (
        LANG
        / "Keyed"
        / f"{package_id}.xml"
    )

    if keyed_path.exists():
        root = ET.parse(keyed_path).getroot()
        built_keyed = len(list(root))

    built_defs = 0

    def_root = LANG / "DefInjected"

    if def_root.exists():
        for path in def_root.glob(
            f"*/{package_id}.xml"
        ):
            root = ET.parse(path).getroot()
            built_defs += len(list(root))

    built = built_keyed + built_defs

    print(name)
    print(f"Package:          {package_id}")

    if expected is not None:
        print(f"Draft-Einträge:   {expected}")

    print(f"Gebaut Keyed:     {built_keyed}")
    print(f"Gebaut Defs:      {built_defs}")
    print(f"Gebaut gesamt:    {built}")
    print(f"Report Keyed:     {missing_keyed}")
    print(f"Report Defs:      {missing_defs}")
    print(f"Report offen:     {missing}")
    print()

    errors = []

    if expected is not None and built != expected:
        errors.append(
            f"Build enthält {built}, "
            f"Draft aber {expected} Einträge."
        )

    if missing:
        errors.append(
            f"Im aktuellen RimWorld-Report "
            f"sind noch {missing} Einträge offen."
        )

    if errors:
        print("Status: ✗ nicht vollständig verifiziert")

        for error in errors:
            print(f"  - {error}")

        raise SystemExit(1)

    if expected is None:
        print(
            "Status: ? im Report vollständig, "
            "aber kein Draft vorhanden"
        )
        return

    print("Status: ✓ vollständig wirksam")

def refresh():
    refresh_report()
    run_analyzer()
    resolve_mapped_def_types()
    status()
    print()
    validate()


def usage():
    print(
        """Nutzung:
  ./rwgt refresh
  ./rwgt status
  ./rwgt validate
  ./rwgt install
  ./rwgt work PACKAGE-ID
  ./rwgt draft PACKAGE-ID
  ./rwgt progress PACKAGE-ID
  ./rwgt build PACKAGE-ID
  ./rwgt verify PACKAGE-ID
"""
    )


def main():
    if len(sys.argv) < 2:
        usage()
        raise SystemExit(2)

    command = sys.argv[1]

    if command == "refresh":
        refresh()

    elif command == "status":
        status()

    elif command == "validate":
        validate()

    elif command == "install":
        install()

    elif command == "work":
        if len(sys.argv) != 3:
            die("work benötigt eine Package-ID.")

        show_work(sys.argv[2])

    elif command == "draft":
        if len(sys.argv) != 3:
            die("draft benötigt eine Package-ID.")

        make_draft(sys.argv[2])

    elif command == "progress":
        if len(sys.argv) != 3:
            die("progress benötigt eine Package-ID.")

        draft_status(sys.argv[2])

    elif command == "build":
        if len(sys.argv) != 3:
            die("build benötigt eine Package-ID.")

        build_translation(sys.argv[2])

    elif command == "verify":
        if len(sys.argv) != 3:
            die("verify benötigt eine Package-ID.")

        verify_translation(sys.argv[2])

    else:
        usage()
        raise SystemExit(2)


if __name__ == "__main__":
    main()
