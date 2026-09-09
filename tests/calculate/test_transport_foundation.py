import json
import tempfile
import unittest
import os
from pathlib import Path

import numpy as np

from backend.engines.boltztrap2 import discover, DenseElectronicState, DenseElectronicStateError
from backend.engines.boltztrap2 import BoltzTraP2WorkflowAdapter
from tests.calculate.test_boltztrap2_workflow import plan as btp_plan
from backend.results.transport import TransportParseError, parse_transport_result
from tests.helpers.fake_executable import write_fake_executable


def _artifact(root):
    shape = [2, 3, 3, 3]
    payload = {
        "temperatures_K": [300.0, 600.0],
        "chemical_potential_eV": [-0.1, 0.0, 0.1],
        "carrier_concentration_cm3": [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]],
        "electrical_conductivity_over_tau": np.ones(shape).tolist(),
        "seebeck": np.ones(shape).tolist(),
        "electronic_thermal_conductivity_over_tau": np.ones(shape).tolist(),
        "power_factor_over_tau": np.ones(shape).tolist(),
        "units": {"electrical_conductivity_over_tau": "S m-1 s-1", "seebeck": "V K-1", "electronic_thermal_conductivity_over_tau": "W m-1 K-1 s-1", "carrier_concentration_cm3": "cm-3", "chemical_potential_eV": "eV", "temperatures_K": "K"},
        "method_assumptions": {"backend": "BoltzTraP2", "relaxation_time": "unspecified"},
    }
    path = Path(root) / "transport.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class TransportFoundationTests(unittest.TestCase):
    def test_btp2_discovery_uses_installed_environment(self):
        with tempfile.TemporaryDirectory() as root:
            tool = write_fake_executable(Path(root) / "btp2", "print('BoltzTraP2 26.3.1')\n")
            installation = discover(environment={"PATH": str(Path(tool).parent)})
        self.assertIsNotNone(installation)
        self.assertRegex(installation.version, r"\d+\.\d+\.\d+")

    def test_structured_transport_result_parses_and_round_trips_to_result(self):
        with tempfile.TemporaryDirectory() as root:
            result = parse_transport_result(_artifact(root), request_id="r", execution_id="e", task_id="t")
            self.assertEqual(result.result_type, "TransportResult")
            self.assertEqual(result.arrays["seebeck"].shape, (2, 3, 3, 3))
            self.assertEqual(result.metadata["units"]["temperatures_K"], "K")

    def test_generated_tasks_use_isolated_shell_free_commands(self):
        tasks, _ = BoltzTraP2WorkflowAdapter().compile_plan(btp_plan(["seebeck"]))
        interpolate = tasks[-2].metadata["command"]
        integrate = tasks[-1].metadata["command"]
        self.assertEqual(interpolate[0], "btp2-python")
        self.assertEqual(interpolate[2], "interpolate")
        self.assertEqual(integrate[2], "integrate")
        self.assertNotIn("shell=True", interpolate)

    def test_dense_state_contract_rejects_dimension_mismatch(self):
        with self.assertRaises(DenseElectronicStateError):
            DenseElectronicState(np.eye(3), np.eye(3), np.zeros((2, 3)), np.ones(2), np.zeros((1, 3)), 0.0, 4.0, "SCALAR_NONSPIN", 2.0, 1.0, 3, 2, (True, True, True), {})

    def test_nonfinite_transport_values_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            path = _artifact(root)
            data = json.loads(path.read_text())
            data["seebeck"][0][0][0][0] = float("nan")
            path.write_text(json.dumps(data))
            with self.assertRaises(TransportParseError): parse_transport_result(path)


if __name__ == "__main__": unittest.main()
