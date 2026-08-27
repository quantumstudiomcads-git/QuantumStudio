import unittest

from backend.compiler.calculation_compiler import CalculationCompiler
from backend.core.calculation_request import CalculationRequest
from backend.engines.qe.hybrid_bands import (
    hybrid_band_contract, validate_hybrid_kpoint_capacity,
)
from backend.engines.qe.models import InvalidQEParameterError
from backend.execution.diagnostics import extract_qe_failure
from frontend.calculate.parameter_session import preset_parameters


STRUCTURE = {
    "periodic": [True, True, True],
    "cell": [[5.4, 0, 0], [0, 5.4, 0], [0, 0, 5.4]],
    "atoms": [{"element": "Si", "x": 0.0, "y": 0.0, "z": 0.0}],
}
PATH_201 = [
    {"label": "G", "coordinates": [0, 0, 0], "points": 200},
    {"label": "X", "coordinates": [0.5, 0, 0], "points": 200},
]


class ManualValidationHotfixTests(unittest.TestCase):
    def test_fresh_ordinary_defaults_are_pbe(self):
        self.assertEqual(preset_parameters(["scf"], "INTERMEDIATE")["functional"], "PBE")
        self.assertEqual(preset_parameters(["bands"], "INTERMEDIATE")["functional"], "PBE")

    def test_hybrid_custom_parameters_do_not_mutate_new_defaults(self):
        hybrid = preset_parameters(["scf"], "CUSTOM", {"functional": "HSE06"})
        self.assertEqual(hybrid["functional"], "HSE06")
        self.assertEqual(preset_parameters(["scf"], "INTERMEDIATE")["functional"], "PBE")

    def test_explicit_hybrid_functionals_remain_selected(self):
        for functional in ("hse06", "b3lyp"):
            request = CalculationRequest(STRUCTURE, ["scf"], parameters={"functional": functional})
            plan = CalculationCompiler(request).compile()
            self.assertEqual(plan.tasks[0].parameters["functional"], functional)

    def test_hybrid_capacity_blocks_real_failure_case(self):
        contract = hybrid_band_contract(PATH_201, [6, 6, 6], STRUCTURE["periodic"])
        with self.assertRaisesRegex(InvalidQEParameterError, "43,416"):
            validate_hybrid_kpoint_capacity(contract)

    def test_fitting_hybrid_and_scalar_bands_are_not_blocked(self):
        fitting = hybrid_band_contract(PATH_201, [5, 5, 5], STRUCTURE["periodic"])
        self.assertEqual(validate_hybrid_kpoint_capacity(fitting), 25125)
        scalar = hybrid_band_contract(PATH_201, [6, 6, 6], STRUCTURE["periodic"])
        self.assertEqual(validate_hybrid_kpoint_capacity(scalar, max_kpoints=50000), 43416)

    def test_qe_fatal_diagnostic_precedes_mpi_abort(self):
        stdout = """%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%\nError in routine add_kpoint (1):\nMaximum number of k-points exceeded: increase npk in pwcom\n%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%\nstopping ...\n"""
        stderr = "MPI_ABORT was invoked on rank 0 in communicator MPI_COMM_WORLD\n"
        message = extract_qe_failure(stdout, stderr, 1)
        self.assertIn("Error in routine add_kpoint", message)
        self.assertIn("Maximum number of k-points exceeded", message)
        self.assertNotIn("MPI_ABORT", message)

    def test_mpi_abort_is_fallback(self):
        message = extract_qe_failure("", "MPI_ABORT was invoked on rank 0", 1)
        self.assertIn("MPI_ABORT", message)


if __name__ == "__main__":
    unittest.main()
