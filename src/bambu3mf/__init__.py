"""Python library for creating BambuStudio-compatible 3MF project files.

Generates 3MF archives that open cleanly in BambuStudio with full support
for multi-plate layouts, per-object filament/extruder assignment, and
printer/filament preset configuration.

Quick start::

    from bambu3mf import BambuProject

    project = BambuProject(
        printer_settings_id="Bambu Lab P1P 0.4 nozzle",
        filaments=[
            {"settings_id": "Bambu PLA Basic @BBL P1P", "colour": "#FF0000"},
            {"settings_id": "Bambu PLA Basic @BBL P1P", "colour": "#0000FF"},
        ],
    )
    plate = project.add_plate(name="My Plate")
    plate.add_stl("model_a.stl", extruder=1)
    plate.add_stl("model_b.stl", position=(150, 100), extruder=2)
    project.save("output.3mf")
"""

from bambu3mf.plate import Plate
from bambu3mf.project import BambuProject

__all__ = ["BambuProject", "Plate"]
