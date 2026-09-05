#!/usr/bin/env python3

from pathlib import Path
import os
import xml.etree.ElementTree as ET

CONFIG = (
    Path.home()
    / ".config/unity3d/Ludeon Studios/RimWorld by Ludeon Studios/Config/ModsConfig.xml"
)

WORKSHOP = Path(
    "/mnt/OBS-Archive-DISK/steam/steamapps/workshop/content/294100"
)

LOCAL_MODS = Path(
    "/mnt/OBS-Archive-DISK/steam/steamapps/common/RimWorld/Mods"
)


def read_about(path):
    about = path / "About" / "About.xml"

    if not about.exists():
        return None

    try:
        root = ET.parse(about).getroot()
    except ET.ParseError:
        return None

    package_id = (root.findtext("packageId") or "").strip()
    name = (root.findtext("name") or "").strip()

    if not package_id:
        return None

    return package_id.lower(), name


def find_language_dirs(mod_path):
    result = []

    skip = {
        "Textures",
        "Graphics",
        "Sounds",
        "Assemblies",
        ".git",
    }

    for current, dirs, _files in os.walk(mod_path):
        current = Path(current)
        rel = current.relative_to(mod_path)

        # Languages sollten nicht beliebig tief im Mod liegen.
        if len(rel.parts) > 4:
            dirs[:] = []
            continue

        dirs[:] = [d for d in dirs if d not in skip]

        if current.name != "Languages":
            continue

        languages = sorted(
            p.name
            for p in current.iterdir()
            if p.is_dir()
        )

        result.append((rel, languages))

        # Unterhalb der Sprachordner brauchen wir nicht weiterlaufen.
        dirs[:] = []

    return result


config_root = ET.parse(CONFIG).getroot()

active = [
    li.text.strip()
    for li in config_root.findall("./activeMods/li")
    if li.text
]

available = {}

for mod_path in WORKSHOP.iterdir():
    if not mod_path.is_dir():
        continue

    info = read_about(mod_path)
    if info:
        package_id, name = info
        available.setdefault(package_id, []).append(
            (name, mod_path, mod_path.name)
        )

if LOCAL_MODS.exists():
    for mod_path in LOCAL_MODS.iterdir():
        if not mod_path.is_dir():
            continue

        info = read_about(mod_path)
        if info:
            package_id, name = info
            available.setdefault(package_id, []).append(
                (name, mod_path, "local")
            )


print(f"Aktive Package-IDs: {len(active)}")
print()

for number, package_id in enumerate(active, 1):
    key = package_id.lower()

    print(f"{number:2}. {package_id}")

    matches = available.get(key)

    if not matches:
        if key.startswith("ludeon."):
            print("    [RimWorld/Core/DLC]")
        else:
            print("    [nicht gefunden]")
        print()
        continue

    for name, mod_path, source in matches:
        print(f"    Name:   {name}")
        print(f"    Quelle: {source}")

        language_dirs = find_language_dirs(mod_path)

        if not language_dirs:
            print("    Languages: keine")
        else:
            for rel, languages in language_dirs:
                print(f"    {rel}:")
                for language in languages:
                    print(f"      - {language}")

    print()
