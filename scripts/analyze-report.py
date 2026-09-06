#!/usr/bin/env python3

from collections import Counter, defaultdict
import json
import re
import xml.etree.ElementTree as ET

import config

try:
    config.configure()
except ValueError as exc:
    raise SystemExit(f"FEHLER: {exc}")

CONFIG = config.MODS_CONFIG
WORKSHOP = config.WORKSHOP
LOCAL_MODS = config.LOCAL_MODS

REPORT = config.DATA / "TranslationReport.txt"
OUT_SUMMARY = config.DATA / "report-summary.txt"
OUT_UNMAPPED = config.DATA / "report-unmapped.txt"
OUT_AMBIGUOUS = config.DATA / "report-ambiguous.txt"
OUT_MAPPED = config.DATA / "report-mapped.jsonl"


def parse_about(modroot):
    about = modroot / "About" / "About.xml"
    if not about.exists():
        return None

    try:
        root = ET.parse(about).getroot()
    except (ET.ParseError, OSError):
        return None

    package_id = (root.findtext("packageId") or "").strip()
    name = (root.findtext("name") or package_id).strip()

    if not package_id:
        return None

    return package_id.lower(), name


def active_package_ids():
    root = ET.parse(CONFIG).getroot()

    return [
        li.text.strip().lower()
        for li in root.findall("./activeMods/li")
        if li.text
    ]


def discover_mods(active):
    available = defaultdict(list)

    if WORKSHOP.exists():
        for modroot in WORKSHOP.iterdir():
            if not modroot.is_dir():
                continue

            info = parse_about(modroot)
            if info:
                package_id, name = info
                available[package_id].append(
                    {
                        "package_id": package_id,
                        "name": name,
                        "root": modroot,
                        "source": modroot.name,
                    }
                )

    if LOCAL_MODS.exists():
        for modroot in LOCAL_MODS.iterdir():
            if not modroot.is_dir():
                continue

            info = parse_about(modroot)
            if info:
                package_id, name = info
                available[package_id].append(
                    {
                        "package_id": package_id,
                        "name": name,
                        "root": modroot,
                        "source": "local",
                    }
                )

    result = []

    for package_id in active:
        if (
            package_id.startswith("ludeon.")
            or package_id == "elhanko.rimworld.modtranslations"
        ):
            continue

        matches = available.get(package_id, [])

        if not matches:
            print(f"WARN: aktive Mod nicht gefunden: {package_id}")
            continue

        # Mehrere Installationen derselben packageId wären auffällig,
        # aber für die Analyse nehmen wir zunächst alle.
        result.extend(matches)

    return result


def xml_files(modroot):
    try:
        yield from modroot.rglob("*.xml")
    except OSError:
        return


def is_language_file(path):
    return "Languages" in path.parts


def is_english_keyed(path):
    parts = path.parts

    try:
        lang_i = parts.index("Languages")
    except ValueError:
        return False

    tail = parts[lang_i + 1:]

    return (
        len(tail) >= 3
        and tail[0] == "English"
        and tail[1] == "Keyed"
    )


def read_text(path):
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""


def build_indexes(mods):
    keyed_index = defaultdict(set)
    def_index = defaultdict(set)

    def_re = re.compile(
        r"<defName>\s*([^<]+?)\s*</defName>",
        re.IGNORECASE,
    )

    print("Indiziere aktive Mods ...")

    for n, mod in enumerate(mods, 1):
        label = mod["package_id"]
        root = mod["root"]

        print(f"[{n:02}/{len(mods):02}] {label}")

        for path in xml_files(root):
            text = read_text(path)
            if not text:
                continue

            # Keyed-Übersetzungen: XML-Elementnamen sind die Keys.
            if is_english_keyed(path):
                try:
                    xml_root = ET.fromstring(text)
                except ET.ParseError:
                    xml_root = None

                if xml_root is not None:
                    for elem in xml_root.iter():
                        if elem is xml_root:
                            continue
                        keyed_index[elem.tag].add(label)

            # Defs: Sprachdateien dürfen nicht als Ursprungs-Defs
            # gewertet werden.
            if not is_language_file(path):
                for match in def_re.finditer(text):
                    defname = match.group(1).strip()
                    if defname:
                        def_index[defname].add(label)

    return keyed_index, def_index


def extract_section(lines, heading_prefix):
    inside = False
    result = []

    for line in lines:
        if line.startswith("========== "):
            inside = line.startswith(
                f"========== {heading_prefix}"
            )
            continue

        if inside and line.strip():
            result.append(line.rstrip("\n"))

    return result


def parse_report():
    lines = REPORT.read_text(
        encoding="utf-8-sig",
        errors="replace",
    ).splitlines()

    keyed_lines = extract_section(
        lines,
        "Missing keyed translations ",
    )

    def_lines = extract_section(
        lines,
        "Def-injected translations missing ",
    )

    keyed = []

    for line in keyed_lines:
        try:
            key, rest = line.split(None, 1)
        except ValueError:
            continue

        source = None
        marker = " (English file: "

        if marker in rest and rest.endswith(")"):
            quoted, source_part = rest.rsplit(marker, 1)
            source = source_part[:-1]
        else:
            quoted = rest

        if quoted.startswith("'") and quoted.endswith("'"):
            english = quoted[1:-1]
        else:
            english = quoted

        keyed.append(
            (key, english, source, line)
        )

    definjected = []

    for line in def_lines:
        if ": " not in line:
            continue

        def_type, rest = line.split(": ", 1)

        try:
            def_path, quoted = rest.split(None, 1)
        except ValueError:
            continue

        defname = def_path.split(".", 1)[0]
        hint = None

        hint_marker = "' (hint:"

        if quoted.startswith("'") and hint_marker in quoted:
            english, hint = quoted[1:].rsplit(
                hint_marker,
                1,
            )
            hint = hint.rstrip(")")
        elif quoted.startswith("'") and quoted.endswith("'"):
            english = quoted[1:-1]
        else:
            english = quoted

        definjected.append(
            (
                def_type.strip(),
                defname,
                def_path,
                english,
                hint,
                line,
            )
        )

    return keyed, definjected


def resolve(candidates):
    if not candidates:
        return "unmapped", None

    if len(candidates) == 1:
        return "mapped", next(iter(candidates))

    return "ambiguous", sorted(candidates)


def main():
    if not REPORT.exists():
        raise SystemExit(
            f"Report fehlt: {REPORT}\n"
            "Symlink data/TranslationReport.txt anlegen."
        )

    active = active_package_ids()
    mods = discover_mods(active)

    mod_names = {
        mod["package_id"]: mod["name"]
        for mod in mods
    }

    keyed_index, def_index = build_indexes(mods)
    keyed, definjected = parse_report()

    stats = defaultdict(
        lambda: {
            "keyed": 0,
            "def": 0,
        }
    )

    mapped = []
    unmapped = []
    ambiguous = []

    for key, english, source, original in keyed:
        state, target = resolve(keyed_index.get(key, set()))

        if state == "mapped":
            stats[target]["keyed"] += 1

            mapped.append(
                {
                    "type": "keyed",
                    "package_id": target,
                    "key": key,
                    "english": english,
                    "source": source,
                }
            )

        elif state == "ambiguous":
            ambiguous.append(
                f"KEYED\t{key}\t{','.join(target)}\t{original}"
            )
        else:
            unmapped.append(
                f"KEYED\t{key}\t{original}"
            )

    for (
        def_type,
        defname,
        def_path,
        english,
        hint,
        original,
    ) in definjected:
        state, target = resolve(def_index.get(defname, set()))

        if state == "mapped":
            stats[target]["def"] += 1

            mapped.append(
                {
                    "type": "def",
                    "package_id": target,
                    "def_type": def_type,
                    "def_name": defname,
                    "path": def_path,
                    "english": english,
                    "hint": hint,
                }
            )

        elif state == "ambiguous":
            ambiguous.append(
                f"DEF\t{def_type}\t{defname}\t"
                f"{','.join(target)}\t{original}"
            )
        else:
            unmapped.append(
                f"DEF\t{def_type}\t{defname}\t{original}"
            )

    rows = []

    for package_id, values in stats.items():
        total = values["keyed"] + values["def"]

        rows.append(
            (
                total,
                values["keyed"],
                values["def"],
                package_id,
                mod_names.get(package_id, package_id),
            )
        )

    rows.sort(reverse=True)

    out = []

    out.append(
        f"Report: {len(keyed)} missing Keyed, "
        f"{len(definjected)} missing DefInjected"
    )
    out.append(
        f"Eindeutig zugeordnet: "
        f"{sum(x['keyed'] + x['def'] for x in stats.values())}"
    )
    out.append(f"Mehrdeutig: {len(ambiguous)}")
    out.append(f"Nicht zugeordnet: {len(unmapped)}")
    out.append("")
    out.append(
        f"{'TOTAL':>6} {'KEYED':>6} {'DEF':>6}  "
        f"{'PACKAGE-ID':45} NAME"
    )
    out.append("-" * 120)

    for total, keyed_n, def_n, package_id, name in rows:
        out.append(
            f"{total:6} {keyed_n:6} {def_n:6}  "
            f"{package_id:45} {name}"
        )

    OUT_SUMMARY.write_text(
        "\n".join(out) + "\n",
        encoding="utf-8",
    )

    OUT_UNMAPPED.write_text(
        "\n".join(unmapped) + ("\n" if unmapped else ""),
        encoding="utf-8",
    )

    OUT_AMBIGUOUS.write_text(
        "\n".join(ambiguous) + ("\n" if ambiguous else ""),
        encoding="utf-8",
    )

    OUT_MAPPED.write_text(
        "".join(
            json.dumps(
                record,
                ensure_ascii=False,
                sort_keys=True,
            ) + "\n"
            for record in mapped
        ),
        encoding="utf-8",
    )

    print()
    print("\n".join(out))

    return {"active": active, "mods": mods, "mapped": mapped,
            "keyed": keyed, "defs": definjected,
            "ambiguous": ambiguous, "unmapped": unmapped}


if __name__ == "__main__":
    main()
