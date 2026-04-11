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


def load_stl(model, path, *, bed_size=(256, 256), position=None):
    """Load an STL file into a lib3mf model, position on bed, return mesh info.

    The build item is initially positioned with bed-centering only (no plate
    offset).  Plate grid offsets are applied later by
    :meth:`Plate._apply_plate_offsets` at save time.

    Args:
        model: A lib3mf Model instance (shared across the project).
        path: Path to the STL file.
        bed_size: ``(width, height)`` of the print bed in mm.
        position: ``(x, y)`` for placing the object's bounding-box min corner
            on the bed.  If None, auto-centers on the bed.

    Returns:
        Dict with keys: ``resource_id`` (int), ``vertex_count`` (int),
        ``triangle_count`` (int), ``bounding_box`` (dict with min/max x/y/z),
        ``center_offset`` (tuple of tx, ty for bed centering).

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
    t.Fields[3][0] = tx
    t.Fields[3][1] = ty
    bi.SetObjectTransform(t)

    return {
        "resource_id": mesh.GetResourceID(),
        "vertex_count": mesh.GetVertexCount(),
        "triangle_count": mesh.GetTriangleCount(),
        "bounding_box": bb,
        "center_offset": (tx, ty),
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


def load_stl_as_mesh(model, path):
    """Load an STL into the model as a mesh object without a build item.

    Used for component parts that will be grouped into a ComponentsObject.
    The auto-created build item is removed, leaving just the mesh resource.

    Returns:
        Dict with ``resource_id``, ``vertex_count``, ``triangle_count``,
        ``bounding_box``, and ``mesh`` (the lib3mf mesh object).
    """
    if not Path(path).exists():
        raise FileNotFoundError(f"STL file not found: {path}")

    reader = model.QueryReader("stl")
    reader.ReadFromFile(str(path))

    mesh = _get_last_mesh(model)
    mesh.SetName(Path(path).stem)

    # Remove the auto-created build item — we'll add a component instead
    bi = _get_last_build_item(model)
    model.RemoveBuildItem(bi)

    bb = _bounding_box(mesh)
    return {
        "resource_id": mesh.GetResourceID(),
        "vertex_count": mesh.GetVertexCount(),
        "triangle_count": mesh.GetTriangleCount(),
        "bounding_box": bb,
        "mesh": mesh,
    }


def create_component_group(model, meshes, *, bed_size=(256, 256),
                           position=None):
    """Group multiple mesh objects into a single ComponentsObject with one build item.

    The build item is initially positioned with bed-centering only (no plate
    offset).  Call :func:`update_build_item_plate_offset` after all plates are
    created to apply the final plate grid offset.

    Args:
        model: A lib3mf Model instance.
        meshes: List of lib3mf mesh objects to group.
        bed_size: ``(width, height)`` of the print bed in mm.
        position: ``(x, y)`` for the group's bounding-box min corner.
            If None, auto-centers on the bed.

    Returns:
        Dict with ``resource_id`` (of the component object) and
        ``center_offset`` ``(tx, ty)`` for bed centering.
    """
    identity = _identity_transform()
    comp_obj = model.AddComponentsObject()
    for mesh in meshes:
        comp_obj.AddComponent(mesh, identity)

    # Compute combined bounding box
    all_bbs = [_bounding_box(m) for m in meshes]
    combined_bb = {
        "min_x": min(b["min_x"] for b in all_bbs),
        "max_x": max(b["max_x"] for b in all_bbs),
        "min_y": min(b["min_y"] for b in all_bbs),
        "max_y": max(b["max_y"] for b in all_bbs),
    }

    if position is not None:
        tx = position[0] - combined_bb["min_x"]
        ty = position[1] - combined_bb["min_y"]
    else:
        cx = (combined_bb["min_x"] + combined_bb["max_x"]) / 2
        cy = (combined_bb["min_y"] + combined_bb["max_y"]) / 2
        tx = bed_size[0] / 2 - cx
        ty = bed_size[1] / 2 - cy

    t = _identity_transform()
    t.Fields[3][0] = tx
    t.Fields[3][1] = ty
    model.AddBuildItem(comp_obj, t)

    return {
        "resource_id": comp_obj.GetResourceID(),
        "center_offset": (tx, ty),
    }


def update_build_item_plate_offset(model, resource_id, center_offset,
                                   plate_offset_x, plate_offset_y):
    """Update a build item's transform to include the final plate grid offset.

    Called at save time after all plates are created and grid positions are known.
    """
    it = model.GetBuildItems()
    while it.MoveNext():
        bi = it.GetCurrent()
        obj = bi.GetObjectResource()
        if obj.GetResourceID() == resource_id:
            t = _identity_transform()
            t.Fields[3][0] = center_offset[0] + plate_offset_x
            t.Fields[3][1] = center_offset[1] + plate_offset_y
            bi.SetObjectTransform(t)
            return


def _identity_transform():
    """Create a lib3mf Transform initialized to the identity matrix."""
    t = lib3mf.Transform()
    t.Fields[0][0] = 1.0
    t.Fields[1][1] = 1.0
    t.Fields[2][2] = 1.0
    return t
