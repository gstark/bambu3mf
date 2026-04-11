# Manual BambuStudio Verification

## Generate test 3MF

```python
from bambu3mf import BambuProject

project = BambuProject()

p1 = project.add_plate(name="Plate 1")
p1.add_stl("path/to/cube.stl")
p1.add_stl("path/to/cube.stl", position=(50, 50))

p2 = project.add_plate(name="Plate 2")
p2.add_stl("path/to/cube.stl", position=(0, 0))

p3 = project.add_plate()
p3.add_stl("path/to/cube.stl")

project.save("test_output.3mf")
```

## Verify in BambuStudio

1. Open `test_output.3mf` in BambuStudio
2. Accept printer profile prompt (expected for minimal 3MF)
3. Check:
   - [ ] Three plates visible in plate tab bar
   - [ ] Plate 1 shows two cube objects
   - [ ] Plate 2 shows one cube at corner
   - [ ] Plate 3 shows one centered cube
   - [ ] Plate names match ("Plate 1", "Plate 2", "Plate 3")
   - [ ] Objects are selectable and show mesh properties
   - [ ] Slicing completes without errors (after printer profile applied)
