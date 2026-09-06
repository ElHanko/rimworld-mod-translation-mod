"""RimWorld 1.6 source Def resolver (including News definitions)."""
import re
import xml.etree.ElementTree as ET


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

        if (
            "Defs" not in parts
            and "News" not in parts
        ):
            continue

        old_version = any(
            _VERSION_DIR.match(part)
            and part != "1.6"
            for part in parts
        )

        if old_version:
            continue

        yield path


def current_patch_xml_files(mod_root):
    """Liefert Patch-Dateien für den aktuellen 1.6-Stand."""

    for path in mod_root.rglob("*.xml"):
        try:
            rel = path.relative_to(mod_root)
        except ValueError:
            continue

        parts = rel.parts

        if (
            "Patches" not in parts
            or "Languages" in parts
            or "About" in parts
        ):
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

    # Manche Mods erzeugen Defs erst mit PatchOperationAdd.
    # Nur Ergänzungen direkt unter <Defs> gelten hier als Def-Quelle.
    for path in current_patch_xml_files(mod_root):
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError:
            continue

        for operation in root.iter():
            if operation.attrib.get("Class") != "PatchOperationAdd":
                continue

            xpath = operation.find("xpath")
            value = operation.find("value")

            if (
                xpath is None
                or (xpath.text or "").strip() != "Defs"
                or value is None
            ):
                continue

            for element in value:
                defname_node = element.find("defName")

                if (
                    defname_node is None
                    or not defname_node.text
                ):
                    continue

                defname = defname_node.text.strip()
                tag = element.tag

                if "}" in tag:
                    tag = tag.rsplit("}", 1)[1]

                result.setdefault(
                    defname,
                    set(),
                ).add(tag)

    return result
