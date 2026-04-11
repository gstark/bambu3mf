import json
import xml.etree.ElementTree as ET

from bambu3mf.config_writer import generate_project_config, generate_project_settings
from bambu3mf.plate import Plate


def _parse(xml_string):
    return ET.fromstring(xml_string)


def _plate_metadata(plate_el):
    return {m.get("key"): m.get("value") for m in plate_el.findall("metadata")}


class TestGenerateProjectConfig:
    def test_single_empty_plate(self):
        plates = [Plate(plate_id=1, name="Plate 1")]
        xml = generate_project_config(plates)
        root = _parse(xml)
        assert root.tag == "config"
        plate_els = root.findall("plate")
        assert len(plate_els) == 1
        meta = _plate_metadata(plate_els[0])
        assert meta["plater_id"] == "1"
        assert meta["plater_name"] == "Plate 1"

    def test_multiple_plates(self):
        plates = [Plate(plate_id=1), Plate(plate_id=2), Plate(plate_id=3)]
        xml = generate_project_config(plates)
        root = _parse(xml)
        plate_els = root.findall("plate")
        assert len(plate_els) == 3
        for i, plate_el in enumerate(plate_els, start=1):
            meta = _plate_metadata(plate_el)
            assert meta["plater_id"] == str(i)
            assert meta["plater_name"] == f"Plate {i}"

    def test_custom_plate_name(self):
        plates = [Plate(plate_id=1, name="Build Plate A")]
        xml = generate_project_config(plates)
        root = _parse(xml)
        meta = _plate_metadata(root.find("plate"))
        assert meta["plater_name"] == "Build Plate A"

    def test_empty_plate_has_no_model_instances(self):
        plates = [Plate(plate_id=1)]
        xml = generate_project_config(plates)
        root = _parse(xml)
        plate_el = root.find("plate")
        assert plate_el.findall("model_instance") == []

    def test_output_is_valid_xml(self):
        plates = [Plate(plate_id=1)]
        xml = generate_project_config(plates)
        ET.fromstring(xml)


class TestGenerateProjectConfigObjectMetadata:
    def test_object_elements_emitted(self):
        plates = [Plate(plate_id=1)]
        plates[0].objects = [
            {"object_id": 1, "instance_id": 0, "name": "cube", "extruder": 1},
        ]
        xml = generate_project_config(plates)
        root = _parse(xml)
        objects = root.findall("object")
        assert len(objects) == 1
        assert objects[0].get("id") == "1"

    def test_object_name_metadata(self):
        plates = [Plate(plate_id=1)]
        plates[0].objects = [
            {"object_id": 1, "instance_id": 0, "name": "benchy", "extruder": 1},
        ]
        xml = generate_project_config(plates)
        root = _parse(xml)
        obj_el = root.find("object")
        meta = {m.get("key"): m.get("value") for m in obj_el.findall("metadata")}
        assert meta["name"] == "benchy"

    def test_object_extruder_metadata(self):
        plates = [Plate(plate_id=1)]
        plates[0].objects = [
            {"object_id": 1, "instance_id": 0, "name": "cube", "extruder": 3},
        ]
        xml = generate_project_config(plates)
        root = _parse(xml)
        obj_el = root.find("object")
        meta = {m.get("key"): m.get("value") for m in obj_el.findall("metadata")}
        assert meta["extruder"] == "3"

    def test_default_extruder_is_1(self):
        plates = [Plate(plate_id=1)]
        plates[0].objects = [
            {"object_id": 1, "instance_id": 0, "name": "cube"},
        ]
        xml = generate_project_config(plates)
        root = _parse(xml)
        obj_el = root.find("object")
        meta = {m.get("key"): m.get("value") for m in obj_el.findall("metadata")}
        assert meta["extruder"] == "1"

    def test_objects_before_plates(self):
        plates = [Plate(plate_id=1)]
        plates[0].objects = [
            {"object_id": 1, "instance_id": 0, "name": "cube", "extruder": 1},
        ]
        xml = generate_project_config(plates)
        root = _parse(xml)
        children = list(root)
        assert children[0].tag == "object"
        assert children[1].tag == "plate"

    def test_multiple_objects_across_plates(self):
        p1 = Plate(plate_id=1)
        p1.objects = [
            {"object_id": 1, "instance_id": 0, "name": "a", "extruder": 1},
        ]
        p2 = Plate(plate_id=2)
        p2.objects = [
            {"object_id": 2, "instance_id": 0, "name": "b", "extruder": 2},
            {"object_id": 3, "instance_id": 0, "name": "c", "extruder": 1},
        ]
        xml = generate_project_config([p1, p2])
        root = _parse(xml)
        objects = root.findall("object")
        assert len(objects) == 3
        ids = [o.get("id") for o in objects]
        assert ids == ["1", "2", "3"]


class TestGenerateProjectSettings:
    def test_default_bed_size(self):
        result = json.loads(generate_project_settings(bed_size=(256, 256)))
        assert result["printable_area"] == ["0x0", "256x0", "256x256", "0x256"]

    def test_custom_bed_size(self):
        result = json.loads(generate_project_settings(bed_size=(180, 180)))
        assert result["printable_area"] == ["0x0", "180x0", "180x180", "0x180"]

    def test_asymmetric_bed_size(self):
        result = json.loads(generate_project_settings(bed_size=(256, 200)))
        assert result["printable_area"] == ["0x0", "256x0", "256x200", "0x200"]

    def test_json_has_name_and_from(self):
        result = json.loads(generate_project_settings(bed_size=(256, 256)))
        assert result["name"] == "project_settings"
        assert result["from"] == "project"

    def test_output_is_valid_json(self):
        json.loads(generate_project_settings(bed_size=(256, 256)))


class TestGenerateProjectSettingsFilaments:
    def test_single_filament(self):
        result = json.loads(generate_project_settings(
            bed_size=(256, 256),
            filaments=[{"settings_id": "PLA @BBL", "colour": "#FF0000", "type": "PLA"}],
        ))
        assert result["filament_settings_id"] == ["PLA @BBL"]
        assert result["filament_colour"] == ["#FF0000"]
        assert result["filament_type"] == ["PLA"]
        assert result["filament_diameter"] == ["1.75"]

    def test_multiple_filaments(self):
        result = json.loads(generate_project_settings(
            bed_size=(256, 256),
            filaments=[
                {"settings_id": "PLA @BBL", "colour": "#FF0000"},
                {"settings_id": "PETG @BBL", "colour": "#0000FF", "type": "PETG"},
            ],
        ))
        assert len(result["filament_settings_id"]) == 2
        assert result["filament_colour"] == ["#FF0000", "#0000FF"]
        assert result["filament_type"] == ["PLA", "PETG"]

    def test_default_colour(self):
        result = json.loads(generate_project_settings(
            bed_size=(256, 256),
            filaments=[{"settings_id": "PLA @BBL"}],
        ))
        assert result["filament_colour"] == ["#00AE42"]

    def test_default_type(self):
        result = json.loads(generate_project_settings(
            bed_size=(256, 256),
            filaments=[{"settings_id": "PLA @BBL"}],
        ))
        assert result["filament_type"] == ["PLA"]

    def test_custom_diameter(self):
        result = json.loads(generate_project_settings(
            bed_size=(256, 256),
            filaments=[{"settings_id": "PLA @BBL", "diameter": "2.85"}],
        ))
        assert result["filament_diameter"] == ["2.85"]

    def test_no_filaments_omits_keys(self):
        result = json.loads(generate_project_settings(bed_size=(256, 256)))
        assert "filament_settings_id" not in result
        assert "filament_colour" not in result
