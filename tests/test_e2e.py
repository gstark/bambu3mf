"""End-to-end integration tests for multi-plate 3MF project creation.

Exercises the full public API: BambuProject, Plate, add_stl, save.
Verifies ZIP structure, config XML, and mesh resource mappings.
"""

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

from bambu3mf import BambuProject

FIXTURE_DIR = Path(__file__).parent / "fixtures"
CUBE_STL = str(FIXTURE_DIR / "cube.stl")

EXPECTED_ZIP_ENTRIES = {"3D/3dmodel.model", "[Content_Types].xml", "_rels/.rels"}


def _parse_config(zip_path):
    with zipfile.ZipFile(zip_path) as z:
        return ET.fromstring(z.read("Metadata/model_settings.config"))


def _plate_metadata(plate_el):
    return {
        m.get("key"): m.get("value")
        for m in plate_el.findall("metadata")
    }


def _instance_metadata(plate_el):
    return [
        {m.get("key"): m.get("value") for m in inst.findall("metadata")}
        for inst in plate_el.findall("model_instance")
    ]


class TestEmptyProjectSave:
    def test_empty_project_saves_without_error(self, tmp_path):
        out = tmp_path / "empty.3mf"
        BambuProject().save(str(out))
        assert out.exists()
        assert zipfile.is_zipfile(out)

    def test_empty_project_has_standard_entries(self, tmp_path):
        out = tmp_path / "empty.3mf"
        BambuProject().save(str(out))
        with zipfile.ZipFile(out) as z:
            assert EXPECTED_ZIP_ENTRIES.issubset(set(z.namelist()))

    def test_empty_project_no_config(self, tmp_path):
        out = tmp_path / "empty.3mf"
        BambuProject().save(str(out))
        with zipfile.ZipFile(out) as z:
            assert "Metadata/model_settings.config" not in z.namelist()


class TestMixedEmptyAndPopulatedPlates:
    def test_empty_plate_saves(self, tmp_path):
        out = tmp_path / "mixed.3mf"
        project = BambuProject()
        project.add_plate(name="Empty")
        project.save(str(out))
        root = _parse_config(str(out))
        plates = root.findall("plate")
        assert len(plates) == 1
        assert _instance_metadata(plates[0]) == []

    def test_mixed_empty_and_populated(self, tmp_path):
        out = tmp_path / "mixed.3mf"
        project = BambuProject()
        project.add_plate(name="Empty Plate")
        p2 = project.add_plate(name="Has Object")
        p2.add_stl(CUBE_STL)
        project.add_plate(name="Also Empty")
        project.save(str(out))

        root = _parse_config(str(out))
        plates = root.findall("plate")
        assert len(plates) == 3
        assert _instance_metadata(plates[0]) == []
        assert len(_instance_metadata(plates[1])) == 1
        assert _instance_metadata(plates[2]) == []


class TestMultiPlateEndToEnd:
    """Full integration: 3+ plates, multiple STLs, mix of positioning."""

    @pytest.fixture()
    def saved_project(self, tmp_path):
        out = tmp_path / "multi.3mf"
        project = BambuProject()

        p1 = project.add_plate(name="Plate 1")
        p1.add_stl(CUBE_STL)
        p1.add_stl(CUBE_STL, position=(50, 50))

        p2 = project.add_plate(name="Plate 2")
        p2.add_stl(CUBE_STL, position=(0, 0))

        p3 = project.add_plate()  # auto-named "Plate 3"
        p3.add_stl(CUBE_STL)
        p3.add_stl(CUBE_STL, position=(100, 100))
        p3.add_stl(CUBE_STL, position=(200, 200))

        project.save(str(out))
        return str(out)

    def test_zip_contains_standard_entries(self, saved_project):
        with zipfile.ZipFile(saved_project) as z:
            names = set(z.namelist())
            assert EXPECTED_ZIP_ENTRIES.issubset(names)

    def test_zip_contains_config(self, saved_project):
        with zipfile.ZipFile(saved_project) as z:
            assert "Metadata/model_settings.config" in z.namelist()

    def test_model_has_bambu_namespace(self, saved_project):
        with zipfile.ZipFile(saved_project) as z:
            xml_text = z.read("3D/3dmodel.model").decode()
        assert 'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021"' in xml_text

    def test_config_has_three_plates(self, saved_project):
        root = _parse_config(saved_project)
        assert len(root.findall("plate")) == 3

    def test_plate_ids_are_sequential(self, saved_project):
        root = _parse_config(saved_project)
        ids = [
            _plate_metadata(p).get("plater_id")
            for p in root.findall("plate")
        ]
        assert ids == ["1", "2", "3"]

    def test_plate_names(self, saved_project):
        root = _parse_config(saved_project)
        names = [
            _plate_metadata(p).get("plater_name")
            for p in root.findall("plate")
        ]
        assert names == ["Plate 1", "Plate 2", "Plate 3"]

    def test_plate1_has_two_instances(self, saved_project):
        root = _parse_config(saved_project)
        instances = _instance_metadata(root.findall("plate")[0])
        assert len(instances) == 2

    def test_plate2_has_one_instance(self, saved_project):
        root = _parse_config(saved_project)
        instances = _instance_metadata(root.findall("plate")[1])
        assert len(instances) == 1

    def test_plate3_has_three_instances(self, saved_project):
        root = _parse_config(saved_project)
        instances = _instance_metadata(root.findall("plate")[2])
        assert len(instances) == 3

    def test_each_instance_has_required_keys(self, saved_project):
        root = _parse_config(saved_project)
        required = {"object_id", "instance_id", "identify_id"}
        for plate_el in root.findall("plate"):
            for inst in _instance_metadata(plate_el):
                assert required.issubset(inst.keys())

    def test_object_ids_are_unique_across_plates(self, saved_project):
        root = _parse_config(saved_project)
        all_obj_ids = []
        for plate_el in root.findall("plate"):
            for inst in _instance_metadata(plate_el):
                all_obj_ids.append(inst["object_id"])
        assert len(all_obj_ids) == len(set(all_obj_ids))

    def test_identify_id_matches_object_id(self, saved_project):
        root = _parse_config(saved_project)
        for plate_el in root.findall("plate"):
            for inst in _instance_metadata(plate_el):
                assert inst["identify_id"] == inst["object_id"]

    def test_model_xml_has_mesh_resources(self, saved_project):
        with zipfile.ZipFile(saved_project) as z:
            xml_bytes = z.read("3D/3dmodel.model")
        root = ET.fromstring(xml_bytes)
        ns = root.tag.split("}")[0] + "}" if "}" in root.tag else ""
        resources = root.find(f"{ns}resources")
        objects = resources.findall(f"{ns}object")
        assert len(objects) == 6  # 6 STLs total


def _object_metadata(root):
    """Return list of {id, name, extruder} for each <object> in config."""
    return [
        {
            "id": obj.get("id"),
            **{m.get("key"): m.get("value") for m in obj.findall("metadata")},
        }
        for obj in root.findall("object")
    ]


class TestFilamentAssignmentEndToEnd:
    @pytest.fixture()
    def saved_project(self, tmp_path):
        out = tmp_path / "filaments.3mf"
        project = BambuProject(
            filaments=[
                {"settings_id": "PLA @BBL", "colour": "#FF0000", "type": "PLA"},
                {"settings_id": "PLA @BBL", "colour": "#0000FF", "type": "PLA"},
                {"settings_id": "PETG @BBL", "colour": "#00FF00", "type": "PETG"},
            ],
        )
        plate = project.add_plate(name="Multi-Filament")
        plate.add_stl(CUBE_STL, position=(30, 100), extruder=1)
        plate.add_stl(CUBE_STL, position=(100, 100), extruder=2)
        plate.add_stl(CUBE_STL, position=(200, 100), extruder=3)
        project.save(str(out))
        return str(out)

    def test_project_settings_has_three_filaments(self, saved_project):
        with zipfile.ZipFile(saved_project) as z:
            import json
            settings = json.loads(z.read("Metadata/project_settings.config"))
        assert len(settings["filament_settings_id"]) == 3
        assert len(settings["filament_colour"]) == 3

    def test_filament_colours(self, saved_project):
        with zipfile.ZipFile(saved_project) as z:
            import json
            settings = json.loads(z.read("Metadata/project_settings.config"))
        assert settings["filament_colour"] == ["#FF0000", "#0000FF", "#00FF00"]

    def test_filament_types(self, saved_project):
        with zipfile.ZipFile(saved_project) as z:
            import json
            settings = json.loads(z.read("Metadata/project_settings.config"))
        assert settings["filament_type"] == ["PLA", "PLA", "PETG"]

    def test_config_has_object_elements(self, saved_project):
        root = _parse_config(saved_project)
        objects = root.findall("object")
        assert len(objects) == 3

    def test_extruder_assignments(self, saved_project):
        root = _parse_config(saved_project)
        objs = _object_metadata(root)
        extruders = [o["extruder"] for o in objs]
        assert extruders == ["1", "2", "3"]

    def test_object_names_from_stl(self, saved_project):
        root = _parse_config(saved_project)
        objs = _object_metadata(root)
        assert all(o["name"] == "cube" for o in objs)

    def test_shared_extruder(self, tmp_path):
        out = tmp_path / "shared.3mf"
        project = BambuProject(
            filaments=[
                {"settings_id": "PLA @BBL", "colour": "#FF0000"},
                {"settings_id": "PLA @BBL", "colour": "#0000FF"},
            ],
        )
        plate = project.add_plate()
        plate.add_stl(CUBE_STL, position=(30, 100), extruder=1)
        plate.add_stl(CUBE_STL, position=(100, 100), extruder=2)
        plate.add_stl(CUBE_STL, position=(200, 100), extruder=1)
        project.save(str(out))
        root = _parse_config(str(out))
        objs = _object_metadata(root)
        assert [o["extruder"] for o in objs] == ["1", "2", "1"]

    def test_default_extruder_is_1(self, tmp_path):
        out = tmp_path / "default_ext.3mf"
        project = BambuProject(
            filaments=[{"settings_id": "PLA @BBL"}],
        )
        plate = project.add_plate()
        plate.add_stl(CUBE_STL)
        project.save(str(out))
        root = _parse_config(str(out))
        objs = _object_metadata(root)
        assert objs[0]["extruder"] == "1"


class TestObjectNamingEndToEnd:
    def test_mesh_name_in_model_xml(self, tmp_path):
        out = tmp_path / "named.3mf"
        project = BambuProject()
        plate = project.add_plate()
        plate.add_stl(CUBE_STL)
        project.save(str(out))
        with zipfile.ZipFile(out) as z:
            xml_text = z.read("3D/3dmodel.model").decode()
        assert 'name="cube"' in xml_text


class TestPlateGridLayout:
    def test_four_plates_2x2(self, tmp_path):
        out = tmp_path / "grid.3mf"
        project = BambuProject()
        for i in range(4):
            p = project.add_plate()
            p.add_stl(CUBE_STL)
        project.save(str(out))
        root = _parse_config(str(out))
        assert len(root.findall("plate")) == 4

    def test_three_plates_layout(self, tmp_path):
        """3 plates → 2 cols: plate 3 goes to row 1."""
        out = tmp_path / "grid3.3mf"
        project = BambuProject()
        for _ in range(3):
            p = project.add_plate()
            p.add_stl(CUBE_STL)
        project.save(str(out))
        with zipfile.ZipFile(out) as z:
            xml_bytes = z.read("3D/3dmodel.model")
        root = ET.fromstring(xml_bytes)
        ns = root.tag.split("}")[0] + "}" if "}" in root.tag else ""
        build = root.find(f"{ns}build")
        items = build.findall(f"{ns}item")
        # plate 3 (index 2) should have negative Y in transform
        transform_str = items[2].get("transform")
        parts = transform_str.split()
        ty = float(parts[-2])  # Y translation
        assert ty < 0  # below origin = second row


class TestBackwardsCompatFilamentSettingsId:
    def test_filament_settings_id_still_works(self, tmp_path):
        out = tmp_path / "compat.3mf"
        project = BambuProject(
            filament_settings_id=["Bambu PLA Basic @BBL P1P"],
        )
        project.save(str(out))
        with zipfile.ZipFile(out) as z:
            import json
            settings = json.loads(z.read("Metadata/project_settings.config"))
        assert settings["filament_settings_id"] == ["Bambu PLA Basic @BBL P1P"]
        assert settings["filament_colour"] == ["#00AE42"]

    def test_filaments_param_takes_precedence(self, tmp_path):
        out = tmp_path / "precedence.3mf"
        project = BambuProject(
            filaments=[{"settings_id": "Custom", "colour": "#123456"}],
            filament_settings_id=["Should Be Ignored"],
        )
        project.save(str(out))
        with zipfile.ZipFile(out) as z:
            import json
            settings = json.loads(z.read("Metadata/project_settings.config"))
        assert settings["filament_settings_id"] == ["Custom"]
        assert settings["filament_colour"] == ["#123456"]


class TestCustomBedSizeEndToEnd:
    def test_a1_mini_bed_size(self, tmp_path):
        out = tmp_path / "a1mini.3mf"
        project = BambuProject(bed_size=(180, 180))
        p = project.add_plate()
        p.add_stl(CUBE_STL)  # auto-centered on 180x180 bed
        project.save(str(out))
        assert zipfile.is_zipfile(out)
        root = _parse_config(str(out))
        assert len(root.findall("plate")) == 1

    def test_a1_mini_rejects_oob_position(self):
        project = BambuProject(bed_size=(180, 180))
        p = project.add_plate()
        with pytest.raises(ValueError, match="exceeds bed size"):
            p.add_stl(CUBE_STL, position=(175, 175))
