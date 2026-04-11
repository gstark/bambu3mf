from pathlib import Path

import pytest

from bambu3mf.stl_loader import load_stl

FIXTURES = Path(__file__).parent / "fixtures"
CUBE_STL = FIXTURES / "cube.stl"


class TestLoadStl:
    def test_returns_mesh_resource_id(self):
        import lib3mf

        model = lib3mf.Wrapper().CreateModel()
        result = load_stl(model, str(CUBE_STL))
        assert isinstance(result["resource_id"], int)

    def test_correct_vertex_count(self):
        import lib3mf

        model = lib3mf.Wrapper().CreateModel()
        result = load_stl(model, str(CUBE_STL))
        assert result["vertex_count"] == 8

    def test_correct_triangle_count(self):
        import lib3mf

        model = lib3mf.Wrapper().CreateModel()
        result = load_stl(model, str(CUBE_STL))
        assert result["triangle_count"] == 12

    def test_returns_bounding_box(self):
        import lib3mf

        model = lib3mf.Wrapper().CreateModel()
        result = load_stl(model, str(CUBE_STL))
        bb = result["bounding_box"]
        assert bb["min_x"] == pytest.approx(0.0)
        assert bb["min_y"] == pytest.approx(0.0)
        assert bb["min_z"] == pytest.approx(0.0)
        assert bb["max_x"] == pytest.approx(10.0)
        assert bb["max_y"] == pytest.approx(20.0)
        assert bb["max_z"] == pytest.approx(30.0)

    def test_invalid_path_raises(self):
        import lib3mf

        model = lib3mf.Wrapper().CreateModel()
        with pytest.raises(FileNotFoundError):
            load_stl(model, "/nonexistent/file.stl")

    def test_creates_build_item(self):
        import lib3mf

        model = lib3mf.Wrapper().CreateModel()
        load_stl(model, str(CUBE_STL))
        it = model.GetBuildItems()
        assert it.MoveNext()

    def test_sets_mesh_name_from_filename(self):
        import lib3mf

        model = lib3mf.Wrapper().CreateModel()
        load_stl(model, str(CUBE_STL))
        it = model.GetMeshObjects()
        it.MoveNext()
        assert it.GetCurrentMeshObject().GetName() == "cube"

    def test_plate_offset_shifts_transform(self):
        import lib3mf

        model = lib3mf.Wrapper().CreateModel()
        load_stl(model, str(CUBE_STL), plate_offset_x=307.2, plate_offset_y=-307.2)
        it = model.GetBuildItems()
        it.MoveNext()
        t = it.GetCurrent().GetObjectTransform()
        assert t.Fields[3][0] == pytest.approx(307.2 + 123, abs=1)
        assert t.Fields[3][1] == pytest.approx(-307.2 + 118, abs=1)
