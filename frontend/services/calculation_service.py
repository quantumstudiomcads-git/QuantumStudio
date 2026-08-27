"""Qt-free Calculate service and canonical Project-structure handoff."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import json
from math import isfinite
from typing import Any

import numpy as np
from ase.data import atomic_numbers

from backend.compiler.request_compiler import RequestCompiler
from backend.core.calculation_request import CalculationRequest
from frontend.core import Structure
from frontend.calculations.reconciliation import (
    CatalogReconciliationError,
    CalculationDescriptor,
    ExecutionSupport,
    reconcile_catalog,
)


_PERIODIC_WORKFLOWS = frozenset({"bands", "dos", "pdos", "nscf", "phonons", "phonon_dos", "boltztrap_bands", "electrical_conductivity", "seebeck", "thermal_conductivity_electronic", "power_factor", "carrier_concentration"})


@dataclass(frozen=True)
class StructureSummary:
    """Read-only description derived from the authoritative Project Structure."""

    name: str
    atom_count: int
    species: tuple[str, ...] = ()
    periodic: tuple[bool, bool, bool] = (False, False, False)
    cell_valid: bool = False
    dimensionality: int | None = None
    valid: bool = False
    message: str = ""


@dataclass(frozen=True)
class PreparedCalculationRequest:
    """A native Structure snapshot paired with the serializable backend request."""

    structure_snapshot: Structure
    summary: StructureSummary
    backend_request: CalculationRequest

    @property
    def id(self) -> str:
        return self.backend_request.id


class CalculationService:
    """Project-to-compiler service; it never accesses Builder widgets or mutates Project."""

    def __init__(self, calculations):
        self._calculations = tuple(calculations)
        self._calculation_map = {calculation.id: calculation for calculation in self._calculations}

    def get_calculation_map(self):
        return dict(self._calculation_map)

    def get_catalog_reconciliation_report(self):
        """Return the backend-supported status map through a Qt-free service boundary."""
        import backend.calculations  # noqa: F401
        from backend.calculations import registry
        registry.validate()
        return reconcile_catalog(self._calculations, registry, strict=True)

    def get_calculation_descriptors(self) -> tuple[CalculationDescriptor, ...]:
        return self.get_catalog_reconciliation_report().descriptors

    def validate_selected_calculations(self, selected_calculations) -> tuple[CalculationDescriptor, ...]:
        selected = tuple(str(item) for item in selected_calculations)
        if not selected:
            raise ValueError("Select at least one calculation before preparing a request.")
        descriptors = {item.id: item for item in self.get_calculation_descriptors()}
        unknown = [item for item in selected if item not in descriptors]
        if unknown:
            raise RuntimeError("Unknown calculation: " + ", ".join(unknown))
        unsupported = [item for item in selected if not descriptors[item].backend_supported]
        if unsupported:
            labels = ", ".join(
                f"{descriptors[item].info.name} ({descriptors[item].status_label})" for item in unsupported
            )
            raise RuntimeError(f"Only implemented calculations can be compiled: {labels}.")
        return tuple(descriptors[item] for item in selected)

    def resolve_calculation_order(self, selected_ids):
        resolved, visited, visiting = [], set(), set()

        def visit(calculation_id):
            if calculation_id in visited:
                return
            if calculation_id in visiting:
                raise RuntimeError(f"Circular calculation dependency detected: {calculation_id}")
            calculation = self._calculation_map.get(calculation_id)
            if calculation is None:
                raise RuntimeError(f"Unknown calculation: {calculation_id}")
            visiting.add(calculation_id)
            for dependency_id in self._get_dependencies(calculation):
                visit(dependency_id)
            visiting.remove(calculation_id)
            visited.add(calculation_id)
            resolved.append(calculation_id)

        for calculation_id in selected_ids:
            visit(calculation_id)
        return resolved

    @staticmethod
    def _get_dependencies(calculation):
        for attribute in ("dependencies", "depends_on", "requires"):
            value = getattr(calculation, attribute, None)
            if value is None:
                continue
            if isinstance(value, str):
                return [value]
            try:
                return list(value)
            except TypeError:
                return []
        return []

    @staticmethod
    def _cell_is_valid(structure: Structure) -> bool:
        try:
            cell = np.asarray(structure.cell, dtype=float)
        except (TypeError, ValueError):
            return False
        return bool(cell.shape == (3, 3) and np.all(np.isfinite(cell)) and abs(float(np.linalg.det(cell))) > 1.0e-10)

    @staticmethod
    def _periodic(structure: Structure) -> tuple[bool, bool, bool]:
        periodic = getattr(structure, "periodic", (False, False, False))
        if len(periodic) != 3 or not all(isinstance(value, (bool, np.bool_)) for value in periodic):
            raise ValueError("Structure PBC must contain three Boolean components.")
        return tuple(bool(value) for value in periodic)

    def summarize_structure(self, project) -> StructureSummary:
        try:
            return self.summarize_native_structure(project.get_structure())
        except Exception as error:
            return StructureSummary("", 0, message=f"Structure unavailable: {error}")

    def summarize_native_structure(self, structure) -> StructureSummary:
        """Summarize a native Structure or preserve lightweight legacy test compatibility."""
        if structure is None:
            return StructureSummary("", 0, message="No active structure. Create or import a structure in Builder first.")
        if not getattr(structure, "atoms", ()):
            return StructureSummary(
                str(getattr(structure, "name", "Active Structure")), 0,
                message="The active structure contains no atoms. Create or import a structure in Builder first.",
            )
        if not isinstance(structure, Structure):
            return StructureSummary(str(getattr(structure, "name", "Active Structure")), len(structure.atoms), valid=True)
        try:
            periodic = self._periodic(structure)
            positions = np.asarray([(atom.x, atom.y, atom.z) for atom in structure.atoms], dtype=float)
            if positions.shape != (len(structure.atoms), 3) or not np.all(np.isfinite(positions)):
                raise ValueError("Atomic positions must be finite Cartesian coordinates.")
            counts = Counter(atom.element for atom in structure.atoms)
            for species_name in counts:
                if species_name not in atomic_numbers:
                    raise ValueError(f"Invalid chemical species: {species_name}")
            composition = tuple(f"{symbol}{count if count != 1 else ''}" for symbol, count in sorted(counts.items()))
            return StructureSummary(
                name=structure.name or "Active Structure", atom_count=len(structure.atoms), species=composition,
                periodic=periodic, cell_valid=self._cell_is_valid(structure), dimensionality=sum(periodic), valid=True,
            )
        except Exception as error:
            return StructureSummary(structure.name or "Active Structure", len(getattr(structure, "atoms", ())), message=str(error))

    @staticmethod
    def _validate_summary_for_selection(summary, selected_calculations):
        if not summary.valid:
            raise RuntimeError(summary.message or "No valid calculation input structure is available.")
        selected = {str(item) for item in selected_calculations}
        if selected & _PERIODIC_WORKFLOWS and (not summary.cell_valid or not any(summary.periodic)):
            names = ", ".join(sorted(selected & _PERIODIC_WORKFLOWS))
            raise RuntimeError(f"{names} requires a valid periodic cell and at least one periodic direction.")

    def validate_structure(self, project, selected_calculations=()):
        structure = project.get_structure()
        summary = self.summarize_native_structure(structure)
        self._validate_summary_for_selection(summary, selected_calculations)
        return structure, summary

    def create_request(self, project, selected_calculations, parameters=None, execution_target="local", name=None) -> PreparedCalculationRequest:
        """Capture an independent native Structure snapshot and serializable backend payload."""
        selected = [str(item) for item in selected_calculations]
        self.validate_selected_calculations(selected)
        structure, summary = self.validate_structure(project, selected)
        snapshot = structure.copy()
        request_parameters = dict(parameters or {})
        if "bands" in selected and not request_parameters.get("kpath"):
            from frontend.builder.brillouin_zone.path_api import materialize_path, normalize_band_path, recommended_band_path
            recommendation = recommended_band_path(snapshot.to_dict())
            request_parameters["kpath"] = normalize_band_path(materialize_path(recommendation.segments, (True,) * len(recommendation.segments), 40))
        request = CalculationRequest(
            structure=snapshot.to_dict(), selected_calculations=selected,
            parameters=request_parameters, execution_target=str(execution_target),
            metadata={"structure_source": "project.structure", "structure_name": snapshot.name},
            name="" if name is None else str(name),
        )
        return PreparedCalculationRequest(snapshot, summary, request)

    def prepare_persisted_request(self, request: CalculationRequest) -> PreparedCalculationRequest:
        """Rebuild transient native state from one persisted request without using Project.structure."""
        if not isinstance(request, CalculationRequest):
            raise TypeError("Expected a CalculationRequest.")
        self.validate_selected_calculations(request.selected_calculations)
        snapshot = Structure.from_dict(request.structure)
        summary = self.summarize_native_structure(snapshot)
        self._validate_summary_for_selection(summary, request.selected_calculations)
        return PreparedCalculationRequest(snapshot, summary, request)

    def duplicate_request(self, request: CalculationRequest) -> CalculationRequest:
        duplicate_name = f"{request.name or request.calculation_id.replace('_', ' ').title()} Copy"
        return request.copy_with(new_id=True, name=duplicate_name)

    def update_request_parameters(self, request: CalculationRequest, parameters, *, name=None) -> CalculationRequest:
        from datetime import datetime, timezone
        changes = {"parameters": dict(parameters), "updated_at": datetime.now(timezone.utc).isoformat()}
        if name is not None:
            changes["name"] = str(name).strip()
        return request.copy_with(**changes)

    def update_request_from_project(self, request: CalculationRequest, project) -> CalculationRequest:
        from datetime import datetime, timezone
        structure, _ = self.validate_structure(project, request.selected_calculations)
        snapshot = structure.copy()
        metadata = dict(request.metadata)
        metadata.update({"structure_source": "project.structure", "structure_name": snapshot.name})
        return request.copy_with(
            structure=snapshot.to_dict(), metadata=metadata,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

    def compile_request(self, prepared_request: PreparedCalculationRequest):
        if not isinstance(prepared_request, PreparedCalculationRequest):
            raise TypeError("Expected a PreparedCalculationRequest.")
        # This package import registers the existing backend calculation catalog; no engine is executed.
        import backend.calculations  # noqa: F401
        return RequestCompiler(prepared_request.backend_request).compile()

    def qe_input_support(self, calculation_ids):
        """Report C4 QE generation support through the Calculate service boundary."""
        from backend.engines.qe import QuantumEspressoAdapter
        return tuple(
            {
                "calculation_id": str(calculation_id),
                "available": QuantumEspressoAdapter.is_supported(str(calculation_id)),
                "reason": QuantumEspressoAdapter.support_reason(str(calculation_id)),
            }
            for calculation_id in calculation_ids
        )

    def preview_qe_inputs(self, prepared_request: PreparedCalculationRequest):
        """Build in-memory QE input previews; never writes files or runs an engine."""
        from backend.engines.qe import QuantumEspressoAdapter
        if not isinstance(prepared_request, PreparedCalculationRequest):
            raise TypeError("Expected a PreparedCalculationRequest.")
        return QuantumEspressoAdapter().compile_plan(self.compile_request(prepared_request))

    def generate_qe_inputs(self, prepared_request: PreparedCalculationRequest, output_root):
        """Explicitly export a saved request's derived QE inputs without execution."""
        from backend.engines.qe import QuantumEspressoAdapter
        if not isinstance(prepared_request, PreparedCalculationRequest):
            raise TypeError("Expected a PreparedCalculationRequest.")
        return QuantumEspressoAdapter().write_plan(self.compile_request(prepared_request), output_root)

    def materialize_existing_qe_workflow(self, workflow_root):
        """Repair workflow-local QE pseudopotentials without re-resolving providers."""
        from backend.engines.qe import QuantumEspressoAdapter
        return QuantumEspressoAdapter().materialize_existing_workflow(workflow_root)

    def execution_workflow(self, prepared_request: PreparedCalculationRequest, workflow_root):
        """Normalize an already exported workflow for the generic local executor."""
        from backend.execution import normalize_adapter_tasks
        if not isinstance(prepared_request, PreparedCalculationRequest):
            raise TypeError("Expected a PreparedCalculationRequest.")
        root = Path(workflow_root)
        manifest = root / "manifest.json"
        if manifest.is_file():
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                data = None
            if isinstance(data, dict) and data.get("engine_id") == "quantum_espresso":
                from backend.engines.qe import QuantumEspressoAdapter
                return normalize_adapter_tasks(prepared_request.id, root, QuantumEspressoAdapter.tasks_from_manifest(root))
        return normalize_adapter_tasks(prepared_request.id, workflow_root, self.preview_engine_inputs(prepared_request))

    def workflow_input_available(self, plan) -> bool:
        """Return C4/C5A generation availability for a compiled plan."""
        if "wannierization" in plan.selected_calculations or set(plan.selected_calculations) & {"boltztrap_bands", "electrical_conductivity", "seebeck", "thermal_conductivity_electronic", "power_factor", "carrier_concentration"}:
            return True
        return all(item["available"] for item in self.qe_input_support(plan.resolved_calculations))

    def preview_engine_inputs(self, prepared_request: PreparedCalculationRequest):
        """Return all derived task inputs for C4 QE or C5A cross-engine previews."""
        plan = self.compile_request(prepared_request)
        if set(plan.selected_calculations) & {"boltztrap_bands", "electrical_conductivity", "seebeck", "thermal_conductivity_electronic", "power_factor", "carrier_concentration"}:
            from backend.engines.boltztrap2 import BoltzTraP2WorkflowAdapter
            return BoltzTraP2WorkflowAdapter().compile_plan(plan)[0]
        if "wannierization" in plan.selected_calculations:
            from backend.engines.wannier90 import Wannier90WorkflowAdapter
            return Wannier90WorkflowAdapter().compile_plan(plan)[0]
        from backend.engines.qe import QuantumEspressoAdapter
        return QuantumEspressoAdapter().compile_plan(plan).tasks

    def generate_engine_inputs(self, prepared_request: PreparedCalculationRequest, output_root):
        """Explicit derived export only; never discovers or executes an engine."""
        plan = self.compile_request(prepared_request)
        if set(plan.selected_calculations) & {"boltztrap_bands", "electrical_conductivity", "seebeck", "thermal_conductivity_electronic", "power_factor", "carrier_concentration"}:
            from backend.engines.boltztrap2 import BoltzTraP2WorkflowAdapter
            return BoltzTraP2WorkflowAdapter().write_plan(plan, output_root)
        if "wannierization" in plan.selected_calculations:
            from backend.engines.wannier90 import Wannier90WorkflowAdapter
            return Wannier90WorkflowAdapter().write_plan(plan, output_root)
        from backend.engines.qe import QuantumEspressoAdapter
        return QuantumEspressoAdapter().write_plan(plan, output_root)
