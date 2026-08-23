import unittest

import numpy as np
from ase import Atoms

from frontend.structure_operations import (
    _candidate_rank_key,
    _cartesian_match_diagnostics,
    _cartesian_supercell_2d,
    _deformation_gradient_2d,
    _enumerate_row_hnf_2d,
    _extract_planar_2d_cell,
    _polar_strain_diagnostics,
    _reduce_2d_row_basis,
    _rotate_planar_lattice,
)


def square_lattice(a=3.0):
    return np.array([[a, 0.0], [0.0, a]])


def hexagonal_lattice(a=3.0):
    return np.array([[a, 0.0], [0.5 * a, np.sqrt(3.0) * a / 2.0]])


def planar_atoms(cell):
    return Atoms(
        "C",
        positions=[(0.0, 0.0, 0.0)],
        cell=[
            (cell[0, 0], cell[0, 1], 0.0),
            (cell[1, 0], cell[1, 1], 0.0),
            (0.0, 0.0, 20.0),
        ],
        pbc=True,
    )


class LatticeMatchingMathTests(unittest.TestCase):

    def test_planar_cell_extraction_and_invalid_geometry(self):
        np.testing.assert_allclose(
            _extract_planar_2d_cell(planar_atoms(square_lattice())),
            square_lattice(),
        )

        with self.assertRaisesRegex(ValueError, "singular"):
            _extract_planar_2d_cell(planar_atoms(np.array([[3.0, 0.0], [6.0, 0.0]])))

        nonplanar = Atoms(
            "C", positions=[(0.0, 0.0, 0.0)],
            cell=[(3.0, 0.0, 0.1), (0.0, 3.0, 0.0), (0.0, 0.0, 20.0)], pbc=True,
        )
        with self.assertRaisesRegex(ValueError, "planar XY"):
            _extract_planar_2d_cell(nonplanar)

        nonfinite = planar_atoms(square_lattice())
        nonfinite.cell.array[0, 0] = np.nan
        with self.assertRaisesRegex(ValueError, "finite"):
            _extract_planar_2d_cell(nonfinite)

    def test_row_vector_supercell_and_rotation_conventions(self):
        lattice = np.array([[3.0, 0.0], [0.0, 4.0]])
        supercell, determinant = _cartesian_supercell_2d(
            lattice, np.array([[2, 1], [0, 1]])
        )
        np.testing.assert_allclose(supercell, np.array([[6.0, 4.0], [0.0, 4.0]]))
        self.assertEqual(determinant, 2)

        rotated = _rotate_planar_lattice(square_lattice(), 90.0)
        np.testing.assert_allclose(
            rotated, np.array([[0.0, 3.0], [-3.0, 0.0]]), atol=1e-12
        )

    def test_deformation_gradient_row_convention(self):
        source = np.eye(2)
        target = np.array([[1.02, 0.0], [0.0, 0.97]])
        deformation = _deformation_gradient_2d(source, target)
        np.testing.assert_allclose(source @ deformation.T, target)

        point = np.array([[1.0, 2.0]])
        np.testing.assert_allclose(point @ deformation.T, np.array([[1.02, 1.94]]))

    def test_polar_strain_known_cases(self):
        identity = _polar_strain_diagnostics(np.eye(2))
        np.testing.assert_allclose(identity.principal_strains, [0.0, 0.0], atol=1e-12)
        self.assertAlmostEqual(identity.rotation_deg, 0.0, places=12)

        isotropic = _polar_strain_diagnostics(1.02 * np.eye(2))
        np.testing.assert_allclose(isotropic.principal_strains, [0.02, 0.02], atol=1e-12)

        anisotropic = _polar_strain_diagnostics(np.diag([1.02, 0.97]))
        np.testing.assert_allclose(anisotropic.principal_strains, [-0.03, 0.02], atol=1e-12)

        angle = np.deg2rad(37.0)
        rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
        rigid = _polar_strain_diagnostics(rotation)
        np.testing.assert_allclose(rigid.principal_strains, [0.0, 0.0], atol=1e-12)
        self.assertAlmostEqual(rigid.rotation_deg, 37.0, places=12)
        np.testing.assert_allclose(rigid.rotation_matrix @ rigid.stretch_tensor, rotation, atol=1e-12)

    def test_identity_square_and_hex_diagnostics(self):
        identity = np.eye(2, dtype=int)
        for lattice in (square_lattice(), hexagonal_lattice()):
            diagnostics = _cartesian_match_diagnostics(lattice, lattice, identity, identity)
            self.assertAlmostEqual(diagnostics.cartesian_residual, 0.0, places=12)
            self.assertAlmostEqual(diagnostics.metric_residual, 0.0, places=12)
            self.assertAlmostEqual(diagnostics.residual_rotation_deg, 0.0, places=12)
            self.assertAlmostEqual(diagnostics.strain_a_to_b.max_abs_strain, 0.0, places=12)
            self.assertEqual(diagnostics.atom_multiplier_a, 1)
            self.assertEqual(diagnostics.atom_multiplier_b, 1)

    def test_known_isotropic_mismatch_diagnostics(self):
        identity = np.eye(2, dtype=int)
        diagnostics = _cartesian_match_diagnostics(
            square_lattice(3.0), square_lattice(3.03), identity, identity
        )
        np.testing.assert_allclose(
            diagnostics.deformation_a_to_b, 1.01 * np.eye(2), atol=1e-12
        )
        np.testing.assert_allclose(
            diagnostics.strain_a_to_b.principal_strains, [0.01, 0.01], atol=1e-12
        )
        np.testing.assert_allclose(
            diagnostics.strain_b_to_a.principal_strains, [1.0 / 1.01 - 1.0] * 2, atol=1e-12
        )

    def test_pure_rotation_exposes_cartesian_orientation_error(self):
        identity = np.eye(2, dtype=int)
        diagnostics = _cartesian_match_diagnostics(
            square_lattice(), square_lattice(), identity, identity, rotation_deg=30.0
        )
        self.assertAlmostEqual(diagnostics.metric_residual, 0.0, places=12)
        self.assertGreater(diagnostics.cartesian_residual, 0.1)
        self.assertAlmostEqual(diagnostics.residual_rotation_deg, 30.0, places=12)
        self.assertAlmostEqual(diagnostics.strain_a_to_b.max_abs_strain, 0.0, places=12)

    def test_hnf_enumeration_is_canonical_and_deterministic(self):
        expected_counts = {1: 1, 2: 4, 3: 8, 4: 15}
        for maximum, expected_count in expected_counts.items():
            first = _enumerate_row_hnf_2d(maximum)
            second = _enumerate_row_hnf_2d(maximum)
            self.assertEqual(len(first), expected_count)
            self.assertEqual([m.tolist() for m in first], [m.tolist() for m in second])
            self.assertEqual(first[0].tolist(), [[1, 0], [0, 1]])
            self.assertEqual(len({tuple(m.flatten()) for m in first}), len(first))
            for matrix in first:
                determinant = int(matrix[0, 0] * matrix[1, 1] - matrix[0, 1] * matrix[1, 0])
                self.assertGreater(determinant, 0)
                self.assertLessEqual(determinant, maximum)
                self.assertEqual(matrix[1, 0], 0)
                self.assertGreaterEqual(matrix[0, 1], 0)
                self.assertLess(matrix[0, 1], matrix[1, 1])

    def test_basis_reduction_and_candidate_ranking_are_deterministic(self):
        basis = np.array([[4.0, 0.0], [7.0, 3.0]])
        reduced, transform = _reduce_2d_row_basis(basis)
        np.testing.assert_allclose(reduced, transform @ basis)
        self.assertEqual(int(round(np.linalg.det(transform))), 1)

        lattice = square_lattice()
        identity = np.eye(2, dtype=int)
        doubled = 2 * identity
        identity_diagnostics = _cartesian_match_diagnostics(lattice, lattice, identity, identity)
        doubled_diagnostics = _cartesian_match_diagnostics(lattice, lattice, doubled, doubled)
        self.assertLess(
            _candidate_rank_key(identity_diagnostics, identity, identity),
            _candidate_rank_key(doubled_diagnostics, doubled, doubled),
        )


if __name__ == "__main__":
    unittest.main()
