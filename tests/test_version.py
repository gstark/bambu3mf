import xml.etree.ElementTree as ET
import zipfile

from bambu3mf import BambuProject
from bambu3mf.project import BAMBU_APPLICATION, _parse_version_inc


class TestParseVersionInc:
    def test_parses_version_from_file(self, tmp_path):
        inc = tmp_path / "version.inc"
        inc.write_text('set(SLIC3R_VERSION "01.02.03.04")\n')
        assert _parse_version_inc(str(inc)) == "01.02.03.04"

    def test_returns_none_for_missing_file(self):
        assert _parse_version_inc("/nonexistent/version.inc") is None

    def test_returns_none_for_malformed_file(self, tmp_path):
        inc = tmp_path / "version.inc"
        inc.write_text("no version here\n")
        assert _parse_version_inc(str(inc)) is None

    def test_ignores_other_set_commands(self, tmp_path):
        inc = tmp_path / "version.inc"
        inc.write_text(
            'set(SLIC3R_APP_NAME "BambuStudio")\n'
            'set(SLIC3R_VERSION "99.88.77.66")\n'
        )
        assert _parse_version_inc(str(inc)) == "99.88.77.66"


class TestBambuApplicationDefault:
    def test_default_reads_from_version_inc(self):
        # BAMBU_APPLICATION should match version.inc in the repo
        assert BAMBU_APPLICATION.startswith("BambuStudio-")
        version_part = BAMBU_APPLICATION.replace("BambuStudio-", "")
        # Should be a dotted version string
        parts = version_part.split(".")
        assert len(parts) == 4

    def test_default_matches_version_inc(self):
        assert BAMBU_APPLICATION == "BambuStudio-02.05.00.66"


class TestAppVersionConfigurable:
    def test_custom_app_version_in_metadata(self, tmp_path):
        out = tmp_path / "out.3mf"
        project = BambuProject(app_version="BambuStudio-99.00.00.01")
        project.save(str(out))
        with zipfile.ZipFile(out) as z:
            xml_bytes = z.read("3D/3dmodel.model")
        root = ET.fromstring(xml_bytes)
        ns = root.tag.split("}")[0] + "}" if "}" in root.tag else ""
        metadata = {
            m.get("name"): m.text for m in root.findall(f"{ns}metadata")
        }
        assert metadata["Application"] == "BambuStudio-99.00.00.01"

    def test_default_app_version_uses_module_constant(self, tmp_path):
        out = tmp_path / "out.3mf"
        project = BambuProject()
        project.save(str(out))
        with zipfile.ZipFile(out) as z:
            xml_bytes = z.read("3D/3dmodel.model")
        root = ET.fromstring(xml_bytes)
        ns = root.tag.split("}")[0] + "}" if "}" in root.tag else ""
        metadata = {
            m.get("name"): m.text for m in root.findall(f"{ns}metadata")
        }
        assert metadata["Application"] == BAMBU_APPLICATION
