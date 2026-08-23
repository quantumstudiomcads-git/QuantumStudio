import subprocess
import sys
import unittest

import numpy as np

from frontend.core.structure import Atom, Structure
from frontend.device_builder.assembly import assemble_device, rotation_matrix_xyz, validate_device
from frontend.device_builder.model import Device, DeviceRegion, RegionRole, role_label


def source_structure():
    structure = Structure(
        atoms=[Atom("C", 1.0, 0.0, 0.0), Atom("O", 0.0, 1.0, 0.0)],
        cell=[[2.0, 0.0, 0.0], [0.0, 3.0, 0.0], [0.0, 0.0, 4.0]],
        name="source",
    )
    structure.periodic = [True, True, False]
    return structure


class DeviceModelTests(unittest.TestCase):
    def test_device_and_region_creation_and_roles(self):
        region = DeviceRegion(source_structure(), name="channel", role=RegionRole.CHANNEL)
        device = Device(name="Device")
        device.add_region(region)
        self.assertEqual(device.regions, [region])
        self.assertEqual(role_label(region.role), "Channel")
        self.assertEqual(device.transport_direction, "Z")

    def test_translation_rotation_and_source_immutability(self):
        source = source_structure()
        source_before = source.to_dict()
        region = DeviceRegion(source, translation=(2.0, 3.0, 4.0), rotation=(0.0, 0.0, 90.0))
        transformed = region.transformed_structure()
        self.assertEqual(source.to_dict(), source_before)
        np.testing.assert_allclose(
            [(atom.x, atom.y, atom.z) for atom in transformed.atoms],
            [(2.0, 4.0, 4.0), (1.0, 3.0, 4.0)],
            atol=1e-12,
        )
        np.testing.assert_allclose(
            np.asarray(transformed.cell),
            np.asarray(source.cell) @ rotation_matrix_xyz((0.0, 0.0, 90.0)).T,
        )

    def test_duplicate_has_unique_identity_and_independent_transform_state(self):
        device = Device(name="Device")
        original = device.add_region(DeviceRegion(source_structure(), translation=(1.0, 0.0, 0.0)))
        duplicate = device.duplicate_region(original.id)
        self.assertNotEqual(original.id, duplicate.id)
        self.assertIsNot(original.source_structure, duplicate.source_structure)
        duplicate.translation = (9.0, 0.0, 0.0)
        self.assertEqual(original.translation, (1.0, 0.0, 0.0))

    def test_visibility_membership_and_assembly_coordinates(self):
        device = Device(name="Device")
        first = device.add_region(DeviceRegion(source_structure(), name="first"))
        second = device.add_region(DeviceRegion(source_structure(), name="second", translation=(10.0, 0.0, 0.0)))
        second.visible = False
        result = assemble_device(device)
        self.assertEqual(len(result.structure.atoms), 2)
        self.assertEqual(result.atom_region_ids, (first.id, first.id))
        second.visible = True
        result = device.assemble_with_membership()
        self.assertEqual(len(result.structure.atoms), 4)
        self.assertEqual(result.atom_region_ids[-2:], (second.id, second.id))
        np.testing.assert_allclose(
            [(atom.x, atom.y, atom.z) for atom in result.structure.atoms[-2:]],
            [(11.0, 0.0, 0.0), (10.0, 1.0, 0.0)],
        )

    def test_explicit_device_cell_and_pbc_propagate(self):
        cell = [[8.0, 0.0, 0.0], [0.0, 9.0, 0.0], [0.0, 0.0, 10.0]]
        device = Device(name="Device", cell=cell, periodic=(True, False, True), transport_direction="X")
        device.add_region(DeviceRegion(source_structure()))
        assembled = device.assemble()
        self.assertEqual(assembled.cell, cell)
        self.assertEqual(assembled.periodic, [True, False, True])

    def test_invalid_geometry_and_transforms_are_rejected(self):
        device = Device(name="Device", cell=[[1.0, 0.0, 0.0], [2.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
        device.add_region(DeviceRegion(source_structure()))
        self.assertFalse(validate_device(device).valid)
        device = Device(name="Device")
        region = device.add_region(DeviceRegion(source_structure()))
        region.translation = (float("nan"), 0.0, 0.0)
        self.assertFalse(validate_device(device).valid)
        with self.assertRaises(ValueError):
            assemble_device(device)

    def test_model_import_does_not_import_qt(self):
        command = (
            "import sys; import frontend.device_builder.model; "
            "assert not any(name.startswith('PySide6') for name in sys.modules)"
        )
        subprocess.run([sys.executable, "-c", command], check=True)
