import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

from bambu3mf import BambuProject
from bambu3mf.config_writer import generate_project_config

FIXTURES = Path(__file__).parent / "fixtures"
CUBE_STL = str(FIXTURES / "cube.stl")


class TestPlateAddStl:
    def test_add_stl_adds_object_to_plate(self):
        project = BambuProject()
        plate = project.add_plate()
        plate.add_stl(CUBE_STL)
        assert len(plate.objects) == 1

    def test_add_stl_records_object_id(self):
        project = BambuProject()
        plate = project.add_plate()
        plate.add_stl(CUBE_STL)
        assert "object_id" in plate.objects[0]

    def test_add_stl_records_instance_id(self):
        project = BambuProject()
        plate = project.add_plate()
        plate.add_stl(CUBE_STL)
        assert "instance_id" in plate.objects[0]

    def test_multiple_stls_on_same_plate(self):
        project = BambuProject()
        plate = project.add_plate()
        plate.add_stl(CUBE_STL)
        plate.add_stl(CUBE_STL)
        assert len(plate.objects) == 2

    def test_multiple_stls_have_different_object_ids(self):
        project = BambuProject()
        plate = project.add_plate()
        plate.add_stl(CUBE_STL)
        plate.add_stl(CUBE_STL)
        ids = [o["object_id"] for o in plate.objects]
        assert ids[0] != ids[1]

    def test_instance_ids_are_zero(self):
        project = BambuProject()
        plate = project.add_plate()
        plate.add_stl(CUBE_STL)
        plate.add_stl(CUBE_STL)
        assert all(o["instance_id"] == 0 for o in plate.objects)

    def test_invalid_path_raises(self):
        project = BambuProject()
        plate = project.add_plate()
        with pytest.raises(FileNotFoundError):
            plate.add_stl("/no/such/file.stl")


class TestAutoCenter:
    def test_cube_centered_on_plate_origin(self):
        """Cube is 10x20x30 at origin. After centering on 256x256 bed,
        translation should place bbox center at (128, 128, z_min=0)."""
        project = BambuProject()
        plate = project.add_plate()
        plate.add_stl(CUBE_STL)
        # Check the build item transform
        it = project._model.GetBuildItems()
        it.MoveNext()
        bi = it.GetCurrent()
        t = bi.GetObjectTransform()
        # Translation is in column 3 (index 3)
        tx = t.Fields[3][0]
        ty = t.Fields[3][1]
        # Center of 10-wide object at x=128 means translate by 128-5=123
        assert tx == pytest.approx(123.0)
        # Center of 20-tall object at y=128 means translate by 128-10=118
        assert ty == pytest.approx(118.0)

    def test_custom_bed_size_centering(self):
        project = BambuProject(bed_size=(180, 180))
        plate = project.add_plate()
        plate.add_stl(CUBE_STL)
        it = project._model.GetBuildItems()
        it.MoveNext()
        bi = it.GetCurrent()
        t = bi.GetObjectTransform()
        tx = t.Fields[3][0]
        ty = t.Fields[3][1]
        # 180/2 - 10/2 = 85
        assert tx == pytest.approx(85.0)
        # 180/2 - 20/2 = 80
        assert ty == pytest.approx(80.0)


class TestConfigWithInstances:
    def test_config_xml_has_model_instance(self):
        project = BambuProject()
        plate = project.add_plate()
        plate.add_stl(CUBE_STL)
        xml = generate_project_config(project.plates)
        root = ET.fromstring(xml)
        instances = root.find("plate").findall("model_instance")
        assert len(instances) == 1

    def test_model_instance_has_object_id(self):
        project = BambuProject()
        plate = project.add_plate()
        plate.add_stl(CUBE_STL)
        xml = generate_project_config(project.plates)
        root = ET.fromstring(xml)
        inst = root.find("plate").find("model_instance")
        meta = {m.get("key"): m.get("value") for m in inst.findall("metadata")}
        assert "object_id" in meta

    def test_model_instance_has_instance_id(self):
        project = BambuProject()
        plate = project.add_plate()
        plate.add_stl(CUBE_STL)
        xml = generate_project_config(project.plates)
        root = ET.fromstring(xml)
        inst = root.find("plate").find("model_instance")
        meta = {m.get("key"): m.get("value") for m in inst.findall("metadata")}
        assert "instance_id" in meta

    def test_model_instance_has_identify_id(self):
        project = BambuProject()
        plate = project.add_plate()
        plate.add_stl(CUBE_STL)
        xml = generate_project_config(project.plates)
        root = ET.fromstring(xml)
        inst = root.find("plate").find("model_instance")
        meta = {m.get("key"): m.get("value") for m in inst.findall("metadata")}
        assert "identify_id" in meta

    def test_multi_object_plate_has_multiple_instances(self):
        project = BambuProject()
        plate = project.add_plate()
        plate.add_stl(CUBE_STL)
        plate.add_stl(CUBE_STL)
        xml = generate_project_config(project.plates)
        root = ET.fromstring(xml)
        instances = root.find("plate").findall("model_instance")
        assert len(instances) == 2


class TestEndToEndSaveWithStl:
    def test_save_with_stl_contains_model_config(self, tmp_path):
        out = tmp_path / "out.3mf"
        project = BambuProject()
        plate = project.add_plate()
        plate.add_stl(CUBE_STL)
        project.save(str(out))
        with zipfile.ZipFile(out) as z:
            assert "Metadata/model_settings.config" in z.namelist()

    def test_save_with_stl_has_mesh_in_model(self, tmp_path):
        out = tmp_path / "out.3mf"
        project = BambuProject()
        plate = project.add_plate()
        plate.add_stl(CUBE_STL)
        project.save(str(out))
        with zipfile.ZipFile(out) as z:
            model_xml = z.read("3D/3dmodel.model").decode()
        root = ET.fromstring(model_xml)
        ns = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
        objects = root.findall(".//m:object", ns)
        assert len(objects) >= 1

    def test_save_config_has_correct_object_id(self, tmp_path):
        out = tmp_path / "out.3mf"
        project = BambuProject()
        plate = project.add_plate()
        plate.add_stl(CUBE_STL)
        project.save(str(out))
        with zipfile.ZipFile(out) as z:
            config = z.read("Metadata/model_settings.config").decode()
        root = ET.fromstring(config)
        inst = root.find("plate").find("model_instance")
        meta = {m.get("key"): m.get("value") for m in inst.findall("metadata")}
        assert int(meta["object_id"]) >= 0


class TestExplicitPositioning:
    """Cube fixture: 10x20x30 at origin (0,0,0)→(10,20,30)."""

    def _get_transform(self, project):
        it = project._model.GetBuildItems()
        bi = None
        while it.MoveNext():
            bi = it.GetCurrent()
        return bi.GetObjectTransform()

    def test_explicit_position_sets_transform(self):
        project = BambuProject()
        plate = project.add_plate()
        plate.add_stl(CUBE_STL, position=(100, 100))
        t = self._get_transform(project)
        # position=(100,100) means bbox min_x at 100, so tx=100
        assert t.Fields[3][0] == pytest.approx(100.0)
        assert t.Fields[3][1] == pytest.approx(100.0)

    def test_explicit_position_zero_zero(self):
        project = BambuProject()
        plate = project.add_plate()
        plate.add_stl(CUBE_STL, position=(0, 0))
        t = self._get_transform(project)
        assert t.Fields[3][0] == pytest.approx(0.0)
        assert t.Fields[3][1] == pytest.approx(0.0)

    def test_auto_center_still_works_without_position(self):
        project = BambuProject()
        plate = project.add_plate()
        plate.add_stl(CUBE_STL)
        t = self._get_transform(project)
        # 256/2 - 10/2 = 123
        assert t.Fields[3][0] == pytest.approx(123.0)

    def test_explicit_position_with_custom_bed(self):
        project = BambuProject(bed_size=(180, 180))
        plate = project.add_plate()
        plate.add_stl(CUBE_STL, position=(50, 50))
        t = self._get_transform(project)
        assert t.Fields[3][0] == pytest.approx(50.0)
        assert t.Fields[3][1] == pytest.approx(50.0)


class TestBoundsValidation:
    """Cube fixture: 10x20x30 at origin → placed at (x,y) occupies x..x+10, y..y+20."""

    def test_object_at_edge_of_bed_passes(self):
        project = BambuProject()  # 256x256
        plate = project.add_plate()
        # Place so right edge is exactly at 256: x=246, obj width=10 → 246+10=256
        plate.add_stl(CUBE_STL, position=(246, 236))  # 236+20=256

    def test_object_exceeds_right_edge_raises(self):
        project = BambuProject()  # 256x256
        plate = project.add_plate()
        with pytest.raises(ValueError, match="bed"):
            plate.add_stl(CUBE_STL, position=(250, 100))  # 250+10=260 > 256

    def test_object_exceeds_top_edge_raises(self):
        project = BambuProject()  # 256x256
        plate = project.add_plate()
        with pytest.raises(ValueError, match="bed"):
            plate.add_stl(CUBE_STL, position=(100, 240))  # 240+20=260 > 256

    def test_negative_position_raises(self):
        project = BambuProject()
        plate = project.add_plate()
        with pytest.raises(ValueError, match="bed"):
            plate.add_stl(CUBE_STL, position=(-1, 100))

    def test_error_message_includes_bed_size(self):
        project = BambuProject(bed_size=(180, 180))
        plate = project.add_plate()
        with pytest.raises(ValueError, match="180"):
            plate.add_stl(CUBE_STL, position=(175, 0))  # 175+10=185 > 180

    def test_error_message_includes_object_bounds(self):
        project = BambuProject()
        plate = project.add_plate()
        with pytest.raises(ValueError, match="10"):
            plate.add_stl(CUBE_STL, position=(250, 0))

    def test_custom_bed_size_bounds_check(self):
        project = BambuProject(bed_size=(180, 180))
        plate = project.add_plate()
        # Fits on 180 bed: 170+10=180
        plate.add_stl(CUBE_STL, position=(170, 160))  # 160+20=180

    def test_custom_bed_size_rejects_over(self):
        project = BambuProject(bed_size=(180, 180))
        plate = project.add_plate()
        with pytest.raises(ValueError):
            plate.add_stl(CUBE_STL, position=(171, 0))  # 171+10=181 > 180

    def test_auto_center_no_bounds_error(self):
        """Auto-centering on default bed should never raise bounds error."""
        project = BambuProject()
        plate = project.add_plate()
        plate.add_stl(CUBE_STL)  # should not raise

    def test_bounds_error_leaves_model_clean(self):
        """Rejected placement must not leave orphaned mesh/build items."""
        project = BambuProject()
        plate = project.add_plate()
        with pytest.raises(ValueError):
            plate.add_stl(CUBE_STL, position=(250, 0))
        assert len(plate.objects) == 0
        # Model should have no build items or meshes
        it = project._model.GetBuildItems()
        count = 0
        while it.MoveNext():
            count += 1
        assert count == 0
