import os, unittest
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np
from PySide6.QtWidgets import QApplication, QLineEdit, QDialog
from backend.results import ResultProvenance, ResultStatus, ScientificResult
from frontend.analyze.plots.appearance import PlotAppearanceState
from frontend.analyze.plots.base import PlotAppearanceEditor
from frontend.analyze.plots.dos import DOSPlot
from frontend.analyze.plots.bands import BandPlot

class AnalyzeUxRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.provenance = ResultProvenance("request","execution","task","qe","dos.x",(),{},"fixture")

    def dos(self):
        return ScientificResult("DOSResult", ResultStatus.VALID, self.provenance,
            arrays={"energy":np.array([-17.,-5.,0.,4.]),"dos":np.array([1.,2.,3.,1.])},
            metadata={"fermi_energy_eV":0.0})

    def test_auto_axes_never_use_sentinel(self):
        state=PlotAppearanceState.default()
        self.assertIsNone(state.x_min); self.assertIsNone(state.x_max)
        self.assertIsNone(state.y_min); self.assertIsNone(state.y_max)
        plot=DOSPlot(); plot.set_result(self.dos())
        editor=PlotAppearanceEditor(plot)
        for key in ("x_min","x_max","y_min","y_max"):
            self.assertIsInstance(editor.controls[key],QLineEdit)
            editor.controls[key].setText("Auto")
            self.assertIsNone(getattr(plot.appearance_state,key))
            self.assertNotIn(getattr(plot.appearance_state,key),(-1e9,1e9))
        editor.controls["x_min"].setText("-10"); editor.controls["x_max"].setText("3")
        editor.controls["y_min"].setText("0"); editor.controls["y_max"].setText("4")
        self.assertEqual((plot.appearance_state.x_min,plot.appearance_state.x_max),(-10.,3.))
        self.assertEqual((plot.appearance_state.y_min,plot.appearance_state.y_max),(0.,4.))
        plot.appearance_state.x_min=None; plot.appearance_state.x_max=None
        plot.appearance_state.y_min=None; plot.appearance_state.y_max=None
        plot.redraw()
        limits=plot.axes.get_xlim()+plot.axes.get_ylim()
        self.assertTrue(all(np.isfinite(limits)))
        self.assertLess(max(abs(value) for value in limits),1e6)
        plot.close()

    def test_single_canvas_survives_repeated_appearance_edits(self):
        plot=DOSPlot(); plot.set_result(self.dos()); editor=PlotAppearanceEditor(plot)
        def count(): return len(plot.findChildren(type(plot.canvas)))
        self.assertEqual(count(),1)
        for family in ("DejaVu Sans","DejaVu Serif","DejaVu Sans"):
            editor.controls["font_family"].setCurrentText(family)
            editor.controls["figure_width"].setValue(6.5)
            editor.controls["figure_height"].setValue(4.0)
            editor.controls["spine_width"].setValue(1.0)
            editor.controls["show_grid"].setChecked(True)
            editor.controls["show_grid"].setChecked(False)
            self.assertEqual(count(),1)
        plot.close()

    def test_docked_editor_is_normal_appearance_workflow(self):
        plot=DOSPlot(); editor=plot.create_appearance_editor()
        self.assertIsInstance(editor,PlotAppearanceEditor)
        self.assertEqual(len(plot.findChildren(QDialog)),0)
        self.assertIsNone(plot.edit_appearance())
        plot.close()

    def test_plot_replacement_has_one_active_canvas(self):
        workspace=None
        from frontend.analyze.workspace import AnalyzeWorkspace
        from frontend.core import Project
        workspace=AnalyzeWorkspace(Project("UX"))
        results=[
            self.dos(),
            ScientificResult("PDOSResult",ResultStatus.VALID,self.provenance,
                arrays={"energy":np.array([-1.,0.,1.])},
                metadata={"fermi_energy_eV":0.0,"components":[{"label":"Si1 p","species":"Si","atom_index":1,"orbital":"p"}],"component_values":[[1.,2.,1.]]}),
            ScientificResult("BandStructureResult",ResultStatus.VALID,self.provenance,
                arrays={"path_coordinate":np.array([0.,1.]),"energies":np.array([[-1.,1.],[-.5,.5]])},metadata={}),
            self.dos()]
        for result in results:
            workspace.current_result=result
            workspace._show_plot()
            self.assertEqual(len(workspace.plot.findChildren(type(workspace.plot.canvas))),1)
        workspace.close()

if __name__=="__main__":
    unittest.main()
