import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from backend.results.transport import parse_transport_result

from frontend.calculate.typed_parameter_controls import control_value, make_control
from frontend.calculations.catalog import CALCULATIONS
from frontend.services.calculation_service import CalculationService


class TransportGuiAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
    def test_partial_transport_entry_is_addable_through_service(self):
        descriptor = CalculationService(CALCULATIONS).validate_selected_calculations(["seebeck"])[0]
        self.assertEqual(descriptor.id, "seebeck")

    def test_configure_preserves_typed_transport_values(self):
        temperatures = make_control("temperatures", "[300.0]")
        model = make_control("relaxation_time_model", "UNSPECIFIED_RELAXATION_TIME")
        self.assertEqual(control_value("temperatures", temperatures), [300.0])
        self.assertEqual(control_value("relaxation_time_model", model), "UNSPECIFIED_RELAXATION_TIME")

    def test_transport_parser_accepts_standard_parser_context(self):
        import json
        import tempfile
        import numpy as np
        with tempfile.TemporaryDirectory() as directory:
            payload = {
                "temperatures_K": [300.0], "chemical_potential_eV": [0.0],
                "carrier_concentration_cm3": [[0.0]],
                "electrical_conductivity_over_tau": np.zeros((1, 1, 3, 3)).tolist(),
                "seebeck": np.zeros((1, 1, 3, 3)).tolist(),
                "electronic_thermal_conductivity_over_tau": np.zeros((1, 1, 3, 3)).tolist(),
                "units": {"temperature": "K"}, "method_assumptions": {"energy_reference": "QE Fermi reference"},
            }
            path = os.path.join(directory, "transport.json")
            with open(path, "w", encoding="utf-8") as stream:
                json.dump(payload, stream)
            result = parse_transport_result(path, method_metadata={"spin_treatment": "SCALAR_NONSPIN"})
            self.assertEqual(result.result_type, "TransportResult")


if __name__ == "__main__":
    unittest.main()
