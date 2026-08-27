import os
import unittest

import numpy as np
from PySide6.QtWidgets import QApplication

from frontend.app.project_window import ProjectWindow
from frontend.calculate import CalculateWorkspace
from frontend.core import Atom, Project, Structure
from frontend.services.calculation_service import CalculationService
from frontend.calculations.catalog import CALCULATIONS

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def app():
    return QApplication.instance() or QApplication([])


def structure(name, a=4.0, species="Si"):
    result = Structure(
        [Atom(species, 0.0, 0.0, 0.0), Atom(species, 1.0, 1.0, 1.0)],
        [[a, 0.0, 0.0], [0.0, a, 0.0], [0.0, 0.0, a]], name=name,
    )
    result.periodic = [True, True, True]
    return result


class CalculateStructureHandoffTests(unittest.TestCase):
    def setUp(self):
        app()
        self.project = Project("Calculate Handoff")
        self.workspace = CalculateWorkspace(self.project)

    def tearDown(self):
        self.workspace.close()

    def test_empty_project_is_safe_catalog_state_and_cannot_prepare_request(self):
        summary = self.workspace.current_structure_summary
        self.assertFalse(summary.valid)
        self.assertIn("No active structure", self.workspace.structure_label.text())
        self.workspace.selected_ids = ["scf"]
        self.workspace._refresh_selection()
        self.assertFalse(self.workspace.compile_button.isEnabled())
        with self.assertRaisesRegex(RuntimeError, "contains no atoms"):
            self.workspace.create_calculation_request()

    def test_workspace_reads_current_native_project_structure_and_refreshes_without_builder_reference(self):
        first = structure("Structure A", 4.0, "Si")
        self.project.set_structure(first)
        self.workspace.refresh()
        self.assertEqual(self.workspace.current_structure_summary.name, "Structure A")
        self.assertEqual(self.workspace.current_structure_summary.atom_count, 2)
        self.assertEqual(self.workspace.current_structure_summary.species, ("Si2",))
        self.assertIn("PBC: X, Y, Z", self.workspace.structure_label.text())
        second = structure("Structure B", 5.0, "C")
        self.project.set_structure(second)
        self.workspace.refresh()
        self.assertEqual(self.workspace.current_structure_summary.name, "Structure B")
        self.assertEqual(self.workspace.current_structure_summary.species, ("C2",))
        self.assertEqual(self.project.get_structure().to_dict(), second.to_dict())

    def test_request_captures_independent_native_snapshot_and_canonical_payload(self):
        first = structure("Structure A", 4.0, "Si")
        self.project.set_structure(first)
        self.workspace.refresh()
        self.workspace.selected_ids = ["scf"]
        prepared = self.workspace.create_calculation_request(parameters={"accuracy": "high"})
        self.assertIsNot(prepared.structure_snapshot, self.project.get_structure())
        self.assertEqual(prepared.structure_snapshot.to_dict(), first.to_dict())
        self.assertEqual(prepared.backend_request.structure, first.to_dict())
        second = structure("Structure B", 5.0, "C")
        self.project.set_structure(second)
        prepared.structure_snapshot.atoms[0].x = 9.0
        self.assertEqual(self.project.get_structure().to_dict(), second.to_dict())
        self.assertEqual(prepared.backend_request.structure, first.to_dict())

    def test_typed_hubbard_terms_control_preserves_structured_values(self):
        from frontend.calculate.typed_parameter_controls import control_value, make_control
        control=make_control("hubbard_terms", [{"species":"Fe","manifold":"3d","u_eV":3.0}])
        self.assertEqual(control_value("hubbard_terms", control), [{"species":"Fe","manifold":"3d","u_eV":3.0}])

    def test_gui_created_dos_and_pdos_enable_private_postprocessing_workflows(self):
        self.project.set_structure(structure("DOS input"))
        self.workspace.refresh()
        for calculation_id, terminal in (("dos", "qe_dos"), ("pdos", "qe_projwfc")):
            self.workspace.selected_ids=[calculation_id]
            request=self.workspace.create_persistent_calculation(name=calculation_id)
            self.assertTrue(request.backend_request.parameters["postprocessing"])
            plan=self.workspace.calculation_service.compile_request(request)
            self.assertIn(terminal, [task.semantic_task_type for task in plan.tasks])

    def test_scf_and_bands_compile_through_existing_backend_plan_with_snapshot(self):
        first = structure("Bands Input")
        self.project.set_structure(first)
        self.workspace.refresh()
        self.workspace.selected_ids = ["bands"]
        plan = self.workspace.prepare_workflow(parameters={"accuracy": "standard"})
        self.assertEqual(plan.selected_calculations, ["bands"])
        self.assertEqual(plan.resolved_calculations, ["scf", "bands"])
        self.assertEqual(plan.structure, first.to_dict())
        self.assertIn("scf", plan.calculation_parameters)
        self.assertIn("bands", plan.calculation_parameters)
        self.assertEqual(self.workspace.calculation_request.structure_snapshot.to_dict(), first.to_dict())
        self.workspace._display_execution_plan()
        self.assertIn("Structure snapshot: Bands Input", self.workspace.execution_preview.text())

    def test_project_window_workspace_switch_refreshes_calculate_from_project(self):
        self.workspace.close()
        first = structure("Switch A", 4.0, "Si")
        self.project.set_structure(first)
        window = ProjectWindow(self.project)
        window._select_vertical(2)
        self.assertEqual(window.calculator.current_structure_summary.name, "Switch A")
        self.project.set_structure(structure("Switch B", 5.0, "C"))
        window._select_vertical(2)
        self.assertEqual(window.calculator.current_structure_summary.name, "Switch B")
        window._allow_close = True
        window.close()
        self.workspace = CalculateWorkspace(self.project)

    def test_periodic_workflow_rejects_nonperiodic_structure_without_mutation(self):
        molecule = Structure([Atom("H", 0.0, 0.0, 0.0)], [[10.0, 0.0, 0.0], [0.0, 10.0, 0.0], [0.0, 0.0, 10.0]], name="Molecule")
        molecule.periodic = [False, False, False]
        self.project.set_structure(molecule)
        before = self.project.get_structure().to_dict()
        self.workspace.refresh()
        self.workspace.selected_ids = ["bands"]
        with self.assertRaisesRegex(RuntimeError, "requires a valid periodic cell"):
            self.workspace.create_calculation_request()
        self.assertEqual(self.project.get_structure().to_dict(), before)


class CalculationServicePayloadTests(unittest.TestCase):
    def test_native_structure_payload_round_trip_preserves_geometry_and_pbc(self):
        project = Project("Payload")
        source = structure("Payload Structure", 6.0, "C")
        source.periodic = [True, False, True]
        project.set_structure(source)
        prepared = CalculationService(CALCULATIONS).create_request(project, ["scf"])
        restored = Structure.from_dict(prepared.backend_request.structure)
        self.assertEqual(restored.to_dict(), source.to_dict())
        np.testing.assert_allclose(restored.cell, source.cell)
