import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QScrollArea, QSpinBox

from frontend.calculate import CalculateWorkspace
from frontend.core import Atom, Project, Structure
from frontend.services.calculation_service import CalculationService
from frontend.calculations.catalog import CALCULATIONS


class CalculateUxCompletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def project(self):
        project = Project("Calculate UX")
        structure = Structure([Atom("Si", 0, 0, 0)], [[4, 0, 0], [0, 4, 0], [0, 0, 4]])
        structure.periodic = [True, True, True]
        project.set_structure(structure)
        return project

    def test_configure_dialog_fit_keeps_buttons_outside_scroll_and_on_screen(self):
        dialog = QDialog()
        scroll = QScrollArea(dialog)
        scroll.setWidgetResizable(True)
        scroll.setWidget(__import__("PySide6.QtWidgets", fromlist=["QWidget"]).QWidget())
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, dialog)
        from PySide6.QtWidgets import QVBoxLayout
        layout = QVBoxLayout(dialog); layout.addWidget(scroll, 1); layout.addWidget(buttons, 0)
        CalculateWorkspace._fit_configuration_dialog(dialog, 720, 1400)
        dialog.show(); self.app.processEvents()
        self.assertLess(dialog.height(), 1400)
        self.assertIs(buttons.parentWidget(), dialog)
        self.assertGreaterEqual(buttons.geometry().bottom(), scroll.geometry().bottom())
        self.assertTrue(dialog.minimumHeight() > 0)
        dialog.close()

    def test_catalog_extended_selection_adds_all_highlighted_calculations(self):
        workspace = CalculateWorkspace(self.project())
        workspace.show(); self.app.processEvents()
        try:
            wanted = {"bands", "dos", "pdos", "charge_density"}
            rows = []
            for row in range(workspace.calculation_list.count()):
                item = workspace.calculation_list.item(row)
                if item.data(Qt.ItemDataRole.UserRole) in wanted:
                    rows.append(item)
            self.assertEqual({item.data(Qt.ItemDataRole.UserRole) for item in rows}, wanted)
            for item in rows: item.setSelected(True)
            self.assertEqual(set(workspace.selected_ids), wanted)
            workspace._create_calculation_requested()
            self.assertEqual({r.selected_calculations[0] for r in workspace.project.get_calculations()}, wanted)
        finally:
            workspace.close()

    def test_configured_list_extended_selection_and_run_label(self):
        workspace = CalculateWorkspace(self.project())
        try:
            for calc_id in ("bands", "dos", "pdos"):
                workspace.selected_ids = [calc_id]
                workspace.create_persistent_calculation(name=calc_id.upper())
            workspace._refresh_configured_calculations()
            for row in range(workspace.configured_list.count()): workspace.configured_list.item(row).setSelected(True)
            self.assertEqual(len(workspace._selected_configured_request_ids()), 3)
            self.assertEqual(workspace.execute_button.text(), "Run Selected (3)")
            self.assertEqual(workspace.generate_qe_button.text(), "Generate QE Inputs (3)")
        finally:
            workspace.close()

    def test_batch_compiler_shares_identical_prerequisites_and_isolates_parameters(self):
        service = CalculationService(CALCULATIONS)
        project = self.project()
        first = service.create_request(project, ["bands"], {"xc_functional": "pbe"}, name="PBE bands").backend_request
        second = service.create_request(project, ["dos"], {"xc_functional": "pbe"}, name="PBE DOS").backend_request
        third = service.create_request(project, ["bands"], {"xc_functional": "pbe", "soc": True}, name="HSE bands").backend_request
        plans = service.compile_batch_requests([first, second, third])
        self.assertEqual(len(plans), 2)
        shared = next(plan for plan in plans if len(plan.metadata["batch_request_ids"]) == 2)
        self.assertEqual({"bands", "dos"}, set(shared.selected_calculations))
        separate = next(plan for plan in plans if len(plan.metadata["batch_request_ids"]) == 1)
        self.assertEqual(separate.parameters["xc_functional"], "pbe")
        self.assertTrue(separate.parameters["soc"])

    def test_batch_cancel_does_not_modify_requests(self):
        service = CalculationService(CALCULATIONS); project = self.project()
        request = service.create_request(project, ["bands"], {"xc_functional": "pbe", "soc": True}).backend_request
        before = request.to_persistence_dict()
        updated = service.update_request_parameters(request, dict(request.parameters), name=request.name)
        self.assertEqual(updated.to_persistence_dict()["parameters"], before["parameters"])
        self.assertEqual(request.to_persistence_dict(), before)


    def test_scalar_magnetization_is_ignored_and_collinear_is_typed(self):
        from backend.engines.qe.writer import _magnetization_values
        from frontend.calculate.typed_parameter_controls import SpeciesMagnetizationControl, control_value, make_control
        structure={"atoms":[{"element":"Fe"},{"element":"O"}]}
        self.assertEqual(_magnetization_values({"starting_magnetization":"{}"}, structure, "SCALAR_NONSPIN"), {})
        control=make_control("starting_magnetization", {}, structure=structure)
        self.assertIsInstance(control, SpeciesMagnetizationControl)
        self.assertEqual(control_value("starting_magnetization", control), {"Fe":0.0,"O":0.0})
        control.boxes["Fe"].setValue(0.5)
        self.assertEqual(control_value("starting_magnetization", control)["Fe"], 0.5)
        self.assertEqual(_magnetization_values({"starting_magnetization":{"Fe":0.5}}, structure, "COLLINEAR_SPIN"), {"starting_magnetization(1)":0.5})

    def test_mesh_parameters_use_three_positive_integer_boxes(self):
        from frontend.calculate.typed_parameter_controls import control_value, make_control
        for key in ("kpoints", "exx_q_mesh", "qmesh"):
            control=make_control(key, [6, 8, 1])
            self.assertEqual(len(control._mesh_boxes), 3)
            self.assertTrue(all(isinstance(box, QSpinBox) and box.value() >= 1 for box in control._mesh_boxes))
            self.assertEqual(control_value(key, control), [6,8,1])

    def test_optional_occupation_values_are_typed_or_omitted(self):
        from frontend.calculate.typed_parameter_controls import control_value, make_control
        control = make_control("degauss", None)
        self.assertIsInstance(control, __import__("PySide6.QtWidgets", fromlist=["QDoubleSpinBox"]).QDoubleSpinBox)
        self.assertGreater(control.value(), 0.0)
        from frontend.services.calculation_service import normalize_qe_parameters
        fixed = normalize_qe_parameters({"occupations": "fixed", "smearing": "mv", "degauss": ""})
        self.assertNotIn("smearing", fixed)
        self.assertNotIn("degauss", fixed)
        smearing = normalize_qe_parameters({"occupations": "smearing", "smearing": "mv", "degauss": 0.01})
        self.assertIsInstance(smearing["degauss"], float)
        updated = CalculationService(CALCULATIONS).update_request_parameters(
            CalculationService(CALCULATIONS).create_request(self.project(), ["bands"], {}).backend_request,
            {"occupations": "fixed", "degauss": "", "smearing": ""},
        )
        self.assertNotIn("degauss", updated.parameters)

    def test_scalar_charge_density_default_request_has_no_magnetization(self):
        service=CalculationService(CALCULATIONS); project=self.project()
        request=service.create_request(project, ["charge_density"], {}, name="Si charge").backend_request
        self.assertNotIn("starting_magnetization", request.parameters)
        prepared=service.prepare_persisted_request(request)
        self.assertNotIn("starting_magnetization", prepared.backend_request.parameters)


    def test_spin_mode_normalization_removes_incompatible_fields(self):
        from frontend.services.calculation_service import normalize_spin_parameters
        scalar=normalize_spin_parameters({"spin_treatment":"SCALAR_NONSPIN","starting_magnetization":{"Fe":0.5},"tot_magnetization":2.0,"noncolin":True,"lspinorb":True})
        self.assertNotIn("starting_magnetization", scalar); self.assertNotIn("tot_magnetization", scalar); self.assertNotIn("noncolin", scalar); self.assertNotIn("lspinorb", scalar)
        collinear=normalize_spin_parameters({"spin_treatment":"COLLINEAR_SPIN","starting_magnetization":{"Fe":0.5},"tot_magnetization":None,"noncolin":True,"lspinorb":True})
        self.assertEqual(collinear["starting_magnetization"], {"Fe":0.5}); self.assertNotIn("tot_magnetization", collinear); self.assertTrue(collinear["spin"]); self.assertNotIn("noncolin", collinear)
        soc=normalize_spin_parameters({"spin_treatment":"SOC","starting_magnetization":{"Te":0.5},"tot_magnetization":1.0,"spin":True})
        self.assertNotIn("starting_magnetization", soc); self.assertNotIn("tot_magnetization", soc); self.assertTrue(soc["noncolin"]); self.assertTrue(soc["lspinorb"]); self.assertFalse(soc["spin"])

    def test_scalar_low_level_total_magnetization_remains_rejected(self):
        from backend.compiler.calculation_compiler import CalculationCompiler
        from backend.core.calculation_request import CalculationRequest
        from backend.engines.qe import QuantumEspressoAdapter
        request=CalculationRequest(structure={"name":"Si","periodic":[True,True,True],"cell":[[3,0,0],[0,3,0],[0,0,3]],"atoms":[{"element":"Si","x":0,"y":0,"z":0}]}, selected_calculations=["scf"], parameters={"spin_treatment":"SCALAR_NONSPIN","tot_magnetization":2.0,"kpoints":[1,1,1],"ecutwfc":40,"ecutrho":320,"conv_thr":1e-6,"pseudopotentials":{"Si":"Si.UPF"}})
        with self.assertRaisesRegex(Exception, "tot_magnetization"):
            QuantumEspressoAdapter().compile_plan(CalculationCompiler(request).compile())


if __name__ == "__main__": unittest.main()
