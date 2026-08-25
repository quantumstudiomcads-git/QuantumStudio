import tempfile
import unittest

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QComboBox, QSpinBox
from pathlib import Path

from backend.execution import ExecutionStore
from backend.execution.models import TaskExecutionRecord, TaskState, WorkflowExecutionRecord
from frontend.builder.brillouin_zone.path_api import materialize_path, recommended_band_path
from frontend.calculate.band_path_dialog import BandPathDialog
from frontend.calculate.functional_pseudo_dialog import FunctionalPseudoDialog
from frontend.calculate.results_dialog import ResultsDialog
from frontend.services.result_service import ResultService


class C9PUserFlowTests(unittest.TestCase):
    def _app(self):
        return QApplication.instance() or QApplication([])

    def test_cubic_recommendation_preserves_repeated_gamma(self):
        recommendation = recommended_band_path({"cell": [[4, 0, 0], [0, 4, 0], [0, 0, 4]], "periodic": [True, True, True]})
        path = materialize_path(recommendation.segments, (True,) * len(recommendation.segments), 40)
        self.assertEqual(recommendation.bravais_label, "Cubic")
        self.assertEqual([point["label"] for point in path], ["Γ", "X", "W", "K", "Γ", "L"])

    def test_disconnected_bz_segments_are_rejected(self):
        recommendation = recommended_band_path({"cell": [[4, 0, 0], [0, 4, 0], [0, 0, 4]], "periodic": [True, True, True]})
        with self.assertRaises(ValueError):
            materialize_path(recommendation.segments, (True, False, True, False, False), 20)

    def test_result_service_parses_current_completed_attempt_stdout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); task_directory = root / "001_scf"; task_directory.mkdir()
            output = task_directory / "scf.out.attempt002"
            output.write_text("!    total energy = -10.0 Ry\nconvergence has been achieved\n")
            (root / "manifest.json").write_text('{"tasks":[{"task_id":"scf-task","semantic_task_type":"scf","working_directory":"001_scf"}]}')
            record = WorkflowExecutionRecord("request", str(root), {"scf-task": TaskExecutionRecord("scf-task", state=TaskState.COMPLETED, stdout_path=str(output), attempt_count=2)}, execution_id="attempt-two")
            ExecutionStore(root).save(record)
            service = ResultService(); parsed = service.parse(root, "attempt-two")
            self.assertEqual(len(parsed["parsed"]), 1)
            self.assertEqual(service.summaries(root, "attempt-two")[0]["status"], "VALID")

    def test_result_service_never_uses_missing_old_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); directory = root / "001_scf"; directory.mkdir()
            (root / "manifest.json").write_text('{"tasks":[{"task_id":"scf-task","semantic_task_type":"scf","working_directory":"001_scf"}]}')
            record = WorkflowExecutionRecord("request", str(root), {"scf-task": TaskExecutionRecord("scf-task", state=TaskState.COMPLETED, stdout_path=str(directory / "scf.out.attempt002"), attempt_count=2)}, execution_id="attempt-two")
            ExecutionStore(root).save(record)
            outcome = ResultService().parse(root, "attempt-two")
            self.assertFalse(outcome["parsed"])
            self.assertIn("source is missing", outcome["errors"][0])

    def test_offscreen_structured_dialogs_use_combos_and_mesh_spins(self):
        self._app()
        functional = FunctionalPseudoDialog({"xc_functional": "hse06", "kpoints": [4, 4, 1]}, ["Si"])
        self.assertIsInstance(functional.family, QComboBox)
        self.assertTrue(all(isinstance(box, QSpinBox) for box in functional.mesh_boxes))
        functional.family.setCurrentText("GGA")
        self.assertFalse(functional.exx.isVisible())
        band = BandPathDialog({"cell": [[4, 0, 0], [0, 4, 0], [0, 0, 4]], "periodic": [True, True, True]})
        self.assertEqual(len(band._checks), 5)
        self.assertIn("Γ", band.preview.text())

    def test_results_dialog_lists_execution_without_loading_arrays(self):
        self._app()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "manifest.json").write_text('{"tasks":[]}')
            ExecutionStore(root).save(WorkflowExecutionRecord("request", str(root), {}, execution_id="abc123"))
            dialog = ResultsDialog(ResultService(), root)
            self.assertEqual(dialog.execution.currentData(), "abc123")
            self.assertIn("Results not parsed", dialog.state.text())
