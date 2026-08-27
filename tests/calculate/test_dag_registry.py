"""C3 deterministic executable-registry and DAG planning tests."""

from __future__ import annotations

import os
import unittest

from PySide6.QtWidgets import QApplication

import backend.calculations  # noqa: F401
from backend.calculations import registry as active_registry
from backend.calculations.definition import CalculationDefinition
from backend.calculations.registry import CalculationRegistry, RegistryValidationError
from backend.compiler.calculation_compiler import CalculationCompiler, DependencyParameterConflictError
from backend.compiler.dependency_resolver import DependencyResolver, DependencyResolutionError
from backend.core.calculation_request import CalculationRequest
from frontend.calculate import CalculateWorkspace
from frontend.calculations.catalog import CALCULATIONS, CalculationInfo
from frontend.calculations.reconciliation import (
    CatalogReconciliationError,
    ExecutionSupport,
    reconcile_catalog,
)
from frontend.core import Atom, Project, Structure
from frontend.services.calculation_service import CalculationService

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def app():
    return QApplication.instance() or QApplication([])


def structure_payload(name="A", element="Si"):
    structure = Structure(
        [Atom(element, 0.0, 0.0, 0.0)],
        [[4.0, 0.0, 0.0], [0.0, 4.0, 0.0], [0.0, 0.0, 4.0]],
        name=name,
    )
    structure.periodic = [True, True, True]
    return structure.to_dict()


def request(selected, parameters=None, structure=None):
    return CalculationRequest(
        structure=structure_payload() if structure is None else structure,
        selected_calculations=list(selected),
        parameters=dict(parameters or {}),
        execution_target="local",
    )


def temporary_registry(*definitions):
    result = CalculationRegistry()
    for definition in definitions:
        result.register(definition)
    return result


class CatalogRegistryReconciliationTests(unittest.TestCase):
    def test_active_catalog_has_exact_implemented_mapping_and_explicit_nonimplemented_entries(self):
        report = CalculationService(CALCULATIONS).get_catalog_reconciliation_report()
        self.assertEqual(report.frontend_count, 147)
        self.assertEqual(report.backend_count, 22)
        self.assertEqual(report.invalid_mappings, ())
        self.assertEqual(set(report.implemented_ids), {item.id for item in active_registry.all()})
        self.assertEqual(len(report.planned_ids), 124)
        nscf = next(item for item in report.descriptors if item.id == "nscf")
        self.assertEqual(nscf.execution_support, ExecutionSupport.UNAVAILABLE)
        self.assertFalse(nscf.backend_supported)

    def test_duplicate_frontend_mapping_fails_and_backend_only_is_diagnostic(self):
        backend = temporary_registry(CalculationDefinition("scf", "SCF", "Test"))
        duplicate = [
            CalculationInfo("scf", "SCF", "Test", "QE", "", status="ready"),
            CalculationInfo("scf", "SCF duplicate", "Test", "QE", "", status="ready"),
        ]
        with self.assertRaisesRegex(CatalogReconciliationError, "Duplicate frontend"):
            reconcile_catalog(duplicate, backend)
        report = reconcile_catalog([], backend, strict=False)
        self.assertEqual(report.backend_only_ids, ("scf",))

    def test_planned_catalog_selection_is_browseable_but_not_compilable(self):
        app()
        project = Project("Planned")
        source = Structure([Atom("Si", 0.0, 0.0, 0.0)], [[4.0, 0.0, 0.0], [0.0, 4.0, 0.0], [0.0, 0.0, 4.0]])
        source.periodic = [True, True, True]
        project.set_structure(source)
        workspace = CalculateWorkspace(project)
        workspace.selected_ids = ["fermi_surface"]
        workspace._refresh_selection()
        self.assertFalse(workspace.compile_button.isEnabled())
        self.assertIn("Cannot prepare", workspace.execution_preview.text())
        with self.assertRaisesRegex(RuntimeError, "Only implemented"):
            workspace.create_calculation_request()
        workspace.close()


class DependencyDagTests(unittest.TestCase):
    def test_bands_plan_has_explicit_scf_edge_and_request_snapshot_reference(self):
        plan = CalculationCompiler(request(["bands"])).compile()
        self.assertEqual(plan.resolved_calculations, ["scf", "bands"])
        scf = plan.task_for_calculation("scf")
        bands = plan.task_for_calculation("bands")
        self.assertEqual(scf.depends_on_task_ids, ())
        self.assertEqual(bands.depends_on_task_ids, (scf.id,))
        self.assertEqual(bands.structure_reference, "request_snapshot")
        self.assertEqual(plan.metadata["dependency_graph"], {"scf": [], "bands": ["scf"]})

    def test_shared_scf_is_planned_once_and_order_is_registry_deterministic(self):
        plan = CalculationCompiler(request(["dos", "bands"])).compile()
        self.assertEqual(plan.resolved_calculations, ["scf", "bands", "dos"])
        self.assertEqual([task.calculation_id for task in plan.tasks].count("scf"), 1)
        scf_id = plan.task_for_calculation("scf").id
        self.assertEqual(plan.task_for_calculation("bands").depends_on_task_ids, (scf_id,))
        self.assertEqual(plan.task_for_calculation("dos").depends_on_task_ids, (scf_id,))

    def test_deep_phonon_dos_dag_is_topologically_ordered(self):
        plan = CalculationCompiler(request(["phonon_dos"])).compile()
        self.assertEqual(plan.resolved_calculations, ["scf", "phonons", "phonon_dos"])
        self.assertEqual(
            plan.task_for_calculation("phonon_dos").depends_on_task_ids,
            (plan.task_for_calculation("phonons").id,),
        )

    def test_cycle_and_missing_dependency_are_rejected_with_clear_errors(self):
        cycle_registry = temporary_registry(
            CalculationDefinition("a", "A", "Test", requires=("b",)),
            CalculationDefinition("b", "B", "Test", requires=("a",)),
        )
        with self.assertRaisesRegex(RegistryValidationError, "a -> b -> a"):
            cycle_registry.validate()
        with self.assertRaisesRegex(DependencyResolutionError, "a -> b -> a"):
            DependencyResolver(["a"], cycle_registry).build()

        missing_registry = temporary_registry(
            CalculationDefinition("a", "A", "Test", requires=("does_not_exist",)),
        )
        with self.assertRaisesRegex(RegistryValidationError, "requires unknown calculation"):
            missing_registry.validate()

    def test_plan_is_deterministic_and_explicit_user_parameters_override_defaults(self):
        source = structure_payload("Snapshot A", "Si")
        first = CalculationCompiler(request(["bands", "dos"], {"accuracy": "high", "ecutwfc": 77, "functional": "HSE"}, source)).compile()
        second = CalculationCompiler(request(["bands", "dos"], {"accuracy": "high", "ecutwfc": 77, "functional": "HSE"}, source)).compile()
        # Plan-local semantic task IDs are deterministic for a single persisted request.
        again = CalculationCompiler(CalculationRequest(
            structure=source, selected_calculations=["bands", "dos"], parameters={"accuracy": "high", "ecutwfc": 77, "functional": "HSE"},
            execution_target="local", id=first.calculation_id,
        )).compile()
        self.assertEqual(first.resolved_calculations, second.resolved_calculations)
        self.assertEqual([task.calculation_id for task in first.tasks], [task.calculation_id for task in second.tasks])
        self.assertEqual([task.id for task in first.tasks], [task.id for task in again.tasks])
        self.assertEqual(first.calculation_parameters["scf"]["ecutwfc"], 77)
        self.assertEqual(first.calculation_parameters["bands"]["functional"], "HSE")
        self.assertEqual(first.structure, source)

    def test_conflicting_shared_dependency_defaults_are_rejected(self):
        local_registry = temporary_registry(
            CalculationDefinition("scf", "SCF", "Test", parameters=("setting",)),
            CalculationDefinition("bands", "Bands", "Test", requires=("scf",), dependency_parameters={"scf": {"setting": "a"}}),
            CalculationDefinition("dos", "DOS", "Test", requires=("scf",), dependency_parameters={"scf": {"setting": "b"}}),
        )
        with self.assertRaisesRegex(DependencyParameterConflictError, "scf.setting"):
            CalculationCompiler(request(["bands", "dos"]), registry_instance=local_registry).compile()

    def test_persisted_request_compiles_from_its_snapshot_not_current_project_structure(self):
        project = Project("Snapshot")
        source_a = Structure.from_dict(structure_payload("A", "Si"))
        project.set_structure(source_a)
        service = CalculationService(CALCULATIONS)
        persisted = service.create_request(project, ["bands"]).backend_request
        source_b = Structure.from_dict(structure_payload("B", "C"))
        project.set_structure(source_b)
        plan = service.compile_request(service.prepare_persisted_request(persisted))
        self.assertEqual(plan.structure, source_a.to_dict())
        self.assertNotEqual(plan.structure, project.get_structure().to_dict())


if __name__ == "__main__":
    unittest.main()
