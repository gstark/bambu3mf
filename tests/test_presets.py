import json
import shutil
import subprocess
import warnings
import zipfile
from pathlib import Path

import pytest

from bambu3mf import BambuProject
from bambu3mf.presets import PresetLibrary, PresetNotFound, find_profiles_dir

FIXTURES = Path(__file__).parent / "fixtures"
BAMBU_STUDIO = "/Applications/BambuStudio.app/Contents/MacOS/BambuStudio"

PRESETS = {
    "machine": {
        "machine_common": {
            "printable_height": "250",
            "nozzle_diameter": ["0.4"],
            "printable_area": ["0x0", "180x0", "180x180", "0x180"],
        },
        "start_gcode": {"machine_start_gcode": "G28"},
        "Printer A": {
            "inherits": "machine_common",
            "include": ["start_gcode"],
            "nozzle_diameter": ["0.6"],
            "default_print_profile": "Process A",
            "default_filament_profile": ["PLA A"],
        },
    },
    "process": {
        "process_common": {"layer_height": "0.2", "wall_loops": "2"},
        "Process A": {
            "inherits": "process_common",
            "wall_loops": "3",
            "compatible_printers": ["Printer A"],
        },
        "Process B": {"inherits": "process_common", "layer_height": "0.1"},
    },
    "filament": {
        "filament_common": {
            "filament_type": ["PLA"],
            "filament_diameter": ["1.75"],
            "nozzle_temperature": ["220", "220"],
            "filament_extruder_variant": ["Standard", "High Flow"],
        },
        "PLA A": {"inherits": "filament_common", "filament_id": "GFA00"},
        "PETG A": {
            "inherits": "filament_common",
            "filament_id": "GFG00",
            "filament_type": ["PETG"],
            "nozzle_temperature": ["255", "260"],
            "compatible_printers": ["Printer A"],
        },
    },
}


@pytest.fixture
def profiles_dir(tmp_path):
    index = {}
    for kind, presets in PRESETS.items():
        (tmp_path / "Vendor" / kind).mkdir(parents=True)
        index[f"{kind}_list"] = [
            {"name": name, "sub_path": f"{kind}/{name}.json"} for name in presets
        ]
        for name, preset in presets.items():
            path = tmp_path / "Vendor" / kind / f"{name}.json"
            path.write_text(json.dumps({"type": kind, "name": name, **preset}))
    (tmp_path / "Vendor.json").write_text(json.dumps(index))
    (tmp_path / "blacklist.json").write_text("{}")
    return tmp_path


def _saved_settings(project, tmp_path):
    out = tmp_path / "out.3mf"
    project.save(str(out))
    with zipfile.ZipFile(out) as z:
        return json.loads(z.read("Metadata/project_settings.config"))


class TestResolve:
    def test_child_overrides_parent(self, profiles_dir):
        machine = PresetLibrary(profiles_dir).resolve("machine", "Printer A")
        assert machine["nozzle_diameter"] == ["0.6"]
        assert machine["printable_height"] == "250"

    def test_include_template_is_merged(self, profiles_dir):
        machine = PresetLibrary(profiles_dir).resolve("machine", "Printer A")
        assert machine["machine_start_gcode"] == "G28"

    def test_unknown_preset(self, profiles_dir):
        with pytest.raises(PresetNotFound, match="Printer Z"):
            PresetLibrary(profiles_dir).resolve("machine", "Printer Z")

    def test_missing_folder(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            PresetLibrary(tmp_path / "nope")


class TestProjectSettings:
    def test_merges_all_three_preset_types(self, profiles_dir):
        s = PresetLibrary(profiles_dir).project_settings(
            "Printer A", "Process B", ["PLA A"])
        assert s["nozzle_diameter"] == ["0.6"]
        assert s["layer_height"] == "0.1"
        assert s["filament_type"] == ["PLA"]
        assert s["printer_settings_id"] == "Printer A"
        assert s["print_settings_id"] == "Process B"
        assert s["filament_settings_id"] == ["PLA A"]

    def test_defaults_come_from_printer(self, profiles_dir):
        s = PresetLibrary(profiles_dir).project_settings("Printer A")
        assert s["print_settings_id"] == "Process A"
        assert s["filament_settings_id"] == ["PLA A"]
        assert s["wall_loops"] == "3"

    def test_preset_file_keys_are_dropped(self, profiles_dir):
        s = PresetLibrary(profiles_dir).project_settings("Printer A")
        assert not {"type", "name", "inherits", "include"} & set(s)

    def test_compatible_printers_renamed_for_process(self, profiles_dir):
        s = PresetLibrary(profiles_dir).project_settings(
            "Printer A", filaments=["PETG A"])
        assert s["print_compatible_printers"] == ["Printer A"]
        assert "compatible_printers" not in s

    def test_filament_arrays_are_joined(self, profiles_dir):
        s = PresetLibrary(profiles_dir).project_settings(
            "Printer A", filaments=["PLA A", "PETG A"])
        assert s["filament_type"] == ["PLA", "PETG"]
        assert s["nozzle_temperature"] == ["220", "220", "255", "260"]
        assert s["filament_self_index"] == ["1", "1", "2", "2"]
        assert s["filament_ids"] == ["GFA00", "GFG00"]

    def test_none_filament_uses_printer_default(self, profiles_dir):
        s = PresetLibrary(profiles_dir).project_settings(
            "Printer A", filaments=[None, "PETG A"])
        assert s["filament_settings_id"] == ["PLA A", "PETG A"]


class TestProjectSave:
    def test_save_writes_complete_settings(self, profiles_dir, tmp_path):
        project = BambuProject(
            printer_settings_id="Printer A",
            filaments=[
                {"settings_id": "PLA A", "colour": "#FF0000"},
                {"settings_id": "PETG A", "colour": "#0000FF"},
            ],
            profiles_dir=profiles_dir,
        )
        s = _saved_settings(project, tmp_path)
        assert s["name"] == "project_settings"
        assert s["printable_height"] == "250"
        assert s["print_settings_id"] == "Process A"
        assert s["filament_colour"] == ["#FF0000", "#0000FF"]
        assert s["filament_type"] == ["PLA", "PETG"]
        assert s["printable_area"] == ["0x0", "180x0", "180x180", "0x180"]

    def test_bed_size_defaults_to_printer_preset(self, profiles_dir):
        project = BambuProject(
            printer_settings_id="Printer A", profiles_dir=profiles_dir)
        assert project.bed_size == (180, 180)

    def test_explicit_bed_size_wins(self, profiles_dir, tmp_path):
        project = BambuProject(
            bed_size=(200, 150),
            printer_settings_id="Printer A", profiles_dir=profiles_dir)
        assert project.bed_size == (200, 150)
        s = _saved_settings(project, tmp_path)
        assert s["printable_area"] == ["0x0", "200x0", "200x150", "0x150"]

    def test_unknown_printer_uses_default_bed_size(self, profiles_dir):
        project = BambuProject(
            printer_settings_id="Printer Z", profiles_dir=profiles_dir)
        assert project.bed_size == (256, 256)

    def test_filament_dict_overrides_preset_type(self, profiles_dir, tmp_path):
        project = BambuProject(
            printer_settings_id="Printer A",
            filaments=[{"settings_id": "PLA A", "type": "PLA-CF"}],
            profiles_dir=profiles_dir,
        )
        assert _saved_settings(project, tmp_path)["filament_type"] == ["PLA-CF"]

    def test_no_filaments_uses_printer_default(self, profiles_dir, tmp_path):
        project = BambuProject(
            printer_settings_id="Printer A", profiles_dir=profiles_dir)
        s = _saved_settings(project, tmp_path)
        assert s["filament_settings_id"] == ["PLA A"]
        assert s["filament_colour"] == ["#00AE42"]

    def test_unknown_preset_warns_and_writes_names_only(self, profiles_dir, tmp_path):
        project = BambuProject(
            printer_settings_id="Printer Z", profiles_dir=profiles_dir)
        with pytest.warns(UserWarning, match="Printer Z"):
            s = _saved_settings(project, tmp_path)
        assert s["printer_settings_id"] == "Printer Z"
        assert "printable_height" not in s

    def test_no_printer_writes_no_preset_settings(self, profiles_dir, tmp_path):
        project = BambuProject(profiles_dir=profiles_dir)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            s = _saved_settings(project, tmp_path)
        assert "printable_height" not in s


@pytest.mark.skipif(
    find_profiles_dir() is None or not shutil.which(BAMBU_STUDIO),
    reason="BambuStudio is not installed",
)
class TestBambuStudioCli:
    def test_info_loads_a_two_plate_project(self, tmp_path):
        project = BambuProject(
            printer_settings_id="Bambu Lab P1P 0.4 nozzle",
            filaments=[
                {"settings_id": "Bambu PLA Basic @BBL P1P", "colour": "#FF0000"},
                {"settings_id": "Bambu PLA Basic @BBL P1P", "colour": "#0000FF"},
            ],
        )
        project.add_plate(name="one").add_stl(str(FIXTURES / "cube.stl"), extruder=1)
        project.add_plate(name="two").add_stl(str(FIXTURES / "cube.stl"), extruder=2)
        out = tmp_path / "out.3mf"
        project.save(str(out))
        result = subprocess.run(
            [BAMBU_STUDIO, "--info", str(out)],
            cwd=tmp_path, capture_output=True, timeout=120,
        )
        assert result.returncode == 0
