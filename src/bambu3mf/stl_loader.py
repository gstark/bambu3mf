"""Low-level STL loading into a lib3mf model with positioning.

Handles reading STL files, computing bounding boxes, setting mesh names,
and positioning objects via build-item transforms.  The transform includes
both the object's position on the plate and the plate's offset in the
multi-plate grid layout.

The lib3mf Transform is a 4x3 matrix stored as Fields[4][3]:
    Fields[0..2] = 3x3 rotation/scale (identity for no rotation)
    Fields[3]    = translation (x, y, z)
"""

from pathlib import Path

import lib3mf


def load_stl(model, path, *, bed_size=(256, 256), position=None,
             plate_offset_x=0.0, plate_offset_y=0.0):
    """Load an STL file into a lib3mf model, position on bed, return mesh info.

    Args:
        model: A lib3mf Model instance (shared across the project).
        path: Path to the STL file.
        bed_size: ``(width, height)`` of the print bed in mm.
        position: ``(x, y)`` for placing the object's bounding-box min corner
            on the bed.  If None, auto-centers on the bed.
        plate_offset_x: Additional X translation to place the object in the
            correct plate's grid cell.  See :mod:`bambu3mf.plate`.
        plate_offset_y: Additional Y translation for the plate grid cell.

    Returns:
        Dict with keys: ``resource_id`` (int), ``vertex_count`` (int),
        ``triangle_count`` (int), ``bounding_box`` (dict with min/max x/y/z).

    Raises:
        FileNotFoundError: If the STL file does not exist.
        ValueError: If the object at the given position exceeds the bed bounds.
    """
    if not Path(path).exists():
        raise FileNotFoundError(f"STL file not found: {path}")

    reader = model.QueryReader("stl")
    reader.ReadFromFile(str(path))

    mesh = _get_last_mesh(model)
    mesh.SetName(Path(path).stem)
    bb = _bounding_box(mesh)

    obj_w = bb["max_x"] - bb["min_x"]
    obj_h = bb["max_y"] - bb["min_y"]

    if position is not None:
        placed_min_x, placed_min_y = position
        placed_max_x = placed_min_x + obj_w
        placed_max_y = placed_min_y + obj_h
        if (placed_min_x < 0 or placed_min_y < 0
                or placed_max_x > bed_size[0] or placed_max_y > bed_size[1]):
            bi = _get_last_build_item(model)
            model.RemoveBuildItem(bi)
            model.RemoveResource(mesh)
            raise ValueError(
                f"Object ({obj_w:.1f}x{obj_h:.1f}mm) at position "
                f"({position[0]}, {position[1]}) exceeds bed size "
                f"({bed_size[0]}x{bed_size[1]}mm). "
                f"Object bounds: ({placed_min_x}, {placed_min_y}) to "
                f"({placed_max_x:.1f}, {placed_max_y:.1f})"
            )
        tx, ty = position[0] - bb["min_x"], position[1] - bb["min_y"]
    else:
        cx = (bb["min_x"] + bb["max_x"]) / 2
        cy = (bb["min_y"] + bb["max_y"]) / 2
        tx = bed_size[0] / 2 - cx
        ty = bed_size[1] / 2 - cy

    bi = _get_last_build_item(model)
    t = _identity_transform()
    t.Fields[3][0] = tx + plate_offset_x
    t.Fields[3][1] = ty + plate_offset_y
    bi.SetObjectTransform(t)

    return {
        "resource_id": mesh.GetResourceID(),
        "vertex_count": mesh.GetVertexCount(),
        "triangle_count": mesh.GetTriangleCount(),
        "bounding_box": bb,
    }


def _get_last_mesh(model):
    """Return the most recently added mesh object in the model."""
    it = model.GetMeshObjects()
    mesh = None
    while it.MoveNext():
        mesh = it.GetCurrentMeshObject()
    return mesh


def _get_last_build_item(model):
    """Return the most recently added build item in the model."""
    it = model.GetBuildItems()
    bi = None
    while it.MoveNext():
        bi = it.GetCurrent()
    return bi


def _bounding_box(mesh):
    """Compute axis-aligned bounding box from mesh vertices."""
    verts = mesh.GetVertices()
    xs = [v.Coordinates[0] for v in verts]
    ys = [v.Coordinates[1] for v in verts]
    zs = [v.Coordinates[2] for v in verts]
    return {
        "min_x": min(xs), "max_x": max(xs),
        "min_y": min(ys), "max_y": max(ys),
        "min_z": min(zs), "max_z": max(zs),
    }


def _identity_transform():
    """Create a lib3mf Transform initialized to the identity matrix."""
    t = lib3mf.Transform()
    t.Fields[0][0] = 1.0
    t.Fields[1][1] = 1.0
    t.Fields[2][2] = 1.0
    return t
