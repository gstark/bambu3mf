"""Plate management and spatial layout for multi-plate projects.

BambuStudio arranges plates in a grid and assigns objects to plates by
checking whether each object's bounding box spatially intersects a plate's
region — it does NOT use the plate→object mapping in model_settings.config
for assignment (that mapping is only used for metadata like identify_id).

Grid layout algorithm (mirrors ``PartPlateList`` in PartPlate.cpp):

* Column count = ``ceil(sqrt(plate_count))``, matching
  ``compute_colum_count()`` in ``src/slic3r/GUI/PartPlate.hpp:38``.
* Gap between plates = 1/5 of plate dimension (``LOGICAL_PART_PLATE_GAP``
  in ``src/slic3r/GUI/PartPlate.cpp:52``).
* Stride = ``dimension * (1 + 1/5) = dimension * 1.2``.
* Plate origins: ``x = col * stride_x``, ``y = -row * stride_y``
  (negative Y = downward rows).

Example layout for 5 plates on a 256mm bed (3 columns)::

    Plate 1 (0, 0)       Plate 2 (307.2, 0)      Plate 3 (614.4, 0)
    Plate 4 (0, -307.2)  Plate 5 (307.2, -307.2)
"""

import math

from bambu3mf.stl_loader import load_stl, load_stl_as_mesh, create_component_group

# Matches LOGICAL_PART_PLATE_GAP in src/slic3r/GUI/PartPlate.cpp:52
PLATE_GAP_RATIO = 1.0 / 5.0


def _plate_cols(plate_count):
    """Compute grid column count, matching BambuStudio's compute_colum_count().

    Returns ceil(sqrt(plate_count)) using the same rounding logic as the
    C++ implementation in src/slic3r/GUI/PartPlate.hpp:38-50.
    """
    v = math.sqrt(plate_count)
    r = round(v)
    return int(r + 1) if v > r else int(r)


class Plate:
    """A single build plate that holds objects.

    Args:
        plate_id: 1-indexed plate number.
        name: Display name shown in BambuStudio's plate list.
            Defaults to ``"Plate {plate_id}"``.
        project: Parent :class:`~bambu3mf.project.BambuProject` reference,
            used for bed_size and the shared lib3mf model.
    """

    def __init__(self, plate_id, *, name=None, project=None):
        self.plate_id = plate_id
        self.name = name if name is not None else f"Plate {plate_id}"
        self.objects = []
        self._project = project

    def _plate_origin(self):
        """Compute (x, y) world-space origin for this plate's grid cell.

        Must be called after all plates are added to the project, since the
        column count depends on the total plate count.
        """
        index = self.plate_id - 1
        total = len(self._project.plates)
        cols = _plate_cols(total)
        col = index % cols
        row = index // cols
        w, h = self._project.bed_size
        stride_x = w * (1.0 + PLATE_GAP_RATIO)
        stride_y = h * (1.0 + PLATE_GAP_RATIO)
        return col * stride_x, -row * stride_y

    def add_stl(self, path, *, position=None, extruder=1):
        """Add an STL model to this plate.

        Args:
            path: Path to the STL file.
            position: ``(x, y)`` in mm for the object's bounding-box min corner,
                relative to this plate's origin.  If None, auto-centers on the
                plate.  Raises ValueError if the object exceeds the bed bounds.
            extruder: 1-indexed filament/extruder slot.  Must correspond to an
                entry in the project's ``filaments`` list.

        Returns:
            Dict with ``resource_id``, ``vertex_count``, ``triangle_count``,
            ``bounding_box``.
        """
        from pathlib import Path as _Path
        ox, oy = self._plate_origin()
        result = load_stl(
            self._project._model, path,
            bed_size=self._project.bed_size,
            position=position,
            plate_offset_x=ox,
            plate_offset_y=oy,
        )
        self.objects.append({
            "object_id": result["resource_id"],
            "instance_id": 0,
            "name": _Path(path).stem,
            "extruder": extruder,
        })
        return result

    def add_stl_group(self, stl_entries, *, position=None):
        """Add multiple STLs as parts of a single grouped object on this plate.

        This creates a lib3mf ComponentsObject that groups the meshes, so they
        share a single transform and move as a unit in BambuStudio.

        Args:
            stl_entries: List of ``(path, extruder)`` tuples.
            position: ``(x, y)`` for the group's bounding-box min corner.
                If None, auto-centers on the plate.

        Returns:
            Dict with ``resource_id`` of the component object.
        """
        from pathlib import Path as _Path
        ox, oy = self._plate_origin()

        parts = []
        meshes = []
        for path, extruder in stl_entries:
            result = load_stl_as_mesh(self._project._model, path)
            meshes.append(result["mesh"])
            parts.append({
                "object_id": result["resource_id"],
                "name": _Path(path).stem,
                "extruder": extruder,
            })

        group = create_component_group(
            self._project._model, meshes,
            bed_size=self._project.bed_size,
            position=position,
            plate_offset_x=ox,
            plate_offset_y=oy,
        )

        self.objects.append({
            "object_id": group["resource_id"],
            "instance_id": 0,
            "name": parts[0]["name"] if parts else "group",
            "extruder": 1,
            "parts": parts,
        })
        return group
