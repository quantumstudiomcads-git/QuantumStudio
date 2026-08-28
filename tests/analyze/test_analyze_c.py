import os, tempfile, unittest
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np
from PySide6.QtWidgets import QApplication
from backend.results import ResultProvenance, ResultStatus, ScientificResult
from frontend.analyze.plots.appearance import PlotAppearanceState, PlotSeriesAppearance, UserPlotPresetStore, available_font_families
from frontend.analyze.plots.base import ScientificPlotWidget
from frontend.analyze.plots.bader import BaderChargePlot
from frontend.analyze.plots.projection import ProjectionPlot
from frontend.analyze.plots.volumetric import VolumetricPlot
from frontend.analyze.plots.work_function import WorkFunctionPlot

class AnalyzeCPlotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.provenance = ResultProvenance("r","e","t","qe","pw.x",(),{},"fixture")

    def test_state_schema_and_font_enumeration(self):
        state = PlotAppearanceState.default()
        self.assertEqual(available_font_families(), tuple(sorted(set(available_font_families()), key=str.casefold)))
        self.assertIn("figure_background", state.to_dict())
        self.assertIn("reference_lines", state.to_dict())
        self.assertEqual(PlotSeriesAppearance.from_dict({"opacity": 2}).opacity, 1.0)

    def test_preset_roundtrip_and_missing_font_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            store = UserPlotPresetStore(directory)
            state = PlotAppearanceState.default()
            state.font_family = "__missing_font__"
            store.save("clean", state)
            loaded = store.load("clean")
            self.assertIn(loaded.font_family, available_font_families())
            self.assertIn("clean", store.names())
            store.delete("clean")
            self.assertNotIn("clean", store.names())

    def test_shared_style_does_not_mutate_bar_result(self):
        result = ScientificResult("BaderChargeResult", ResultStatus.VALID, self.provenance,
            arrays={"atom_index":[1,2], "net_charge":[0.1,-0.2]}, metadata={})
        snapshot = list(result.arrays["net_charge"])
        plot = BaderChargePlot()
        plot.set_result(result)
        plot.appearance_state.series["net_charge"] = {"color":"#ff0000","line_width":2,"opacity":.4}
        plot.appearance_state.reference_lines["zero_charge"] = {"color":"#0000ff","line_width":2,"line_style":":"}
        plot.redraw()
        self.assertEqual(result.arrays["net_charge"], snapshot)
        self.assertTrue(plot.axes.patches)
        plot.close()

    def test_work_function_reference_and_export(self):
        result = ScientificResult("WorkFunctionResult", ResultStatus.VALID, self.provenance,
            arrays={"distance_A":[0.,1.], "potential_eV":[1.,2.]},
            metadata={"work_function_analysis":{"vacuum_levels":[{"level_eV":3.,"start_fractional":.5,"end_fractional":1.}]}})
        plot = WorkFunctionPlot()
        plot.set_result(result)
        self.assertIn("potential", plot.appearance_state.series)
        self.assertIn("vacuum_level", plot.appearance_state.reference_lines)
        with tempfile.TemporaryDirectory() as directory:
            for suffix in ("png","pdf","svg"):
                path = os.path.join(directory, "figure."+suffix)
                plot.export_figure(path, fmt=suffix, dpi=150)
                self.assertGreater(os.path.getsize(path), 0)
        plot.close()

    def test_volumetric_shared_image_state(self):
        result = ScientificResult("VolumetricResult", ResultStatus.VALID, self.provenance,
            arrays={"values":np.arange(27,dtype=float).reshape(3,3,3)},
            metadata={"cell":np.eye(3), "unit":"e/Angstrom^3"})
        plot = VolumetricPlot()
        plot.set_result(result)
        plot.appearance_state.colormap = "plasma"
        plot.appearance_state.color_min = 2.
        plot.appearance_state.color_max = 20.
        plot.redraw()
        self.assertTrue(plot.axes.images)
        self.assertEqual(plot.axes.images[0].get_cmap().name, "plasma")
        self.assertEqual(tuple(plot.axes.images[0].get_clim()), (2.,20.))
        self.assertEqual(result.arrays["values"].shape, (3,3,3))
        plot.close()

if __name__ == "__main__":
    unittest.main()
