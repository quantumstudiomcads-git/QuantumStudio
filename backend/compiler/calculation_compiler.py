"""Compile reproducible public requests into deterministic engine-agnostic task DAGs."""
from __future__ import annotations
import hashlib
import json
from typing import Any
from backend.calculations.registry import CalculationRegistry, registry
from backend.compiler.dependency_resolver import DependencyResolver
from backend.compiler.execution_plan import ExecutionPlan, PlannedTask
from backend.compiler.parameter_resolver import ParameterResolver
from backend.core.calculation_request import CalculationRequest
from backend.engines.wannier90.models import WannierInputSettings

class DependencyParameterConflictError(RuntimeError): pass

def _signature(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]

class CalculationCompiler:
    def __init__(self, request=None, *, calculation_id=None, selected_calculations=None, execution_target="local", registry_instance: CalculationRegistry | None = None):
        if request is None:
            if selected_calculations is None: raise TypeError("CalculationCompiler requires a CalculationRequest or selected_calculations.")
            request = CalculationRequest(structure={}, selected_calculations=list(selected_calculations), execution_target=execution_target)
            if calculation_id is not None: request.id = str(calculation_id)
        if not isinstance(request, CalculationRequest): raise TypeError("CalculationCompiler requires a CalculationRequest.")
        self.request, self.registry = request, registry if registry_instance is None else registry_instance

    def compile(self) -> ExecutionPlan:
        graph = DependencyResolver(self.request.selected_calculations, self.registry).build()
        defaults = self._shared_dependency_defaults(graph.ordered_calculations)
        parameters = ParameterResolver(self.request.parameters, self.registry).resolve(list(graph.ordered_calculations), defaults, self.request.structure)
        tasks = self._public_tasks(graph, parameters)
        if "wannierization" in self.request.selected_calculations:
            tasks = self._expand_wannierization(tasks, parameters)
        elif "electron_phonon" in self.request.selected_calculations:
            tasks = self._expand_electron_phonon(tasks, parameters)
        elif set(self.request.selected_calculations) & {"boltztrap_bands", "electrical_conductivity", "seebeck", "thermal_conductivity_electronic", "power_factor", "carrier_concentration"}:
            from backend.compiler.boltztrap2 import expand_boltztrap2
            tasks = expand_boltztrap2(self.request, tasks, parameters)
        plan = ExecutionPlan(calculation_id=self.request.id, selected_calculations=list(self.request.selected_calculations), resolved_calculations=[task.calculation_id for task in tasks], execution_target=self.request.execution_target, parameters=dict(self.request.parameters), calculation_parameters=parameters, structure=dict(self.request.structure), tasks=tasks)
        plan.metadata.update({"parameters": parameters, "dependency_graph": ({task.id: list(task.depends_on_task_ids) for task in tasks} if ({"wannierization", "electron_phonon", "boltztrap_bands", "electrical_conductivity", "seebeck", "thermal_conductivity_electronic", "power_factor", "carrier_concentration"} & set(self.request.selected_calculations)) else {item: list(graph.dependencies_for(item)) for item in graph.ordered_calculations}), "parameter_precedence": ["schema_defaults", "accuracy_preset", "workflow_dependency_defaults", "structure_derived_defaults", "explicit_request_parameters"], "structure_reference": "request_snapshot"})
        return plan

    def _public_tasks(self, graph, parameters):
        ids = {item: f"{self.request.id}:{item}" for item in graph.ordered_calculations}
        return [PlannedTask(id=ids[item], calculation_id=item, semantic_task_type=item, engine_id=self.registry.get(item).engine, tool_id=None, parameter_signature=_signature(parameters[item]), depends_on_task_ids=tuple(ids[dep] for dep in graph.dependencies_for(item)), parameters=dict(parameters[item]), structure_reference="request_snapshot", artifact_outputs=("qe_charge_density", "qe_save") if item == "scf" else (), metadata={"workflow": self.registry.get(item).workflow, "dependency_level": graph.level_for(item)}) for item in graph.ordered_calculations]

    def _expand_wannierization(self, tasks, parameters):
        settings = WannierInputSettings.from_parameters(self.request.parameters)
        scf = next(task for task in tasks if task.calculation_id == "scf")
        public = next(task for task in tasks if task.calculation_id == "wannierization")
        nscf_parameters = dict(parameters["scf"])
        nscf_parameters.update({"kpoints": {"mode": "automatic", "mesh": list(settings.mp_grid), "shifts": [0, 0, 0]}, "nbnd": settings.num_bands, "wannier_mp_grid": list(settings.mp_grid)})
        signature = _signature({"semantic_task_type": "qe_pw_nscf", "purpose": "wannier", "parameters": nscf_parameters})
        nscf = PlannedTask(id=f"{self.request.id}:qe_pw_nscf:{signature}", calculation_id="qe_pw_nscf", semantic_task_type="qe_pw_nscf", engine_id="quantum_espresso", tool_id="pw.x", parameter_signature=signature, depends_on_task_ids=(scf.id,), parameters=nscf_parameters, structure_reference="request_snapshot", artifact_inputs=("qe_charge_density", "qe_save"), artifact_outputs=("qe_wavefunctions", "qe_eigenvalues"), metadata={"purpose": "wannier", "public_calculation_id": public.calculation_id})
        seed = f"qs_{self.request.id.replace('-', '_')[:16]}"
        pp = PlannedTask(id=f"{self.request.id}:wannier90_preprocess", calculation_id="wannier90_preprocess", semantic_task_type="wannier90_preprocess", engine_id="wannier90", tool_id="wannier90.x", parameter_signature=_signature({"settings": settings, "stage": "preprocess"}), depends_on_task_ids=(nscf.id,), parameters={"seedname": seed, "wannier": settings}, structure_reference="request_snapshot", artifact_inputs=("qe_wavefunctions",), artifact_outputs=("wannier_nnkp",), metadata={"command": ["wannier90.x", "-pp", seed]})
        pw2 = PlannedTask(id=f"{self.request.id}:qe_pw2wannier90", calculation_id="qe_pw2wannier90", semantic_task_type="qe_pw2wannier90", engine_id="quantum_espresso", tool_id="pw2wannier90.x", parameter_signature=_signature({"seed": seed, "stage": "pw2wannier90"}), depends_on_task_ids=(nscf.id, pp.id), parameters={"seedname": seed}, structure_reference="request_snapshot", artifact_inputs=("qe_wavefunctions", "wannier_nnkp"), artifact_outputs=("wannier_amn", "wannier_mmn", "wannier_eig"), metadata={})
        run = PlannedTask(id=f"{self.request.id}:wannier90_run", calculation_id="wannier90_run", semantic_task_type="wannier90_run", engine_id="wannier90", tool_id="wannier90.x", parameter_signature=_signature({"settings": settings, "stage": "run"}), depends_on_task_ids=(pp.id, pw2.id), parameters={"seedname": seed, "wannier": settings}, structure_reference="request_snapshot", artifact_inputs=("wannier_nnkp", "wannier_amn", "wannier_mmn", "wannier_eig"), artifact_outputs=("wannier_hr", "wannier_centres"), metadata={"command": ["wannier90.x", seed]})
        return [task for task in tasks if task is not public] + [nscf, pp, pw2, run]

    def _expand_electron_phonon(self, tasks, parameters):
        from backend.engines.epw.models import EPWSettings, EPWMeshMismatchError
        settings = WannierInputSettings.from_parameters(self.request.parameters)
        epw = EPWSettings.from_parameters(self.request.parameters)
        if tuple(settings.mp_grid) != epw.nk_coarse:
            raise EPWMeshMismatchError("Wannier mp_grid must equal EPW nk_coarse.")
        scf = next(task for task in tasks if task.calculation_id == "scf")
        public = next(task for task in tasks if task.calculation_id == "electron_phonon")
        base = self._expand_wannierization([task for task in tasks if task is not public] + [PlannedTask(id=public.id, calculation_id="wannierization", semantic_task_type="wannierization", parameters={})], {**parameters, "wannierization": {}})
        # The C5A expansion provides the compatible signed NSCF/Wannier chain.
        nscf = next(task for task in base if task.semantic_task_type == "qe_pw_nscf")
        run = next(task for task in base if task.semantic_task_type == "wannier90_run")
        ph = PlannedTask(id=f"{self.request.id}:qe_ph_epw", calculation_id="qe_ph_epw", semantic_task_type="qe_ph_epw", engine_id="quantum_espresso", tool_id="ph.x", parameter_signature=_signature({"q":epw.nq_coarse}), depends_on_task_ids=(scf.id,), parameters={"qmesh":list(epw.nq_coarse)}, structure_reference="request_snapshot", artifact_inputs=("qe_save",), artifact_outputs=("qe_dynamical_matrix","qe_dvscf","qe_qpoint_metadata"), metadata={"purpose":"epw"})
        task = PlannedTask(id=f"{self.request.id}:epw_run", calculation_id="epw_run", semantic_task_type="epw_run", engine_id="epw", tool_id="epw.x", parameter_signature=_signature({"epw":epw,"nscf":nscf.parameter_signature}), depends_on_task_ids=(run.id,ph.id), parameters={"epw":epw}, structure_reference="request_snapshot", artifact_inputs=("qe_save","qe_wavefunctions","wannier_nnkp","wannier_amn","wannier_mmn","wannier_hr","qe_dynamical_matrix","qe_dvscf"), artifact_outputs=("epw_electron_phonon_data","epw_scattering_rates"), metadata={"external_wannier":True})
        return base + [ph, task]
    def _shared_dependency_defaults(self, ordered_calculations):
        resolved, origins = {}, {}
        for calculation_id in ordered_calculations:
            for dependency_id, values in self.registry.get(calculation_id).dependency_parameters.items():
                target = resolved.setdefault(dependency_id, {})
                for parameter, value in values.items():
                    key = (dependency_id, parameter)
                    if parameter in target and target[parameter] != value:
                        raise DependencyParameterConflictError(f"Dependency parameter conflict for '{dependency_id}.{parameter}': '{origins[key]}' requires {target[parameter]!r}, but '{calculation_id}' requires {value!r}.")
                    target[parameter], origins[key] = value, calculation_id
        return resolved
