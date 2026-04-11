"""Serializers for BambuStudio 3MF config files.

Two config files are written into the 3MF archive:

``Metadata/project_settings.config`` (JSON)
    Project-level settings: bed geometry, printer preset, and filament slots.
    BambuStudio uses ``filament_colour`` from this file to determine the
    filament count when loading plate data — if it is missing, the app
    crashes with a null-pointer dereference (PartPlate.cpp:6544 calls
    ``config_loaded.option<ConfigOptionStrings>("filament_colour")->size()``
    without a null check).

``Metadata/model_settings.config`` (XML)
    Per-object metadata (name, extruder assignment) and plate-to-object
    mappings.  The ``<object>`` elements must appear *before* ``<plate>``
    elements.  Extruder values are 1-indexed and correspond to positions
    in the ``filament_settings_id`` / ``filament_colour`` arrays.

    Note: BambuStudio does NOT use the plate→object mapping here for
    spatial assignment — it uses bounding-box intersection instead.
    The mapping is used for metadata like identify_id and loaded_id.
"""

import json

import xml.etree.ElementTree as ET


def generate_project_config(plates):
    """Generate ``model_settings.config`` XML from a list of Plates.

    Emits ``<object>`` elements with name and extruder metadata for each
    object across all plates, followed by ``<plate>`` elements with
    ``<model_instance>`` children.

    Object elements must come before plate elements — BambuStudio's XML
    parser (``_handle_start_config_metadata`` in bbs_3mf.cpp:4358) uses
    ``m_curr_config.object_id`` to route metadata, and this is only set
    after seeing an ``<object>`` start tag.
    """
    root = ET.Element("config")
    for plate in plates:
        for obj in plate.objects:
            extruder = str(obj.get("extruder", 1))
            obj_el = ET.SubElement(root, "object")
            obj_el.set("id", str(obj["object_id"]))
            _add_metadata(obj_el, "name", obj.get("name", "Object"))
            _add_metadata(obj_el, "extruder", extruder)
        plate_el = ET.SubElement(root, "plate")
        _add_metadata(plate_el, "plater_id", str(plate.plate_id))
        _add_metadata(plate_el, "plater_name", plate.name)
        for obj in plate.objects:
            inst_el = ET.SubElement(plate_el, "model_instance")
            _add_metadata(inst_el, "object_id", str(obj["object_id"]))
            _add_metadata(inst_el, "instance_id", str(obj["instance_id"]))
            _add_metadata(inst_el, "identify_id", str(obj["object_id"]))
    return ET.tostring(root, encoding="unicode")


DEFAULT_FILAMENT_COLOUR = "#00AE42"


def generate_project_settings(*, bed_size, printer_settings_id="", filaments=None):
    """Generate ``project_settings.config`` JSON.

    Args:
        bed_size: ``(width, height)`` in mm.  Serialized as ``printable_area``
            rectangle corners: ``["0x0", "{w}x0", "{w}x{h}", "0x{h}"]``.
        printer_settings_id: System preset name string.
        filaments: List of dicts with optional keys ``settings_id``,
            ``colour`` (hex string, default ``#00AE42``),
            ``type`` (default ``"PLA"``), ``diameter`` (default ``"1.75"``).

    All filament arrays must have the same length — BambuStudio indexes
    them by extruder number (0-based internally, 1-based in user-facing UI).
    """
    w, h = bed_size
    settings = {
        "name": "project_settings",
        "from": "project",
        "printable_area": ["0x0", f"{w}x0", f"{w}x{h}", f"0x{h}"],
    }
    if printer_settings_id:
        settings["printer_settings_id"] = printer_settings_id
    if filaments:
        settings["filament_settings_id"] = [
            f.get("settings_id", "") for f in filaments
        ]
        settings["filament_diameter"] = [
            f.get("diameter", "1.75") for f in filaments
        ]
        settings["filament_colour"] = [
            f.get("colour", DEFAULT_FILAMENT_COLOUR) for f in filaments
        ]
        settings["filament_type"] = [
            f.get("type", "PLA") for f in filaments
        ]
    return json.dumps(settings, indent=4)


def _add_metadata(parent, key, value):
    """Append a ``<metadata key="..." value="..."/>`` child element."""
    meta = ET.SubElement(parent, "metadata")
    meta.set("key", key)
    meta.set("value", value)
