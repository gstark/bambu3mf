"""Objects must sit on the bed (Z=0), whatever the Z range of the STL file."""
import re
import struct
import zipfile

import pytest

from bambu3mf import BambuProject

FACETS = [(0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3)]


def _write_tetrahedron(path, *, min_z, origin=(0, 0)):
    ox, oy = origin
    points = [
        (ox, oy, min_z), (ox + 10, oy, min_z),
        (ox, oy + 10, min_z), (ox, oy, min_z + 10),
    ]
    # Binary STL: 80-byte header, facet count, then normal + 3 vertices each.
    data = bytes(80) + struct.pack("<I", len(FACETS))
    for facet in FACETS:
        coords = [c for i in facet for c in points[i]]
        data += struct.pack("<12fH", 0, 0, 0, *coords, 0)
    path.write_bytes(data)
    return str(path)


def _item_translations(path):
    with zipfile.ZipFile(path) as z:
        model = z.read("3D/3dmodel.model").decode()
    return [
        [float(n) for n in transform.split()[9:]]
        for transform in re.findall(r'<item [^>]*transform="([^"]+)"', model)
    ]


@pytest.mark.parametrize("min_z", [24, -3, 0])
def test_add_stl_puts_object_on_bed(tmp_path, min_z):
    project = BambuProject()
    project.add_plate().add_stl(_write_tetrahedron(tmp_path / "t.stl", min_z=min_z))
    out = tmp_path / "out.3mf"
    project.save(str(out))
    [(_, _, tz)] = _item_translations(out)
    assert tz == -min_z


def test_z_offset_is_kept_on_later_plates(tmp_path):
    stl = _write_tetrahedron(tmp_path / "t.stl", min_z=24)
    project = BambuProject()
    project.add_plate().add_stl(stl)
    project.add_plate().add_stl(stl)
    out = tmp_path / "out.3mf"
    project.save(str(out))
    assert [t[2] for t in _item_translations(out)] == [-24, -24]


def test_group_is_lowered_as_one_unit(tmp_path):
    low = _write_tetrahedron(tmp_path / "low.stl", min_z=5)
    high = _write_tetrahedron(tmp_path / "high.stl", min_z=15, origin=(20, 0))
    project = BambuProject()
    project.add_plate().add_stl_group([(low, 1), (high, 1)])
    out = tmp_path / "out.3mf"
    project.save(str(out))
    [(_, _, tz)] = _item_translations(out)
    assert tz == -5
