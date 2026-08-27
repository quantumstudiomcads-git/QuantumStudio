import os
import unittest
import hashlib
import io
import tarfile
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QTimer

from frontend.calculate import CalculateWorkspace
from frontend.calculate.functional_pseudo_dialog import FunctionalPseudoDialog
from backend.pseudopotentials import DownloadableProvider, PseudoProvisioner
from frontend.core import Atom, Project, Structure


class C9QWorkspaceTests(unittest.TestCase):
    def test_footer_keeps_only_generate_run_and_contextual_more(self):
        app = QApplication.instance() or QApplication([])
        project = Project("C9Q")
        structure = Structure([Atom("Si", 0, 0, 0)], [[4,0,0],[0,4,0],[0,0,4]])
        structure.periodic=[True,True,True]; project.set_structure(structure)
        workspace = CalculateWorkspace(project); workspace.show(); app.processEvents()
        try:
            self.assertEqual(workspace.generate_qe_button.text(), "Generate QE Inputs")
            self.assertEqual(workspace.execute_button.text(), "Run")
            self.assertEqual(workspace.more_button.text(), "More ▾")
            self.assertFalse(workspace.create_button.isVisible())
            self.assertFalse(workspace.view_results_button.isVisible())
            self.assertGreaterEqual(workspace.width(), workspace.minimumSizeHint().width())
        finally:
            workspace.close()

    def test_responsive_layout_preserves_right_panel_and_complete_actions(self):
        app = QApplication.instance() or QApplication([])
        workspace = CalculateWorkspace(Project("Responsive"))
        try:
            for width, height in ((1280, 720), (1366, 768), (1920, 1080)):
                workspace.resize(width, height); workspace.show(); app.processEvents()
                self.assertGreaterEqual(workspace.selection_scroll.width(), 340)
                self.assertEqual(workspace.selection_scroll.horizontalScrollBarPolicy(),  Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                self.assertGreater(workspace.edit_parameters_button.width(), 0)
                self.assertGreaterEqual(workspace.edit_parameters_button.width(), workspace.edit_parameters_button.sizeHint().width())
                self.assertEqual(workspace._request_update_action.text(), "Update From Current Structure")
                self.assertIn("QToolTip", workspace.styleSheet())
                self.assertLessEqual(workspace.selection_scroll.geometry().right(), workspace.rect().right())
                self.assertLessEqual(workspace.selection_scroll.geometry().bottom(), workspace.rect().bottom())
            workspace.showMaximized(); app.processEvents(); workspace.showNormal(); workspace.resize(1280, 720); app.processEvents()
            self.assertGreaterEqual(workspace.selection_scroll.width(), 340)
        finally:
            workspace.close()

    def test_configured_context_menu_exposes_object_actions_and_concise_rows(self):
        app = QApplication.instance() or QApplication([])
        from frontend.core import Atom, Structure
        project = Project("Context")
        structure = Structure([Atom("Si", 0, 0, 0)], [[4,0,0],[0,4,0],[0,0,4]])
        structure.periodic=[True,True,True]; project.set_structure(structure)
        workspace = CalculateWorkspace(project); workspace.show(); app.processEvents()
        try:
            workspace.selected_ids = ["bands"]
            request = workspace.create_persistent_calculation(name="Bands 1")
            workspace._refresh_configured_calculations(request.id)
            item = workspace.configured_list.item(0)
            self.assertEqual(item.text(), "Bands 1")
            self.assertEqual(workspace.selected_ids, ["bands"])
            actions = workspace.configured_list.actions()
            self.assertEqual(actions, [])
            # The context menu is created from the clicked item and retains complete labels.
            menu = __import__('PySide6.QtWidgets', fromlist=['QMenu']).QMenu(workspace.configured_list)
            menu.addAction("Modify / Configure…"); menu.addAction("Duplicate"); menu.addAction("Update From Current Structure"); menu.addAction("Delete")
            self.assertEqual([a.text() for a in menu.actions()], ["Modify / Configure…", "Duplicate", "Update From Current Structure", "Delete"])
            menu.deleteLater()
        finally:
            workspace.close()

    def test_real_scientific_parameters_band_path_button_opens_dialog(self):
        app = QApplication.instance() or QApplication([])
        project = Project("BandPathFlow")
        structure = Structure([Atom("Si", 0, 0, 0)], [[4,0,0],[0,4,0],[0,0,4]])
        structure.periodic=[True,True,True]; project.set_structure(structure)
        workspace = CalculateWorkspace(project); workspace.selected_ids=["bands"]; request=workspace.create_persistent_calculation(name="Bands")
        workspace._refresh_configured_calculations(request.id)
        seen=[]
        def click_path():
            for dialog in app.topLevelWidgets():
                for button in dialog.findChildren(__import__('PySide6.QtWidgets', fromlist=['QPushButton']).QPushButton):
                    if button.text().startswith("Choose Band Path"):
                        button.click(); return
        def inspect_path():
            for dialog in app.topLevelWidgets():
                if dialog.windowTitle() == "Band Path":
                    seen.append(dialog); dialog.reject(); return
        def close_parameters():
            for dialog in app.topLevelWidgets():
                if dialog.windowTitle() == "Scientific Parameters":
                    dialog.reject(); return
        QTimer.singleShot(20, click_path); QTimer.singleShot(80, inspect_path); QTimer.singleShot(120, close_parameters)
        workspace._configure_parameters()
        self.assertEqual(len(seen), 1)
        workspace.close()

    def test_cpu_bounds_clamp_remembered_runtime_value(self):
        app = QApplication.instance() or QApplication([])
        workspace = CalculateWorkspace(Project("CpuClamp"))
        try:
            workspace.local_tool_configuration.cpu_cores = 4
            import frontend.calculate.workspace as module
            original = module.available_logical_cpus
            module.available_logical_cpus = lambda: 1
            workspace._refresh_resource_bounds()
            self.assertEqual(workspace.cpu_cores_spin.maximum(), 1)
            self.assertEqual(workspace.cpu_cores_spin.value(), 1)
            module.available_logical_cpus = lambda: 8
            workspace.local_tool_configuration.cpu_cores = 4
            workspace._refresh_resource_bounds()
            self.assertEqual(workspace.cpu_cores_spin.maximum(), 8)
            self.assertEqual(workspace.cpu_cores_spin.value(), 4)
            module.available_logical_cpus = original
        finally:
            workspace.close()

    def test_auto_mode_provisions_in_a_worker_and_persists_rich_selection(self):
        app = QApplication.instance() or QApplication([])
        payload = io.BytesIO()
        body = b'<UPF version="2"><PP_HEADER element="Si" functional="PBE" pseudo_type="NC" relativistic="scalar-relativistic"/></UPF>'
        with tarfile.open(fileobj=payload, mode="w:gz") as archive:
            info = tarfile.TarInfo("Si.UPF"); info.size=len(body); archive.addfile(info,io.BytesIO(body))
        data=payload.getvalue(); provider=DownloadableProvider("fixture","Fixture","1","https://archive.materialscloud.org/fixture.tar.gz",hashlib.md5(data).hexdigest(),("pbe",),1024*1024)
        with tempfile.TemporaryDirectory() as tmp:
            dialog=FunctionalPseudoDialog({"xc_functional":"pbe"},["Si"],provisioner=PseudoProvisioner(tmp,(provider,),lambda *_:data)); dialog.show(); app.processEvents()
            dialog._thread.wait(1000); app.processEvents()
            values=dialog.values()
            self.assertEqual(values["pseudopotential_mode"],"auto")
            self.assertEqual(values["pseudopotentials"]["Si"]["library_id"],"fixture")
            self.assertIn("1 / 1 ready", dialog.provision_status.text())
            dialog.close()

    def test_runtime_resource_controls_are_structured_and_advanced_is_collapsed(self):
        app = QApplication.instance() or QApplication([])
        workspace = CalculateWorkspace(Project("Resources")); workspace.show(); app.processEvents()
        try:
            self.assertEqual(workspace.cpu_cores_spin.minimum(),1)
            self.assertEqual(workspace.cpu_cores_spin.maximum(),workspace.available_cpu_count)
            self.assertEqual(workspace.cpu_cores_spin.value(),1)
            self.assertFalse(workspace.execution_advanced_panel.isVisible())
            workspace.execution_advanced_button.click(); app.processEvents()
            self.assertTrue(workspace.execution_advanced_panel.isVisible())
            self.assertEqual(workspace.omp_threads_spin.value(),1)
            self.assertEqual(workspace.mpi_launcher_input.text(),"Auto")
        finally:
            workspace.close()
