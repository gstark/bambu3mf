# bambu3mf

Python library for creating BambuStudio-compatible 3MF project files. Supports multi-plate layouts, per-object extruder assignment, and printer/filament preset configuration.

## Installation

```bash
pip install bambu3mf
```

Requires Python 3.10+ and [lib3mf](https://github.com/3MFConsortium/lib3mf).

## Quick Start

```python
from bambu3mf import BambuProject

project = BambuProject(
    printer_settings_id="Bambu Lab P1P 0.4 nozzle",
    filaments=[
        {"settings_id": "Bambu PLA Basic @BBL P1P", "colour": "#FF0000"},
        {"settings_id": "Bambu PLA Basic @BBL P1P", "colour": "#0000FF"},
    ],
)

plate = project.add_plate(name="My Plate")
plate.add_stl("body.stl", extruder=1)
plate.add_stl("accent.stl", position=(150, 100), extruder=2)

project.save("output.3mf")
```

Open `output.3mf` in BambuStudio and it will load with correct plate layout, filament colors, and printer preset -- ready to slice.

## Examples

### Single Object, Auto-Centered

```python
from bambu3mf import BambuProject

project = BambuProject()
plate = project.add_plate()
plate.add_stl("model.stl")  # centered on bed automatically
project.save("simple.3mf")
```

### Multi-Plate Project

```python
from bambu3mf import BambuProject

project = BambuProject(
    printer_settings_id="Bambu Lab X1 Carbon 0.4 nozzle",
    filaments=[{"settings_id": "Bambu PLA Basic @BBL X1C", "colour": "#FFFFFF"}],
)

p1 = project.add_plate(name="Base Parts")
p1.add_stl("base_left.stl", position=(10, 10))
p1.add_stl("base_right.stl", position=(140, 10))

p2 = project.add_plate(name="Top Parts")
p2.add_stl("top.stl")

project.save("multi_plate.3mf")
```

Plates are arranged in a grid layout matching BambuStudio's internal algorithm. Objects are assigned to plates by spatial position.

### Multi-Color Print

```python
from bambu3mf import BambuProject

project = BambuProject(
    printer_settings_id="Bambu Lab P1S 0.4 nozzle",
    filaments=[
        {"settings_id": "Bambu PLA Basic @BBL P1S", "colour": "#000000", "type": "PLA"},
        {"settings_id": "Bambu PLA Basic @BBL P1S", "colour": "#FF5733", "type": "PLA"},
        {"settings_id": "Bambu PLA Basic @BBL P1S", "colour": "#FFFFFF", "type": "PLA"},
    ],
)

plate = project.add_plate()
plate.add_stl("frame.stl", extruder=1)          # black
plate.add_stl("logo.stl", position=(80, 80), extruder=2)   # orange
plate.add_stl("text.stl", position=(80, 120), extruder=3)  # white

project.save("multicolor.3mf")
```

### Custom Bed Size (A1 Mini)

```python
from bambu3mf import BambuProject

project = BambuProject(
    bed_size=(180, 180),
    printer_settings_id="Bambu Lab A1 mini 0.4 nozzle",
)
plate = project.add_plate()
plate.add_stl("small_part.stl")
project.save("a1_mini.3mf")
```

### Description Metadata

```python
from bambu3mf import BambuProject

project = BambuProject(
    description="<p>Print-in-place gearbox with 0.2mm clearance.</p>",
)
plate = project.add_plate(name="Main")
plate.add_stl("gearbox.stl")
project.save("described.3mf")
```

`description` is written to `<metadata name="Description">...</metadata>` in `3D/3dmodel.model`. If the value contains HTML-like text, it is XML-escaped in the 3MF archive.

## API Reference

### `BambuProject`

```python
BambuProject(
    *,
    bed_size=(256, 256),        # (width, height) in mm
    printer_settings_id="",     # BambuStudio printer preset name
    filaments=None,             # list of filament dicts (see below)
    app_version=None,           # override Application metadata
    description=None,           # optional 3MF Description metadata (HTML text is XML-escaped)
)
```

**Filament dicts** accept these keys:

| Key | Default | Description |
|---|---|---|
| `settings_id` | `""` | BambuStudio filament preset name |
| `colour` | `"#00AE42"` | Hex color shown in slicer UI |
| `type` | `"PLA"` | Material type |
| `diameter` | `"1.75"` | Filament diameter in mm |

**Methods:**

- `add_plate(*, name=None)` -- Create a new plate. Returns a `Plate`. Plates are 1-indexed.
- `save(path)` -- Write the 3MF file.

### `Plate`

Created via `project.add_plate()`. Do not instantiate directly.

**Methods:**

- `add_stl(path, *, position=None, extruder=1)` -- Load an STL onto this plate.
  - `position`: `(x, y)` in mm for the object's min corner, relative to plate origin. `None` to auto-center.
  - `extruder`: 1-indexed filament slot.
  - Returns a dict with `resource_id`, `vertex_count`, `triangle_count`, `bounding_box`.
  - Raises `FileNotFoundError` if the STL doesn't exist.
  - Raises `ValueError` if the object exceeds bed bounds at the given position.

## How It Works

The library generates a valid 3MF ZIP archive containing:

| File | Format | Purpose |
|---|---|---|
| `3D/3dmodel.model` | XML | Mesh geometry with BambuStudio namespace |
| `Metadata/project_settings.config` | JSON | Printer, filament, and bed configuration |
| `Metadata/model_settings.config` | XML | Per-object metadata and plate layout |

Mesh geometry is handled by [lib3mf](https://github.com/3MFConsortium/lib3mf). BambuStudio-specific metadata (namespace, version, config files) is injected post-write since lib3mf has no API for custom namespaces.

**Key compatibility detail:** BambuStudio assigns objects to plates by spatial bounding-box intersection, not by the plate-to-object mapping in config. The library handles this automatically by positioning objects in the correct grid cell.

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

See [LICENSE](LICENSE) for details.
