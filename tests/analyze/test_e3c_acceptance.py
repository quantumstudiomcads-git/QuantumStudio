import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest
from pathlib import Path

import numpy as np
from PySide6.QtWidgets import QApplication

from backend.analyze.transforms import tabular_data
from backend.results import ResultProvenance, ResultStatus, ScientificResult
from frontend.analyze.plots.vibrational import IRPlot, LOTOPlot
from frontend.analyze.workspace import AnalyzeWorkspace
from frontend.core import Project


class E3CAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.provenance = ResultProvenance("request", "execution", "task", "qe", "dynmat.x", (), {}, "fixture")

    def loto(self):
        return ScientificResult(
            "LOTOResult", ResultStatus.VALID, self.provenance,
            arrays={
                "frequencies_uncorrected_cm1": np.array([24., 24., 24., 398., 398., 398.]),
                "frequencies_uncorrected_THz": np.array([.7, .7, .7, 11.9, 11.9, 11.9]),
                "frequencies_nonanalytic_cm1": np.array([0., 0., 0., 398., 398., 702.]),
                "frequencies_nonanalytic_THz": np.array([0., 0., 0., 11.9, 11.9, 21.0]),
                "frequency_shifts_cm1": np.array([-24., -24., -24., 0., 0., 304.]),
                "frequency_shifts_THz": np.array([-.7, -.7, -.7, 0., 0., 9.1]),
            },
            metadata={"direction_unit_cartesian": [1., 0., 0.], "classifications": ["ambiguous"] * 6},
        )

    def ir(self):
        return ScientificResult(
            "IRResult", ResultStatus.VALID, self.provenance,
            arrays={
                "frequencies_cm1": np.array([0., 0., 0., 398., 398., 702.]),
                "frequencies_THz": np.array([0., 0., 0., 11.9, 11.9, 21.0]),
                "native_ir_quantity": np.array([0., 0., 0., 9.1, 9.1, 9.1]),
                "activity_mask": np.array([False, False, False, True, True, True]),
            },
            metadata={"native_ir_unit": "(D/A)^2/amu"},
        )

    def test_loto_frequency_unit_switch_redraws_in_thz(self):
        plot = LOTOPlot()
        result = self.loto()
        plot.set_result(result)
        plot.set_frequency_unit("THz")
        self.assertEqual(plot.axes.get_ylabel(), "Frequency (THz)")
        self.assertTrue(np.allclose(plot.axes.lines[0].get_ydata(), result.arrays["frequencies_uncorrected_THz"]))
        plot.close()

    def test_loto_table_export_columns_include_direction_and_classification(self):
        headers, rows = tabular_data(self.loto())
        self.assertEqual(headers[:4], ["direction_x", "direction_y", "direction_z", "mode"])
        self.assertEqual(headers[-1], "classification")
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[0][0:3], [1.0, 0.0, 0.0])

    def test_ir_activity_is_discrete_and_axis_label_is_native(self):
        plot = IRPlot()
        result = self.ir()
        plot.set_result(result)
        activity = result.arrays["native_ir_quantity"].copy()
        plot.set_frequency_unit("THz")
        self.assertEqual(plot.axes.get_ylabel(), "IR activity ((D/Å)²/amu)")
        np.testing.assert_array_equal(activity, result.arrays["native_ir_quantity"])
        plot.close()

    def test_loto_shifts_use_asr_equivalent_reference(self):
        from backend.results import DEFAULT_PARSERS
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/"lo_to.dynmat.out"
            source.write_text("\n".join(f" freq ( {i} ) = {value/33.3564095:.6f} [THz] = {value:.6f} [cm-1]" for i,value in enumerate([0.,0.,0.,398.079847,398.079847,702.196771],1)))
            activity="\n".join(f" {i} 0.0 0.0 {0.0 if i < 4 else 9.1639}" for i in range(1,7))
            result=DEFAULT_PARSERS.parse("QE_DYNMAT_POLAR",source,activity_text=activity,purpose="lo_to",direction=[1.,0.,0.],expected_mode_count=6,uncorrected_frequencies_cm1=[-0.000005,-0.000003,0.000005,398.079847,398.079847,398.079847],uncorrected_frequencies_THz=[-0.00000015,-0.00000009,0.00000015,11.934134,11.934134,11.934134],uncorrected_reference="ASR-consistent analytic dynmat reference")
            self.assertEqual(result.metadata["uncorrected_reference"],"ASR-consistent analytic dynmat reference")
            self.assertTrue(np.max(np.abs(result.arrays["frequency_shifts_cm1"][:3])) < 2e-5)
            self.assertTrue(np.max(np.abs(result.arrays["frequency_shifts_cm1"][3:5])) < 1e-9)
            self.assertAlmostEqual(float(result.arrays["frequency_shifts_cm1"][5]),304.116924,places=5)

    def test_loto_analyze_exposes_direction_control(self):
        workspace = AnalyzeWorkspace(Project("E3C"))
        workspace.current_result = self.loto()
        workspace.resize(1366, 768)
        workspace._show_plot()
        self.app.processEvents()
        self.assertTrue(hasattr(workspace, "phonon_direction"))
        self.assertEqual(workspace.phonon_direction.count(), 1)
        self.assertEqual(workspace.phonon_direction.itemText(0), "[1, 0, 0]")
        workspace.close()


if __name__ == "__main__":
    unittest.main()
