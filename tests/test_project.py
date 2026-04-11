import json
import xml.etree.ElementTree as ET
import zipfile

from bambu3mf import BambuProject


class TestBambuProjectInit:
    def test_default_bed_size(self):
        project = BambuProject()
        assert project.bed_size == (256, 256)

    def test_custom_bed_size(self):
        project = BambuProject(bed_size=(180, 180))
        assert project.bed_size == (180, 180)


class TestBambuProjectSave:
    def test_save_creates_file(self, tmp_path):
        out = tmp_path / "out.3mf"
        BambuProject().save(str(out))
        assert out.exists()

    def test_save_produces_valid_zip(self, tmp_path):
        out = tmp_path / "out.3mf"
        BambuProject().save(str(out))
        assert zipfile.is_zipfile(out)

    def test_save_contains_model(self, tmp_path):
        out = tmp_path / "out.3mf"
        BambuProject().save(str(out))
        with zipfile.ZipFile(out) as z:
            assert "3D/3dmodel.model" in z.namelist()

    def test_save_contains_content_types(self, tmp_path):
        out = tmp_path / "out.3mf"
        BambuProject().save(str(out))
        with zipfile.ZipFile(out) as z:
            assert "[Content_Types].xml" in z.namelist()

    def test_save_contains_rels(self, tmp_path):
        out = tmp_path / "out.3mf"
        BambuProject().save(str(out))
        with zipfile.ZipFile(out) as z:
            assert "_rels/.rels" in z.namelist()

    def test_model_xml_is_parseable(self, tmp_path):
        out = tmp_path / "out.3mf"
        BambuProject().save(str(out))
        with zipfile.ZipFile(out) as z:
            xml_bytes = z.read("3D/3dmodel.model")
        root = ET.fromstring(xml_bytes)
        assert root.tag.endswith("model")

    def test_model_xml_has_bambu_namespace(self, tmp_path):
        out = tmp_path / "out.3mf"
        BambuProject().save(str(out))
        with zipfile.ZipFile(out) as z:
            xml_text = z.read("3D/3dmodel.model").decode()
        assert 'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021"' in xml_text

    def test_model_xml_has_3mf_version_metadata(self, tmp_path):
        out = tmp_path / "out.3mf"
        BambuProject().save(str(out))
        with zipfile.ZipFile(out) as z:
            xml_bytes = z.read("3D/3dmodel.model")
        root = ET.fromstring(xml_bytes)
        ns = root.tag.split("}")[0] + "}" if "}" in root.tag else ""
        metadata = {
            m.get("name"): m.text
            for m in root.findall(f"{ns}metadata")
        }
        assert "BambuStudio:3mfVersion" in metadata
        assert metadata["BambuStudio:3mfVersion"] == "1"

    def test_model_xml_has_application_metadata(self, tmp_path):
        out = tmp_path / "out.3mf"
        BambuProject().save(str(out))
        with zipfile.ZipFile(out) as z:
            xml_bytes = z.read("3D/3dmodel.model")
        root = ET.fromstring(xml_bytes)
        ns = root.tag.split("}")[0] + "}" if "}" in root.tag else ""
        metadata = {
            m.get("name"): m.text
            for m in root.findall(f"{ns}metadata")
        }
        assert "Application" in metadata
        assert metadata["Application"].startswith("BambuStudio-")

    def test_save_with_custom_bed_size(self, tmp_path):
        out = tmp_path / "out.3mf"
        BambuProject(bed_size=(180, 180)).save(str(out))
        assert zipfile.is_zipfile(out)


class TestAddPlate:
    def test_add_plate_returns_plate(self):
        from bambu3mf.plate import Plate

        project = BambuProject()
        plate = project.add_plate()
        assert isinstance(plate, Plate)

    def test_add_plate_with_name(self):
        project = BambuProject()
        plate = project.add_plate(name="My Plate")
        assert plate.name == "My Plate"

    def test_add_plate_auto_names(self):
        project = BambuProject()
        p1 = project.add_plate()
        p2 = project.add_plate()
        assert p1.name == "Plate 1"
        assert p2.name == "Plate 2"

    def test_add_plate_ids_are_1_indexed(self):
        project = BambuProject()
        p1 = project.add_plate()
        p2 = project.add_plate()
        assert p1.plate_id == 1
        assert p2.plate_id == 2

    def test_plates_list(self):
        project = BambuProject()
        project.add_plate()
        project.add_plate()
        assert len(project.plates) == 2


class TestSaveWithPlates:
    def test_save_contains_model_config(self, tmp_path):
        out = tmp_path / "out.3mf"
        project = BambuProject()
        project.add_plate()
        project.save(str(out))
        with zipfile.ZipFile(out) as z:
            assert "Metadata/model_settings.config" in z.namelist()

    def test_config_xml_has_plate_elements(self, tmp_path):
        out = tmp_path / "out.3mf"
        project = BambuProject()
        project.add_plate(name="Plate 1")
        project.add_plate(name="Plate 2")
        project.save(str(out))
        with zipfile.ZipFile(out) as z:
            config = z.read("Metadata/model_settings.config").decode()
        root = ET.fromstring(config)
        plates = root.findall("plate")
        assert len(plates) == 2

    def test_config_xml_plate_ids_1_indexed(self, tmp_path):
        out = tmp_path / "out.3mf"
        project = BambuProject()
        project.add_plate()
        project.add_plate()
        project.save(str(out))
        with zipfile.ZipFile(out) as z:
            config = z.read("Metadata/model_settings.config").decode()
        root = ET.fromstring(config)
        plates = root.findall("plate")
        ids = [
            m.get("value")
            for p in plates
            for m in p.findall("metadata")
            if m.get("key") == "plater_id"
        ]
        assert ids == ["1", "2"]

    def test_save_no_plates_no_config(self, tmp_path):
        out = tmp_path / "out.3mf"
        BambuProject().save(str(out))
        with zipfile.ZipFile(out) as z:
            assert "Metadata/model_settings.config" not in z.namelist()


class TestProjectSettings:
    def test_save_contains_project_settings(self, tmp_path):
        out = tmp_path / "out.3mf"
        BambuProject().save(str(out))
        with zipfile.ZipFile(out) as z:
            assert "Metadata/project_settings.config" in z.namelist()

    def test_project_settings_has_default_printable_area(self, tmp_path):
        out = tmp_path / "out.3mf"
        BambuProject().save(str(out))
        with zipfile.ZipFile(out) as z:
            settings = json.loads(z.read("Metadata/project_settings.config"))
        assert settings["printable_area"] == ["0x0", "256x0", "256x256", "0x256"]

    def test_project_settings_has_custom_printable_area(self, tmp_path):
        out = tmp_path / "out.3mf"
        BambuProject(bed_size=(180, 180)).save(str(out))
        with zipfile.ZipFile(out) as z:
            settings = json.loads(z.read("Metadata/project_settings.config"))
        assert settings["printable_area"] == ["0x0", "180x0", "180x180", "0x180"]
