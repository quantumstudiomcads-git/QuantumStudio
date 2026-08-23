import unittest

import numpy as np
from ase import Atoms

from frontend.structure_io import StructureIO
from frontend.structure_operations import (
    _apply_2d_lattice_target,
    add_vacuum,
    apply_strain,
    create_heterostructure,
    create_supercell,
)

def square_layer(a=3.0, z=0.0):
    return Atoms(
        "C",
        positions=[(0.25 * a, 0.25 * a, z)],
        cell=[(a, 0.0, 0.0), (0.0, a, 0.0), (0.0, 0.0, 20.0)],
        pbc=True,
    )


class StructureOperationsTests(unittest.TestCase):

    def test_apply_2d_lattice_target_preserves_z(self):
        atoms = square_layer()
        old_cell = atoms.cell.array.copy()
        old_z = atoms.get_positions()[:, 2].copy()
        target = np.array([[3.2, 0.4, 0.0], [-0.2, 3.1, 0.0]])

        result = _apply_2d_lattice_target(atoms, target)

        np.testing.assert_allclose(result.cell.array[:2, :2], target[:, :2])
        np.testing.assert_allclose(result.cell.array[2], old_cell[2])
        np.testing.assert_allclose(result.get_positions()[:, 2], old_z)
        self.assertTrue(np.isfinite(result.get_positions()).all())

    def test_apply_2d_lattice_target_rejects_invalid_geometry(self):
        atoms = square_layer()
        with self.assertRaisesRegex(ValueError, r"shape \(2, 3\)"):
            _apply_2d_lattice_target(atoms, np.zeros((2, 2)))
        with self.assertRaisesRegex(ValueError, "planar"):
            _apply_2d_lattice_target(atoms, np.array([[3.0, 0.0, 0.1], [0.0, 3.0, 0.0]]))

    def test_identical_heterostructure(self):
        result = create_heterostructure(
            square_layer(), square_layer(), max_index=1, max_strain=0.01,
            interlayer_distance=3.4, vacuum=5.0,
        )
        self.assertIsInstance(result, Atoms)
        self.assertAlmostEqual(result.info["heterostructure_strain_bottom"], 0.0)
        self.assertAlmostEqual(result.info["heterostructure_strain_top"], 0.0)
        self.assertTrue(np.isfinite(result.get_positions()).all())
        self.assertGreater(abs(np.linalg.det(result.cell.array[:2, :2])), 1e-10)
        z = result.get_positions()[:, 2]
        self.assertAlmostEqual(z.max() - z.min(), 3.4, places=10)

    def test_slightly_mismatched_heterostructure(self):
        result = create_heterostructure(
            square_layer(3.0), square_layer(3.1), max_index=2, max_strain=0.05,
            vacuum=5.0,
        )
        self.assertIsInstance(result, Atoms)
        self.assertIn("heterostructure_mismatch", result.info)
        self.assertIn("heterostructure_matrix_bottom", result.info)
        self.assertIn("heterostructure_matrix_top", result.info)
        self.assertGreater(abs(np.linalg.det(result.cell.array[:2, :2])), 1e-10)
        self.assertTrue(np.isfinite(result.get_positions()).all())

    def test_existing_basic_operations_still_work(self):
        base = square_layer()
        supercell = create_supercell(base, 2, 1, 1)
        self.assertEqual(len(supercell), 2 * len(base))
        strained = apply_strain(base, strain_x=0.01, strain_y=0.02)
        self.assertTrue(np.isfinite(strained.cell.array).all())
        vacuum = add_vacuum(base, vacuum=2.0, axis=2)
        self.assertGreater(np.linalg.norm(vacuum.cell.array[2]), np.linalg.norm(base.cell.array[2]))

    def test_heterostructure_ase_to_native_handoff(self):
        result = create_heterostructure(
            square_layer(), square_layer(), max_index=1, max_strain=0.01,
        )
        native = StructureIO.from_ase(result, name="test heterostructure")
        self.assertEqual(len(native.atoms), len(result))
        self.assertEqual(len(native.cell), 3)
        self.assertTrue(all(np.isfinite([atom.x, atom.y, atom.z]).all() for atom in native.atoms))


if __name__ == "__main__":
    unittest.main()
