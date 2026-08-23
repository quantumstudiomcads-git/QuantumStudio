import unittest

import numpy as np

from frontend.core.structure import Atom, Structure
from frontend.device_builder.assembly import (
    DEFAULT_COLLISION_SCALE, align_region_centers, align_region_surface,
    assemble_device, covalent_radius, detect_inter_region_collisions,
    fit_device_cell, place_region, repeat_region, transformed_region_bounds,
    validate_device,
)
from frontend.device_builder.model import Device, DeviceRegion, RegionRole


def structure(points=((0.0, 0.0, 0.0), (2.0, 4.0, 6.0)), element="C"):
    source = Structure(
        atoms=[Atom(element, *point) for point in points],
        cell=[[5.0, 0.0, 0.0], [0.0, 7.0, 0.0], [0.0, 0.0, 11.0]],
        name="source",
    )
    source.periodic = [True, True, False]
    return source


class DeviceGeometryTests(unittest.TestCase):
    def setUp(self):
        self.source = structure()
        self.device = Device(name="Geometry Device", periodic=(True, False, True))
        self.reference = self.device.add_region(DeviceRegion(self.source, name="Reference", translation=(10.0, 20.0, 30.0)))
        self.moving = self.device.add_region(DeviceRegion(self.source, name="Moving"))

    def test_place_above_below_right_left_uses_current_bounds_and_preserves_source(self):
        before = self.source.to_dict()
        cases = (
            ("above", 2, lambda reference, moving: moving.minimum[2] - reference.maximum[2]),
            ("below", 2, lambda reference, moving: reference.minimum[2] - moving.maximum[2]),
            ("right", 0, lambda reference, moving: moving.minimum[0] - reference.maximum[0]),
            ("left", 0, lambda reference, moving: reference.minimum[0] - moving.maximum[0]),
        )
        for direction, _, separation in cases:
            self.moving.translation = (0.0, 0.0, 0.0)
            place_region(self.moving, self.reference, direction, gap=2.5)
            self.assertAlmostEqual(separation(transformed_region_bounds(self.reference), transformed_region_bounds(self.moving)), 2.5)
        self.assertEqual(self.source.to_dict(), before)

    def test_align_centers_and_surfaces(self):
        for axes in ("X", "Y", "Z", "XY", "XYZ"):
            self.moving.translation = (0.0, 0.0, 0.0)
            align_region_centers(self.moving, self.reference, axes)
            reference_center = transformed_region_bounds(self.reference).center
            moving_center = transformed_region_bounds(self.moving).center
            for index, letter in enumerate("XYZ"):
                if letter in axes:
                    self.assertAlmostEqual(moving_center[index], reference_center[index])
        for surface, axis, attribute in (("top", 2, "maximum"), ("bottom", 2, "minimum"), ("left", 0, "minimum"), ("right", 0, "maximum")):
            self.moving.translation = (0.0, 0.0, 0.0)
            align_region_surface(self.moving, self.reference, surface)
            self.assertAlmostEqual(
                getattr(transformed_region_bounds(self.moving), attribute)[axis],
                getattr(transformed_region_bounds(self.reference), attribute)[axis],
            )

    def test_repeat_region_creates_independent_lattice_translated_regions(self):
        original_translation = self.moving.translation
        source_atom_count = len(self.source.atoms)
        duplicates = repeat_region(self.device, self.moving.id, 2, 2, 1)
        self.assertEqual(len(duplicates), 3)
        self.assertEqual(len({region.id for region in self.device.regions}), len(self.device.regions))
        self.assertEqual(self.moving.translation, original_translation)
        self.assertEqual(len(self.source.atoms), source_atom_count)
        self.assertTrue(all(region.role == self.moving.role and region.visible == self.moving.visible for region in duplicates))
        translations = {tuple(np.round(region.translation, 12)) for region in duplicates}
        self.assertEqual(translations, {(5.0, 0.0, 0.0), (0.0, 7.0, 0.0), (5.0, 7.0, 0.0)})
        with self.assertRaises(ValueError):
            repeat_region(self.device, self.moving.id, 11, 1, 1)

    def test_fit_cell_encloses_device_with_padding_without_changing_relative_transforms(self):
        before_translations = [region.translation for region in self.device.regions]
        before_difference = np.asarray(self.reference.translation) - np.asarray(self.moving.translation)
        fit_device_cell(self.device, padding=(1.0, 2.0, 3.0))
        assembled = assemble_device(self.device).structure
        positions = np.asarray([(atom.x, atom.y, atom.z) for atom in assembled.atoms])
        np.testing.assert_allclose(positions.min(axis=0), (1.0, 2.0, 3.0), atol=1e-12)
        np.testing.assert_allclose(
            np.diag(np.asarray(self.device.cell)),
            positions.max(axis=0) - positions.min(axis=0) + (2.0, 4.0, 6.0),
            atol=1e-12,
        )
        self.assertEqual([region.translation for region in self.device.regions], before_translations)
        np.testing.assert_allclose(np.asarray(self.reference.translation) - np.asarray(self.moving.translation), before_difference)
        self.assertEqual(self.device.periodic, (True, False, True))
        self.assertTrue(validate_device(self.device, assembled_structure=assembled).valid)

    def test_collisions_are_inter_region_only_structured_and_non_mutating(self):
        single = structure(points=((0.0, 0.0, 0.0),))
        device = Device(name="Collision Device")
        first = device.add_region(DeviceRegion(single, name="First"))
        second = device.add_region(DeviceRegion(single, name="Second"))
        before = [(region.translation, region.source_structure.to_dict()) for region in device.regions]
        collisions = detect_inter_region_collisions(device)
        self.assertEqual(len(collisions), 1)
        collision = collisions[0]
        self.assertEqual({collision.region_a_id, collision.region_b_id}, {first.id, second.id})
        self.assertEqual((collision.atom_a_index, collision.atom_b_index), (0, 0))
        self.assertAlmostEqual(collision.distance, 0.0)
        self.assertAlmostEqual(collision.threshold, DEFAULT_COLLISION_SCALE * 2.0 * covalent_radius("C"))
        self.assertEqual([(region.translation, region.source_structure.to_dict()) for region in device.regions], before)
        second.translation = (10.0, 0.0, 0.0)
        self.assertEqual(detect_inter_region_collisions(device), ())
        self.assertEqual(detect_inter_region_collisions(Device(name="Single", regions=[first])), ())
        second.translation = (0.0, 0.0, 0.0)
        validation = validate_device(device, check_collisions=True)
        self.assertTrue(validation.valid)
        self.assertTrue(any("overlap" in warning for warning in validation.warnings))

    def test_validation_reports_empty_invalid_geometry_and_outside_explicit_cell(self):
        self.assertFalse(validate_device(Device(name="Empty")).valid)
        self.device.padding = (-1.0, 0.0, 0.0)
        self.assertFalse(validate_device(self.device).valid)
        invalid_pbc = Device(name="Invalid PBC", periodic=(1, False, False))
        invalid_pbc.add_region(DeviceRegion(self.source))
        self.assertFalse(validate_device(invalid_pbc).valid)
        outside = Device(name="Outside", cell=[[2.0, 0.0, 0.0], [0.0, 2.0, 0.0], [0.0, 0.0, 2.0]])
        outside.add_region(DeviceRegion(structure(points=((5.0, 0.0, 0.0),))))
        warning_result = validate_device(outside, assembled_structure=assemble_device(outside).structure)
        self.assertTrue(any("outside" in warning for warning in warning_result.warnings))
