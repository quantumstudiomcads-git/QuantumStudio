import tempfile
import time
import unittest

import numpy as np
from ase import Atoms

from frontend.project import Project
from frontend.structure_io import StructureIO
from frontend.structure_operations import (
    _find_best_2d_match_with_statistics,
    create_heterostructure,
    find_best_2d_match,
)


def square_layer(a=3.0, z=0.0):
    return Atoms(
        "C",
        positions=[(0.25 * a, 0.25 * a, z)],
        cell=[(a, 0.0, 0.0), (0.0, a, 0.0), (0.0, 0.0, 20.0)],
        pbc=True,
    )


def hexagonal_layer(a=3.0):
    return Atoms(
        "C",
        positions=[(0.0, 0.0, 0.0)],
        cell=[
            (a, 0.0, 0.0),
            (0.5 * a, np.sqrt(3.0) * a / 2.0, 0.0),
            (0.0, 0.0, 20.0),
        ],
        pbc=True,
    )


class HeterostructureMatcherTests(unittest.TestCase):

    def test_identical_square_prefers_primitive_identity(self):
        match = find_best_2d_match(
            square_layer(), square_layer(), max_index=2, max_strain=0.0,
        )
        np.testing.assert_array_equal(match.matrix_a, np.eye(2, dtype=int))
        np.testing.assert_array_equal(match.matrix_b, np.eye(2, dtype=int))
        self.assertAlmostEqual(match.max_principal_strain, 0.0, places=12)
        self.assertAlmostEqual(match.cartesian_residual, 0.0, places=12)
        self.assertAlmostEqual(match.residual_rotation_deg, 0.0, places=12)

    def test_identical_hexagonal_prefers_primitive_identity(self):
        match = find_best_2d_match(
            hexagonal_layer(), hexagonal_layer(), max_index=2, max_strain=0.0,
        )
        np.testing.assert_array_equal(match.matrix_a, np.eye(2, dtype=int))
        np.testing.assert_array_equal(match.matrix_b, np.eye(2, dtype=int))
        self.assertAlmostEqual(match.max_principal_strain, 0.0, places=12)

    def test_one_percent_mismatch_has_principal_strain_diagnostics(self):
        match = find_best_2d_match(
            square_layer(3.00), square_layer(3.03), max_index=1, max_strain=0.01,
        )
        expected_a = np.sqrt(1.01) - 1.0
        expected_b = 1.0 / np.sqrt(1.01) - 1.0
        np.testing.assert_allclose(match.principal_strains_a, [expected_a, expected_a])
        np.testing.assert_allclose(match.principal_strains_b, [expected_b, expected_b])
        self.assertAlmostEqual(match.max_principal_strain, expected_a, places=12)

    def test_known_hexagonal_commensurate_orientation_uses_det_seven(self):
        a = 3.0
        angle = np.degrees(np.arccos(13.0 / 14.0))
        basis = np.array([[a, 0.0], [0.5 * a, np.sqrt(3.0) * a / 2.0]])
        match, _statistics = _find_best_2d_match_with_statistics(
            hexagonal_layer(), hexagonal_layer(), max_index=3, max_strain=1e-8,
            target_angle_deg=angle,
        )
        self.assertEqual(match.determinant_a, 7)
        self.assertEqual(match.determinant_b, 7)
        self.assertAlmostEqual(match.max_principal_strain, 0.0, places=12)
        self.assertAlmostEqual(match.residual_rotation_deg, 0.0, places=12)

    def test_insufficient_strain_returns_clear_no_match(self):
        with self.assertRaisesRegex(RuntimeError, "No commensurate orientation-preserving"):
            find_best_2d_match(
                square_layer(3.00), square_layer(3.03), max_index=1, max_strain=0.004,
            )

    def test_left_handed_cell_is_rejected(self):
        left_handed = Atoms(
            "C", positions=[(0.0, 0.0, 0.0)],
            cell=[(3.0, 0.0, 0.0), (0.0, -3.0, 0.0), (0.0, 0.0, 20.0)],
            pbc=True,
        )
        with self.assertRaisesRegex(ValueError, "left-handed"):
            find_best_2d_match(left_handed, square_layer(), max_index=1)

    def test_deterministic_result_and_bounded_local_search(self):
        results = [
            _find_best_2d_match_with_statistics(
                square_layer(3.0), square_layer(3.03), max_index=3, max_strain=0.01,
            )
            for _ in range(3)
        ]
        first_match, first_stats = results[0]
        for match, stats in results[1:]:
            np.testing.assert_array_equal(match.matrix_a, first_match.matrix_a)
            np.testing.assert_array_equal(match.matrix_b, first_match.matrix_b)
            self.assertEqual(stats.hnf_candidates, first_stats.hnf_candidates)
            self.assertEqual(stats.local_integer_candidates, first_stats.local_integer_candidates)
        self.assertEqual(first_stats.local_integer_candidates, 2 * 81 * first_stats.hnf_candidates)
        self.assertLess(first_stats.unique_matrix_pairs, first_stats.local_integer_candidates)
        self.assertLessEqual(first_stats.full_diagnostic_evaluations, first_stats.unique_matrix_pairs)

    def test_impossible_request_returns_quickly(self):
        started = time.perf_counter()
        with self.assertRaisesRegex(RuntimeError, "No commensurate orientation-preserving"):
            find_best_2d_match(
                square_layer(3.0), square_layer(4.0), max_index=1, max_strain=0.001,
            )
        self.assertLess(time.perf_counter() - started, 1.0)

    def test_strain_modes_and_layer_geometry(self):
        expected_balanced = np.sqrt(1.01) - 1.0
        expected_bottom = 0.01
        common = dict(
            interlayer_distance=3.4,
            max_index=1,
            max_strain=0.01,
            vacuum=5.0,
        )
        balanced = create_heterostructure(
            square_layer(3.0), square_layer(3.03), strain_mode="balanced", **common,
        )
        bottom = create_heterostructure(
            square_layer(3.0), square_layer(3.03), strain_mode="bottom", **common,
        )
        top = create_heterostructure(
            square_layer(3.0), square_layer(3.03), strain_mode="top", **common,
        )
        self.assertAlmostEqual(
            max(abs(value) for value in balanced.info["heterostructure_principal_strain_A"]),
            expected_balanced,
            places=12,
        )
        self.assertAlmostEqual(
            max(abs(value) for value in bottom.info["heterostructure_principal_strain_B"]),
            0.0,
            places=12,
        )
        self.assertAlmostEqual(
            max(abs(value) for value in bottom.info["heterostructure_principal_strain_A"]),
            expected_bottom,
            places=12,
        )
        self.assertAlmostEqual(
            max(abs(value) for value in top.info["heterostructure_principal_strain_A"]),
            0.0,
            places=12,
        )
        self.assertEqual(balanced.info["heterostructure_final_atom_count"], len(balanced))
        self.assertEqual(balanced.pbc.tolist(), [True, True, False])
        z = balanced.get_positions()[:, 2]
        self.assertAlmostEqual(z.max() - z.min(), 3.4, places=12)
        self.assertAlmostEqual(balanced.cell.array[2, 2], 13.4, places=12)

    def test_generated_structure_round_trips_through_project_file(self):
        result = create_heterostructure(
            square_layer(), square_layer(), max_index=1, max_strain=0.0,
            interlayer_distance=3.4, vacuum=5.0,
        )
        native = StructureIO.from_ase(result, name="heterostructure")
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = f"{temporary_directory}/heterostructure.qs"
            project = Project("heterostructure", path)
            project.set_structure(native)
            project.save()
            reopened = Project.load(path).get_structure()
        self.assertEqual(len(reopened.atoms), len(native.atoms))
        self.assertEqual(reopened.periodic, [True, True, False])

    def test_metadata_and_native_handoff(self):
        result = create_heterostructure(
            square_layer(), square_layer(), max_index=1, max_strain=0.0,
            interlayer_distance=3.4, vacuum=5.0,
        )
        for field in (
            "heterostructure_det_A",
            "heterostructure_det_B",
            "heterostructure_requested_orientation",
            "heterostructure_principal_strain_A",
            "heterostructure_principal_strain_B",
            "heterostructure_max_principal_strain",
            "heterostructure_cartesian_residual",
            "heterostructure_residual_rotation_deg",
            "heterostructure_estimated_atom_count",
        ):
            self.assertIn(field, result.info)
        self.assertTrue(np.isfinite(result.get_positions()).all())
        self.assertGreater(abs(np.linalg.det(result.cell.array[:2, :2])), 1e-12)
        native = StructureIO.from_ase(result, name="heterostructure")
        self.assertEqual(len(native.atoms), len(result))


if __name__ == "__main__":
    unittest.main()
