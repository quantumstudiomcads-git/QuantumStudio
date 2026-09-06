import os, unittest
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np
from PySide6.QtWidgets import QApplication, QLineEdit, QDialog, QLabel, QTabBar, QTabWidget, QSizePolicy
from PySide6.QtCore import Qt
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

    def band(self):
        return ScientificResult("BandStructureResult", ResultStatus.VALID, self.provenance,
            arrays={"path_coordinate":np.array([0.,1.,2.]),"energies":np.array([[-1.,1.],[-.5,.5],[0.,1.5]])},
            metadata={"path_labels":{0:"Γ",2:"X"}})

    def pdos(self):
        return ScientificResult("PDOSResult", ResultStatus.VALID, self.provenance,
            arrays={"energy":np.array([-1.,0.,1.])},
            metadata={"fermi_energy_eV":0.0,"components":[{"id":"si1:s","label":"Si1 s","species":"Si","atom_index":1,"orbital":"s"}],"component_values":[[1.,2.,1.]]})

    def test_result_switches_rebuild_one_data_set_and_band_toolbar(self):
        from frontend.analyze.workspace import AnalyzeWorkspace
        from frontend.core import Project
        workspace=AnalyzeWorkspace(Project("Analyze lifecycle")); workspace.show(); self.app.processEvents()
        try:
            for result in (self.dos(), self.pdos(), self.band(), self.dos(), self.band(), self.dos()):
                workspace.current_result=result; workspace._show_plot(); self.app.processEvents()
                self.assertEqual(len(workspace.views.findChildren(type(workspace.plot.canvas))), 1)
            workspace.current_result=self.dos()
            for _ in range(5): workspace._show_plot()
            texts=[workspace.data_layout.itemAt(i).widget().text() for i in range(workspace.data_layout.count()) if isinstance(workspace.data_layout.itemAt(i).widget(), QLabel)]
            self.assertEqual(texts.count("Energy reference"),1)
            workspace.current_result=self.band(); workspace._show_plot(); toolbar=workspace.plot.interaction_toolbar
            self.assertIs(workspace.plot.marker_button.parentWidget(),toolbar)
            self.assertIs(workspace.plot.readout.parentWidget(),toolbar)
            self.assertEqual(toolbar.layout().indexOf(workspace.plot.marker_button) < toolbar.layout().indexOf(workspace.plot.readout), True)
            self.assertEqual(len(toolbar.findChildren(type(workspace.plot.marker_button))),5)
        finally:
            workspace.close()

    def test_selected_result_calculation_persists_across_workspace_reopen(self):
        from backend.core.calculation_request import CalculationRequest
        from frontend.analyze.workspace import AnalyzeWorkspace
        from frontend.core import Project
        project=Project("Persisted Analyze selection")
        first=CalculationRequest(id="raman-6",structure={},selected_calculations=["raman"],parameters={},name="Raman 6x6x6")
        final=CalculationRequest(id="raman-12",structure={},selected_calculations=["raman"],parameters={},name="Raman 12x12x12")
        project.add_calculation(first); project.add_calculation(final)
        workspace=AnalyzeWorkspace(project)
        workspace.calculation.setCurrentIndex(workspace.calculation.findData(final.id))
        self.assertEqual(project.analysis["selected_result_request_id"],final.id)
        workspace.close()
        reopened=AnalyzeWorkspace(project)
        self.assertEqual(reopened.calculation.currentData(),final.id)
        reopened.close()

    def test_plot_first_layout_and_export_size_independence(self):
        from frontend.analyze.workspace import AnalyzeWorkspace
        from frontend.core import Project
        workspace=AnalyzeWorkspace(Project("Plot first")); workspace.resize(1366,768); workspace.show(); self.app.processEvents()
        try:
            self.assertEqual(workspace.plot.canvas.sizePolicy().horizontalPolicy(), QSizePolicy.Policy.Expanding)
            self.assertEqual(workspace.plot.canvas.sizePolicy().verticalPolicy(), QSizePolicy.Policy.Expanding)
            self.assertIsInstance(workspace.navigation, QTabBar)
            self.assertIsInstance(workspace.control_sections, QTabWidget)
            self.assertEqual([workspace.control_sections.tabText(i) for i in range(workspace.control_sections.count())], ["Data","Style","Details","Export"])
            self.assertEqual([workspace.appearance_editor.category_tabs.tabText(i) for i in range(workspace.appearance_editor.category_tabs.count())], ["Presets","Series","Axes","Text","Reference","Legend","Figure"])
            splitter=workspace.findChild(__import__("PySide6.QtWidgets",fromlist=["QSplitter"]).QSplitter)
            self.assertIsNotNone(splitter)
            self.assertGreater(splitter.sizes()[1], splitter.sizes()[0])
            self.assertGreater(splitter.sizes()[1], splitter.sizes()[2])
            before=workspace.plot.canvas.size()
            workspace.plot.appearance_state.figure_width=3.5; workspace.plot.appearance_state.figure_height=2.5; workspace.plot.apply_appearance(); workspace.plot.canvas.draw_idle(); self.app.processEvents()
            after=workspace.plot.canvas.size()
            self.assertEqual(before, after)
            workspace.plot.appearance_state.figure_width=7.0; workspace.plot.appearance_state.figure_height=5.0; workspace.plot.apply_appearance(); self.app.processEvents()
            self.assertEqual(before, workspace.plot.canvas.size())
        finally:
            workspace.close()

    def test_final_layout_uses_compact_results_and_vertical_style_rail(self):
        from frontend.analyze.workspace import AnalyzeWorkspace
        from frontend.core import Project
        workspace=AnalyzeWorkspace(Project("Final layout")); workspace.resize(1366,768); workspace.show(); self.app.processEvents()
        try:
            self.assertEqual(workspace.result_browser.sizePolicy().verticalPolicy(), QSizePolicy.Policy.Expanding)
            self.assertGreater(workspace.result_browser.maximumHeight(), 100000)
            editor=workspace.appearance_editor
            self.assertEqual([editor.category_list.item(i).text() for i in range(editor.category_list.count())], ["Series","Axes","Text","Reference","Legend","Figure"])
            self.assertEqual(editor.category_stack.count(), 6)
            self.assertEqual(editor.category_list.currentRow(), 0)
            self.assertEqual(editor.findChildren(QTabWidget), [])
            self.assertEqual([workspace.control_sections.tabText(i) for i in range(workspace.control_sections.count())], ["Data","Style","Details","Export"])
            self.assertNotIn("Presets", [editor.category_list.item(i).text() for i in range(editor.category_list.count())])
        finally:
            workspace.close()

    def test_micro_polish_axis_labels_and_vertical_data_export_controls(self):
        from frontend.analyze.workspace import AnalyzeWorkspace
        from frontend.core import Project
        plot=DOSPlot(); plot.set_result(self.dos())
        self.assertEqual(plot.axes.xaxis.label.get_color(), "black")
        self.assertEqual(plot.axes.yaxis.label.get_color(), "black")
        self.assertEqual(plot.axes.get_xlabel(), "Energy − E_F (eV)")
        self.assertEqual(plot.axes.get_ylabel(), "DOS (states/eV/cell)")
        plot.close()

        workspace=AnalyzeWorkspace(Project("Micro polish")); workspace.resize(1366,768); workspace.show(); self.app.processEvents()
        try:
            workspace.current_result=self.pdos(); workspace._show_plot(); self.app.processEvents()
            form=workspace.pdos_controls.layout()
            self.assertEqual([form.labelForField(box).text() for box in (workspace.pdos_species,workspace.pdos_atom,workspace.pdos_orbital)], ["Species","Atom","Orbital"])
            pdos_y=[box.geometry().top() for box in (workspace.pdos_species,workspace.pdos_atom,workspace.pdos_orbital)]
            self.assertEqual(pdos_y, sorted(pdos_y))
            workspace.current_result=self.dos(); workspace._show_plot(); self.app.processEvents()
            self.assertEqual(workspace.plot.reference.currentText(), "Fermi = 0")
            data_widgets=[workspace.data_layout.itemAt(i).widget() for i in range(workspace.data_layout.count())]
            energy_label=next(widget for widget in data_widgets if isinstance(widget,QLabel) and widget.text()=="Energy reference")
            energy_combo=workspace.plot.reference
            self.assertLess(energy_label.geometry().top(), energy_combo.geometry().top())
            export_widgets=[workspace.export_section.layout().itemAt(i).widget() for i in range(workspace.export_section.layout().count())]
            self.assertEqual([widget.text() for widget in export_widgets if hasattr(widget,"text")], ["Figure","Export Figure…","Data","Export Data…"])
        finally:
            workspace.close()

if __name__=="__main__":
    unittest.main()
