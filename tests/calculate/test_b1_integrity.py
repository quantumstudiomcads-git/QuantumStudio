import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from backend.results.models import ResultProvenance, ResultStatus, ScientificResult
from backend.results.store import ResultStore
from frontend.core.project import Project


class B1IntegrityTests(unittest.TestCase):
    def test_project_save_is_atomic_and_round_trips(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "project.qs"
            project = Project("B1", path)
            project.structure = {"atoms": [], "cell": []}
            project.save()
            self.assertEqual(Project.load(path).name, "B1")
            self.assertFalse(list(Path(directory).glob("*.tmp")))

    def test_result_store_round_trip_uses_json_and_npz(self):
        provenance = ResultProvenance("request", "execution", "task", "internal", "parser", (), {}, "fixture")
        result = ScientificResult("FixtureResult", ResultStatus.VALID, provenance, arrays={"x": np.array([1.0, 2.0])})
        with tempfile.TemporaryDirectory() as directory:
            store = ResultStore(directory, "execution")
            store.save(result)
            loaded = store.load(result.result_id)
            self.assertTrue(np.array_equal(loaded.arrays["x"], result.arrays["x"]))
            self.assertTrue((Path(directory) / "executions/execution/results" / f"{result.result_id}.json").is_file())

    def test_b1_report_is_machine_readable_and_declares_zero_launches(self):
        from scripts.audit.b1_product_integrity import build_report
        report = build_report()
        self.assertFalse(report["engine_execution"]["launched"])
        self.assertIn("catalog", report)
