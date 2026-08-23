import math
import tempfile
import time
import unittest

import numpy as np
from ase import Atoms

from frontend.project import Project
from frontend.structure_io import StructureIO
from frontend.structure_operations import (
    _rotate_planar_lattice,
    create_moire_structure,
    create_supercell,
)


def square_layer(a=3.0, position=(0.0, 0.0, 0.0)):
    return Atoms(
        "C", positions=[position],
        cell=[(a, 0.0, 0.0), (0.0, a, 0.0), (0.0, 0.0, 20.0)], pbc=True,
    )


def hexagonal_layer(a=3.0):
    return Atoms(
        "C", positions=[(0.0, 0.0, 0.0)],
        cell=[
            (a, 0.0, 0.0),
            (0.5 * a, np.sqrt(3.0) * a / 2.0, 0.0),
            (0.0, 0.0, 20.0),
        ], pbc=True,
    )


class MoireStructureTests(unittest.TestCase):

    KNOWN_TWIST_DEG = math.degrees(math.acos(13.0 / 14.0))

    def test_zero_angle_identical_square_is_primitive_aligned_bilayer(self):
        result = create_moire_structure(
            square_layer(), square_layer(), twist_angle=0.0, max_index=1,
            max_strain=0.0, interlayer_distance=3.4, vacuum=5.0,
        )
        self.assertEqual(result.info["quantum_studio_operation"], "moire")
        self.assertEqual(result.info["moire_matrix_A"], [[1, 0], [0, 1]])
        self.assertEqual(result.info["moire_matrix_B"], [[1, 0], [0, 1]])
        self.assertEqual(result.info["moire_det_A"], 1)
        self.assertEqual(result.info["moire_det_B"], 1)
        self.assertAlmostEqual(result.info["moire_max_principal_strain"], 0.0, places=12)
        self.assertAlmostEqual(result.info["moire_residual_rotation_deg"], 0.0, places=12)
        self.assertEqual(result.pbc.tolist(), [True, True, False])
        self.assertAlmostEqual(result.cell.array[2, 2], 13.4, places=12)
        self.assertAlmostEqual(np.ptp(result.positions[:, 2]), 3.4, places=12)
        self.assertEqual(len(result), 2)

    def test_zero_angle_identical_hexagonal_is_primitive_aligned_bilayer(self):
        result = create_moire_structure(
            hexagonal_layer(), hexagonal_layer(), twist_angle=0.0, max_index=1,
            max_strain=0.0, interlayer_distance=3.4, vacuum=5.0,
        )
        self.assertEqual(result.info["moire_matrix_A"], [[1, 0], [0, 1]])
        self.assertEqual(result.info["moire_matrix_B"], [[1, 0], [0, 1]])
        self.assertEqual(result.info["moire_final_atom_count"], 2)
        self.assertGreater(abs(np.linalg.det(result.cell.array[:2, :2])), 1e-12)

    def test_known_commensurate_hexagonal_twist(self):
        result = create_moire_structure(
            hexagonal_layer(), hexagonal_layer(), twist_angle=self.KNOWN_TWIST_DEG,
            max_index=3, max_strain=1e-8, interlayer_distance=3.4, vacuum=5.0,
        )
        matrix_a = np.asarray(result.info["moire_matrix_A"], dtype=int)
        matrix_b = np.asarray(result.info["moire_matrix_B"], dtype=int)
        a = hexagonal_layer().cell.array[:2, :2]
        b_theta = _rotate_planar_lattice(a, self.KNOWN_TWIST_DEG)
        np.testing.assert_allclose(matrix_a @ a, matrix_b @ b_theta, atol=1e-10)
        self.assertEqual(result.info["moire_det_A"], 7)
        self.assertEqual(result.info["moire_det_B"], 7)
        self.assertAlmostEqual(result.info["moire_max_principal_strain"], 0.0, places=12)
        self.assertAlmostEqual(result.info["moire_residual_rotation_deg"], 0.0, places=12)
        self.assertAlmostEqual(result.info["moire_requested_twist_deg"], self.KNOWN_TWIST_DEG, places=12)
        self.assertAlmostEqual(result.info["moire_achieved_twist_deg"], self.KNOWN_TWIST_DEG, places=12)
        self.assertEqual(result.info["moire_final_atom_count"], 14)
        self.assertTrue(np.isfinite(result.positions).all())
        self.assertGreater(abs(np.linalg.det(result.cell.array[:2, :2])), 1e-12)

    def test_requested_twist_is_applied_once_to_atomic_geometry(self):
        result = create_moire_structure(
            square_layer(position=(0.0, 0.0, 0.0)),
            square_layer(position=(0.5, 0.0, 0.0)),
            twist_angle=90.0, max_index=2, max_strain=1e-8, vacuum=5.0,
        )
        # The second atom is the top layer's only atom.  Its non-deformed XY
        # location is the one physical +90-degree rotation of (0.5, 0.0).
        np.testing.assert_allclose(result.positions[1, :2], [0.0, 0.5], atol=1e-10)
        self.assertAlmostEqual(result.info["moire_requested_twist_deg"], 90.0)
        self.assertAlmostEqual(result.info["moire_residual_rotation_deg"], 0.0, places=10)

    def test_repeated_known_solution_is_deterministic(self):
        outputs = [
            create_moire_structure(
                hexagonal_layer(), hexagonal_layer(), twist_angle=self.KNOWN_TWIST_DEG,
                max_index=3, max_strain=1e-8, vacuum=5.0,
            )
            for _ in range(3)
        ]
        first = outputs[0].info
        for result in outputs[1:]:
            self.assertEqual(result.info["moire_matrix_A"], first["moire_matrix_A"])
            self.assertEqual(result.info["moire_matrix_B"], first["moire_matrix_B"])
            self.assertEqual(result.info["moire_det_A"], first["moire_det_A"])
            self.assertEqual(result.info["moire_det_B"], first["moire_det_B"])

    def test_insufficient_search_budget_returns_clear_no_match(self):
        with self.assertRaisesRegex(RuntimeError, "No commensurate orientation-preserving"):
            create_moire_structure(
                hexagonal_layer(), hexagonal_layer(), twist_angle=self.KNOWN_TWIST_DEG,
                max_index=2, max_strain=1e-8,
            )

    def test_excessive_strain_returns_clear_no_match(self):
        with self.assertRaisesRegex(RuntimeError, "No commensurate orientation-preserving"):
            create_moire_structure(
                square_layer(3.0), square_layer(3.03), twist_angle=0.0,
                max_index=1, max_strain=0.004,
            )

    def test_strict_residual_rotation_rejection_returns_quickly(self):
        started = time.perf_counter()
        with self.assertRaisesRegex(RuntimeError, "No commensurate orientation-preserving"):
            create_moire_structure(
                hexagonal_layer(), hexagonal_layer(), twist_angle=0.02,
                max_index=1, max_strain=0.01,
            )
        self.assertLess(time.perf_counter() - started, 1.0)

    def test_handoff_project_roundtrip_and_following_build_operation(self):
        result = create_moire_structure(
            hexagonal_layer(), hexagonal_layer(), twist_angle=self.KNOWN_TWIST_DEG,
            max_index=3, max_strain=1e-8, vacuum=5.0,
        )
        native = StructureIO.from_ase(result, name="moire")
        self.assertEqual(len(native.atoms), len(result))
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_path = f"{temporary_directory}/moire.qs"
            project = Project("moire", project_path)
            project.set_structure(native)
            project.save()
            reopened = Project.load(project_path).get_structure()
        self.assertEqual(len(reopened.atoms), len(native.atoms))
        self.assertEqual(reopened.periodic, [True, True, False])
        following = create_supercell(result, 1, 1, 1)
        self.assertEqual(len(following), len(result))


if __name__ == "__main__":
    unittest.main()
