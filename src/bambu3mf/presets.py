"""Expand BambuStudio system preset names into complete settings.

A ``project_settings.config`` that holds only preset names opens in the
BambuStudio GUI, because the GUI looks the presets up by name.  The CLI does
not.  ``BambuStudio --info`` and ``--slice`` read keys such as
``nozzle_diameter`` and ``printable_height`` from the file without a null
check (``CLI::run`` in BambuStudio.cpp) and segfault when they are missing.

This module reads the system presets that ship with BambuStudio and flattens
them into the complete settings that the CLI needs.

Profile layout (``<BambuStudio>/resources/profiles``)::

    BBL.json                      vendor index: name -> sub_path per preset type
    BBL/machine/<name>.json       printer presets
    BBL/process/<name>.json       process presets
    BBL/filament/<name>.json      filament presets

A preset file holds only the keys that differ from its ``inherits`` parent.
It can also name ``include`` templates, which add keys such as start G-code.
"""

import json
import sys
from pathlib import Path

_INSTALL_PROFILE_DIRS = {
    "darwin": ["/Applications/BambuStudio.app/Contents/Resources/profiles"],
    "win32": [r"C:\Program Files\Bambu Studio\resources\profiles"],
}

# Keys that describe the preset file itself, not a print setting.
_PRESET_FILE_KEYS = {
    "type", "name", "inherits", "from", "setting_id", "instantiation",
    "include", "description",
}


class PresetNotFound(KeyError):
    """A preset name is not in the profile folder."""


def find_profiles_dir():
    """Return the profile folder of an installed BambuStudio, or ``None``."""
    for candidate in _INSTALL_PROFILE_DIRS.get(sys.platform, []):
        path = Path(candidate)
        if path.is_dir():
            return path
    return None


class PresetLibrary:
    """The system presets in one BambuStudio profile folder."""

    def __init__(self, profiles_dir):
        self.profiles_dir = Path(profiles_dir)
        if not self.profiles_dir.is_dir():
            raise FileNotFoundError(f"Profile folder not found: {profiles_dir}")
        self._paths = {"machine": {}, "process": {}, "filament": {}}
        for index_path in sorted(self.profiles_dir.glob("*.json")):
            index = json.loads(index_path.read_text(encoding="utf-8"))
            vendor_dir = self.profiles_dir / index_path.stem
            for kind, paths in self._paths.items():
                for entry in index.get(f"{kind}_list", []):
                    paths.setdefault(entry["name"], vendor_dir / entry["sub_path"])

    def resolve(self, kind, name):
        """Return preset *name* with its parents and templates merged in.

        *kind* is ``"machine"``, ``"process"``, or ``"filament"``.
        """
        try:
            path = self._paths[kind][name]
        except KeyError:
            raise PresetNotFound(
                f"{kind} preset {name!r} is not in {self.profiles_dir}"
            ) from None
        preset = json.loads(path.read_text(encoding="utf-8"))
        merged = self.resolve(kind, preset["inherits"]) if preset.get("inherits") else {}
        for template in preset.get("include", []):
            merged.update(self.resolve(kind, template))
        merged.update(preset)
        return merged

    def project_settings(self, printer, process=None, filaments=None):
        """Return the complete settings for a printer, process, and filaments.

        Args:
            printer: Printer preset name.
            process: Process preset name.  Defaults to the
                ``default_print_profile`` of the printer.
            filaments: List of filament preset names.  A ``None`` entry, or
                no list, gives the ``default_filament_profile`` of the printer.

        Raises:
            PresetNotFound: A preset name is not in the profile folder.
        """
        machine = self.resolve("machine", printer)
        process = process or machine["default_print_profile"]
        default_filaments = machine["default_filament_profile"]
        filaments = [f or default_filaments[0] for f in filaments or default_filaments]
        process_preset = self.resolve("process", process)

        settings = _settings_of(process_preset)
        settings["print_compatible_printers"] = settings.pop("compatible_printers", [])
        settings.update(
            _merge_filaments([self.resolve("filament", f) for f in filaments])
        )
        settings.update(_settings_of(machine))
        settings["printer_settings_id"] = printer
        settings["print_settings_id"] = process
        settings["filament_settings_id"] = list(filaments)
        return settings


def _settings_of(preset):
    return {k: v for k, v in preset.items() if k not in _PRESET_FILE_KEYS}


def _merge_filaments(presets):
    """Join the per-filament presets into project-level arrays.

    BambuStudio stores each filament setting as one array for all filaments.
    A filament can have more than one value per setting, one for each extruder
    variant.  ``filament_self_index`` gives the 1-based filament of each value.
    """
    filaments = [_settings_of(p) for p in presets]
    merged = {}
    for key in dict.fromkeys(k for f in filaments for k in f):
        fallback = next(f[key] for f in filaments if key in f)
        if isinstance(fallback, list):
            merged[key] = [v for f in filaments for v in f.get(key, fallback)]
        else:
            merged[key] = fallback
    merged.pop("compatible_printers", None)
    merged.pop("filament_id", None)
    merged["filament_ids"] = [f.get("filament_id", "") for f in filaments]
    merged["filament_self_index"] = [
        str(index)
        for index, f in enumerate(filaments, start=1)
        for _ in f.get("filament_extruder_variant", [""])
    ]
    return merged
