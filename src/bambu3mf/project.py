"""Core project class that orchestrates 3MF file creation.

A BambuStudio 3MF archive contains:

    3D/3dmodel.model              Mesh geometry + BambuStudio XML namespace/metadata
    Metadata/project_settings.config   JSON with printer, filament, and bed config
    Metadata/model_settings.config     XML with per-object metadata and plate layout
    [Content_Types].xml           Standard 3MF boilerplate
    _rels/.rels                   Standard 3MF boilerplate

BambuStudio compatibility notes (discovered empirically):

* The ``Application`` metadata must match the installed BambuStudio version
  exactly, otherwise a "Newer 3mf version" warning appears.  The version
  format is ``BambuStudio-MM.mm.PP.BB`` and is parsed by a custom semver
  library that packs the 4th component into ``patch`` via ``patch*100+build``
  (see ``src/semver/semver.c:202``).

* ``project_settings.config`` must include ``filament_colour`` when plates
  are present.  BambuStudio dereferences this without a null check in
  ``PartPlateList::load_from_3mf_structure`` (PartPlate.cpp:6544), causing
  a SIGSEGV crash if it is missing.

* ``printer_settings_id`` and ``filament_settings_id`` must reference known
  system preset names (e.g. "Bambu Lab P1P 0.4 nozzle"), otherwise a
  "Customized Preset" warning dialog appears.

* The BambuStudio CLI (``--info``, ``--slice``) needs complete settings in
  ``project_settings.config``.  It segfaults on a file that holds only preset
  names.  :mod:`bambu3mf.presets` expands the names from the system presets
  of an installed BambuStudio.

* BambuStudio assigns objects to plates by **spatial intersection**, not by
  the plate→object mapping in ``model_settings.config``.  Objects must be
  physically positioned within their target plate's coordinate region.
  See :mod:`bambu3mf.plate` for the grid layout algorithm.
"""

import re
import warnings
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import lib3mf

from bambu3mf.config_writer import generate_project_config, generate_project_settings
from bambu3mf.plate import Plate
from bambu3mf.presets import PresetLibrary, PresetNotFound, find_profiles_dir

BAMBU_NAMESPACE = 'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021"'
BAMBU_3MF_VERSION = "1"
DEFAULT_BED_SIZE = (256, 256)

_FALLBACK_VERSION = "02.05.00.66"
_VERSION_INC_PATH = Path(__file__).resolve().parents[4] / "version.inc"


def _parse_version_inc(path):
    """Extract SLIC3R_VERSION from a CMake version.inc file."""
    try:
        text = Path(path).read_text()
    except OSError:
        return None
    match = re.search(r'set\(SLIC3R_VERSION\s+"([^"]+)"\)', text)
    return match.group(1) if match else None


BAMBU_APPLICATION = "BambuStudio-{}".format(
    _parse_version_inc(_VERSION_INC_PATH) or _FALLBACK_VERSION
)


class BambuProject:
    """A 3MF project that can be opened in BambuStudio.

    Args:
        bed_size: Print bed dimensions as (width, height) in mm.
            Defaults to the ``printable_area`` of the printer preset.  If
            the preset is not available, defaults to (256, 256) for P1/X1
            series printers.
        app_version: Override the Application metadata string.
            Must match the target BambuStudio version to avoid warnings.
        description: Optional 3MF Description metadata text.
            May contain HTML-formatted content; it is XML-escaped before
            being stored in ``3D/3dmodel.model``.
        printer_settings_id: System preset name for the printer,
            e.g. ``"Bambu Lab P1P 0.4 nozzle"``.  Must match a preset
            known to BambuStudio to avoid the "Customized Preset" dialog.
        filaments: List of filament dicts, each with optional keys:
            ``settings_id``, ``colour`` (hex), ``type``, ``diameter``.
            Determines the filament slots available for extruder assignment.
        filament_settings_id: Legacy shorthand — list of preset name strings.
            Converted to filaments dicts internally.  Ignored if ``filaments``
            is also provided.
        profiles_dir: BambuStudio profile folder (``resources/profiles``).
            Defaults to the folder of an installed BambuStudio.  When
            ``printer_settings_id`` is set and the folder has the presets,
            ``save`` writes the complete settings that the BambuStudio CLI
            needs.  Otherwise it writes only the preset names, which the
            GUI can open and the CLI cannot.
    """

    def __init__(self, *, bed_size=None, app_version=None,
                 description=None, printer_settings_id="", print_settings_id="",
                 filament_settings_id=None, filaments=None, profiles_dir=None):
        self.app_version = app_version or BAMBU_APPLICATION
        self.description = description
        self.printer_settings_id = printer_settings_id
        self.print_settings_id = print_settings_id
        if filaments:
            self.filaments = filaments
            self.filament_settings_id = filament_settings_id
        elif filament_settings_id:
            self.filaments = [{"settings_id": s} for s in filament_settings_id]
            self.filament_settings_id = filament_settings_id
        else:
            self.filaments = None
            self.filament_settings_id = None
        self.profiles_dir = profiles_dir
        self.bed_size = bed_size or self._preset_bed_size() or DEFAULT_BED_SIZE
        self.plates = []
        self._wrapper = lib3mf.Wrapper()
        self._model = self._wrapper.CreateModel()

    def add_plate(self, *, name=None):
        """Create a new plate and return it.

        Plates are 1-indexed.  Each plate occupies a distinct spatial region
        so BambuStudio can assign objects by intersection.
        """
        plate_id = len(self.plates) + 1
        plate = Plate(plate_id, name=name, project=self)
        self.plates.append(plate)
        return plate

    def save(self, path):
        """Write the project to a 3MF file at *path*.

        The save process:
        1. lib3mf writes the base 3MF (geometry, build items).
        2. BambuStudio namespace + metadata are injected into the model XML.
        3. ``project_settings.config`` (JSON) is appended with printer/filament config.
        4. ``model_settings.config`` (XML) is appended with per-object metadata
           and plate layout (only when plates exist).
        """
        for plate in self.plates:
            plate._apply_plate_offsets()
        writer = self._model.QueryWriter("3mf")
        writer.WriteToFile(path)
        self._inject_bambu_metadata(path)
        self._inject_project_settings(path)
        if self.plates:
            self._inject_model_config(path)

    def _inject_bambu_metadata(self, path):
        """Rewrite the model XML to add BambuStudio namespace and metadata.

        Adds the BambuStudio XML namespace to ``<model>`` and inserts
        ``BambuStudio:3mfVersion`` and ``Application`` metadata elements
        before ``<resources>``.  This is done via regex substitution on the
        XML text because lib3mf has no API for custom namespaces.
        """
        metadata_lines = [
            f'\t<metadata name="BambuStudio:3mfVersion">{escape(BAMBU_3MF_VERSION)}</metadata>',
            f'\t<metadata name="Application">{escape(self.app_version)}</metadata>',
        ]
        if self.description is not None:
            metadata_lines.append(
                f'\t<metadata name="Description">{escape(self.description)}</metadata>'
            )
        metadata_xml = "\n".join(metadata_lines) + "\n"
        with zipfile.ZipFile(path, "r") as zin:
            names = zin.namelist()
            contents = {}
            for name in names:
                data = zin.read(name)
                if name == "3D/3dmodel.model":
                    text = data.decode("utf-8")
                    text = re.sub(
                        r"(<model\b)",
                        rf"\1 {BAMBU_NAMESPACE}",
                        text,
                        count=1,
                    )
                    text = re.sub(
                        r"(<resources)",
                        metadata_xml + r"\1",
                        text,
                        count=1,
                    )
                    data = text.encode("utf-8")
                contents[name] = data

        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zout:
            for name in names:
                zout.writestr(name, contents[name])

    def _inject_project_settings(self, path):
        """Append ``Metadata/project_settings.config`` (JSON) to the archive."""
        settings_json = generate_project_settings(
            bed_size=self.bed_size,
            printer_settings_id=self.printer_settings_id,
            print_settings_id=self.print_settings_id,
            filaments=self.filaments,
            preset_settings=self._preset_settings(),
        )
        with zipfile.ZipFile(path, "a", zipfile.ZIP_DEFLATED) as z:
            z.writestr("Metadata/project_settings.config", settings_json)

    def _preset_library(self):
        """Return the presets for the printer of this project, or ``None``."""
        profiles_dir = self.profiles_dir or find_profiles_dir()
        if not self.printer_settings_id or profiles_dir is None:
            return None
        return PresetLibrary(profiles_dir)

    def _preset_bed_size(self):
        """Return the bed size of the printer preset, or ``None``.

        ``printable_area`` is a list of ``"XxY"`` corner points.
        """
        library = self._preset_library()
        if library is None:
            return None
        try:
            machine = library.resolve("machine", self.printer_settings_id)
        except PresetNotFound:
            return None  # save() gives the warning
        corners = [
            [float(n) for n in corner.split("x")]
            for corner in machine["printable_area"]
        ]
        return tuple(
            int(size) if size.is_integer() else size
            for size in (max(axis) - min(axis) for axis in zip(*corners))
        )

    def _preset_settings(self):
        """Return the complete settings of the named presets, or ``None``."""
        library = self._preset_library()
        if library is None:
            return None
        try:
            return library.project_settings(
                self.printer_settings_id,
                self.print_settings_id,
                [f.get("settings_id") for f in self.filaments or []],
            )
        except PresetNotFound as error:
            warnings.warn(
                f"{error.args[0]}. The file has only preset names, "
                "so the BambuStudio CLI cannot load it.",
                stacklevel=3,
            )
            return None

    def _inject_model_config(self, path):
        """Append ``Metadata/model_settings.config`` (XML) to the archive."""
        config_xml = generate_project_config(self.plates)
        with zipfile.ZipFile(path, "a", zipfile.ZIP_DEFLATED) as z:
            z.writestr("Metadata/model_settings.config", config_xml)
