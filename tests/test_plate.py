from bambu3mf.plate import Plate


class TestPlateInit:
    def test_plate_has_id(self):
        plate = Plate(plate_id=1)
        assert plate.plate_id == 1

    def test_plate_has_name(self):
        plate = Plate(plate_id=1, name="My Plate")
        assert plate.name == "My Plate"

    def test_plate_auto_names_from_id(self):
        plate = Plate(plate_id=3)
        assert plate.name == "Plate 3"

    def test_plate_objects_empty_by_default(self):
        plate = Plate(plate_id=1)
        assert plate.objects == []
