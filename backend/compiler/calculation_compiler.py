"""Compile reproducible public requests into deterministic engine-agnostic task DAGs."""
from __future__ import annotations
import hashlib
import json
from dataclasses import replace
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
        if (str(self.request.parameters.get("spin_treatment", "")).upper() == "SOC"
                and "pdos" in self.request.selected_calculations):
            raise ValueError("SOC PDOS projector/spinor decomposition is not yet supported.")
        graph = DependencyResolver(self.request.selected_calculations, self.registry).build()
        defaults = self._shared_dependency_defaults(graph.ordered_calculations)
        parameters = ParameterResolver(self.request.parameters, self.registry).resolve(list(graph.ordered_calculations), defaults, self.request.structure)
        from backend.dft.functionals import hybrid_capability
        capability = hybrid_capability(self.request.parameters.get("xc_functional", "pbe"), self.request.selected_calculations)
        if capability != "SUPPORTED":
            if capability == "UNSUPPORTED_BY_QE_PHONON": raise ValueError("Quantum ESPRESSO ph.x does not support hybrid functionals for this workflow.")
            raise ValueError("Current hybrid NSCF-dependent workflow is not yet implemented in Quantum Studio.")
        if "raman" in self.request.selected_calculations:
            self._validate_raman_contract(parameters)
        if set(self.request.selected_calculations) & {"phonons", "phonon_dos", "phonon_band_structure"}:
            self._validate_hubbard_phonon_contract(parameters)
        tasks = self._public_tasks(graph, parameters)
        if "raman" in self.request.selected_calculations:
            raman_task = next(task for task in tasks if task.calculation_id == "raman")
            sig = _signature({"purpose":"raman_postprocess", "parent":raman_task.parameter_signature})
            tasks.append(PlannedTask(id=f"{self.request.id}:dynmat_raman:{sig}", calculation_id="qe_dynmat_raman", semantic_task_type="qe_dynmat", engine_id="quantum_espresso", tool_id="dynmat.x", parameter_signature=sig, depends_on_task_ids=(raman_task.id,), parameters={"direction":[0.0,0.0,0.0],"original_direction":[0.0,0.0,0.0],"asr":"crystal","filout":"raman.dynmat.out","fileig":"raman.modes.eig","purpose":"raman"}, structure_reference="request_snapshot", artifact_inputs=("QE_RAMAN_RESPONSE",), artifact_outputs=("RAMAN_MODE_RESPONSE",), metadata={"purpose":"raman","parent_raman_task_id":raman_task.id,"expected_mode_count":3*len(self.request.structure.get("atoms",()))}))
        if set(self.request.selected_calculations) & {"dielectric", "absorption", "refractive_index", "extinction_coefficient", "reflectivity", "energy_loss", "optical_conductivity"}:
            from backend.compiler.optical import expand_optical
            tasks = expand_optical(self.request, tasks, parameters)
        elif "wannierization" in self.request.selected_calculations:
            tasks = self._expand_wannierization(tasks, parameters)
        elif "electron_phonon" in self.request.selected_calculations:
            tasks = self._expand_electron_phonon(tasks, parameters)
        elif set(self.request.selected_calculations) & {"boltztrap_bands", "electrical_conductivity", "seebeck", "thermal_conductivity_electronic", "power_factor", "carrier_concentration"}:
            from backend.compiler.boltztrap2 import expand_boltztrap2
            tasks = expand_boltztrap2(self.request, tasks, parameters)
        if set(self.request.selected_calculations) & {"born_charges", "lo_to_splitting", "infrared", "dielectric_phonon"}:
            from backend.compiler.polar import expand_polar
            tasks = expand_polar(self.request, tasks, parameters)
        if (set(self.request.selected_calculations) & {"bands","dos","pdos","charge_density","spin_density","electron_localization","electrostatic_potential","work_function","fermi_surface","hubbard_u","band_gap","effective_mass","bader_charge","charge_transfer","mulliken_population","magnetic_moment","band_decomposed_charge","orbital_texture","hybrid_electronic","phonon_dos","phonon_band_structure"}) and (self.request.parameters.get("postprocessing") or bool(set(self.request.selected_calculations) & {"phonon_dos", "phonon_band_structure"})):
            from backend.compiler.postprocessing import expand
            tasks = expand(self.request, tasks, parameters)
        if "phonons" in self.request.selected_calculations:
            tasks = [replace(task, artifact_outputs=("QE_DYNAMICAL_MATRIX",), metadata={**task.metadata, "purpose": "gamma_phonons", "expected_mode_count": 3 * len(self.request.structure.get("atoms", ())), "q_point": [0.0, 0.0, 0.0]}) if task.calculation_id == "phonons" else task for task in tasks]
        plan = ExecutionPlan(calculation_id=self.request.id, selected_calculations=list(self.request.selected_calculations), resolved_calculations=[task.calculation_id for task in tasks], execution_target=self.request.execution_target, parameters=dict(self.request.parameters), calculation_parameters=parameters, structure=dict(self.request.structure), tasks=tasks)
        plan.metadata.update({"parameters": parameters, "dependency_graph": ({task.id: list(task.depends_on_task_ids) for task in tasks} if ({"wannierization", "electron_phonon", "boltztrap_bands", "electrical_conductivity", "seebeck", "thermal_conductivity_electronic", "power_factor", "carrier_concentration"} & set(self.request.selected_calculations)) else {item: list(graph.dependencies_for(item)) for item in graph.ordered_calculations}), "parameter_precedence": ["schema_defaults", "accuracy_preset", "workflow_dependency_defaults", "structure_derived_defaults", "explicit_request_parameters"], "structure_reference": "request_snapshot"})
        return plan

    def _validate_hubbard_phonon_contract(self, parameters):
        """Apply the QE 7.6 PHonon+U restrictions before engine preparation."""
        requested = self.request.parameters
        terms = requested.get("hubbard_terms", [])
        if not terms:
            return
        projector = str(requested.get("hubbard_projector", "atomic")).strip().lower()
        if projector != "atomic":
            raise ValueError("QE 7.6 DFPT+U phonons require Hubbard_projectors='atomic'.")
        kind = int(requested.get("lda_plus_u_kind", 0))
        if kind != 0:
            raise ValueError("QE 7.6 DFPT+U phonons support only the standard rotationally invariant Hubbard kind (lda_plus_u_kind=0).")
        spin = str(requested.get("spin_treatment", "SCALAR_NONSPIN")).upper()
        if spin in {"NONCOLLINEAR", "SOC"} or requested.get("noncolin") or requested.get("soc"):
            raise ValueError("QE 7.6 DFPT+U phonons do not support noncollinear or SOC Hubbard calculations.")
        species = [str(term.get("species", "")).strip() for term in terms if isinstance(term, dict)]
        if len(species) != len(terms) or any(not item for item in species):
            raise ValueError("Hubbard phonon terms must be structured species/manifold/U mappings.")
        if len(set(species)) != len(species):
            raise ValueError("QE 7.6 DFPT+U phonons support at most one Hubbard channel per atom type.")

    def _validate_raman_contract(self, parameters):
        requested = self.request.parameters
        functional = str(requested.get("xc_functional", requested.get("functional", "pbe"))).lower()
        if functional in {"lda", "pz"}: functional = "pz"
        if functional != "pz":
            raise ValueError("Quantum ESPRESSO 7.6 native Raman response is supported only for LDA/PZ.")
        spin = str(requested.get("spin_treatment", "SCALAR_NONSPIN")).upper()
        if spin not in {"SCALAR_NONSPIN", "SCALAR_NONMAGNETIC"}:
            raise ValueError("Native Raman response requires a scalar non-spin-polarized calculation.")
        q = requested.get("q_point", (0.0, 0.0, 0.0))
        if q is not None and any(abs(float(v)) > 1.0e-12 for v in q):
            raise ValueError("Native Raman response is supported only at Gamma.")
        if requested.get("smearing") or str(requested.get("occupations", "fixed")).lower() not in {"fixed", "fixed_occupations"}:
            raise ValueError("Native Raman response requires fixed occupations and no smearing.")
        pseudos = requested.get("pseudopotentials", {})
        if not isinstance(pseudos, dict) or not pseudos:
            raise ValueError("Native Raman response requires explicit norm-conserving pseudopotential provenance.")
        for element, value in pseudos.items():
            kind = str(value.get("pseudo_type", "")) if isinstance(value, dict) else ""
            if kind.upper() != "NC":
                raise ValueError(f"Quantum ESPRESSO 7.6 Raman requires norm-conserving pseudopotentials; {element} is {kind or 'unknown'}.")
    def _pseudopotential_identity(self):
        values = self.request.parameters.get("pseudopotentials", {})
        if not isinstance(values, dict): return {}
        return {str(element): ({"sha256": value.get("sha256"), "filename": value.get("filename")} if isinstance(value, dict) else {"legacy_assignment": str(value)}) for element, value in sorted(values.items())}

    def _public_tasks(self, graph, parameters):
        ids = {item: f"{self.request.id}:{item}" for item in graph.ordered_calculations}
        pseudo_identity = self._pseudopotential_identity()
        return [PlannedTask(id=ids[item], calculation_id=item, semantic_task_type=item, engine_id=self.registry.get(item).engine, tool_id=None, parameter_signature=_signature({"calculation_id": item, "structure": self.request.structure, "parameters": parameters[item], "pseudopotentials": pseudo_identity if self.registry.get(item).engine == "quantum_espresso" else {}}), depends_on_task_ids=tuple(ids[dep] for dep in graph.dependencies_for(item)), parameters=dict(parameters[item]), structure_reference="request_snapshot", artifact_outputs=("qe_charge_density", "qe_save") if item == "scf" else (), metadata={"workflow": self.registry.get(item).workflow, "dependency_level": graph.level_for(item)}) for item in graph.ordered_calculations]

    def _expand_wannierization(self, tasks, parameters):
        settings = WannierInputSettings.from_parameters(self.request.parameters)
        scf = next(task for task in tasks if task.calculation_id == "scf")
        public = next(task for task in tasks if task.calculation_id == "wannierization")
        nscf_parameters = dict(parameters["scf"])
        nscf_parameters.update({"kpoints": {"mode": "automatic", "mesh": list(settings.mp_grid), "shifts": [0, 0, 0]}, "nbnd": settings.num_bands, "wannier_mp_grid": list(settings.mp_grid)})
        if str(self.request.parameters.get("e5_stage", "")).upper() == "FINAL_PRODUCT":
            from backend.engines.epw.grid import qe_full_grid_card
            nscf_parameters["epw_full_grid"] = list(settings.mp_grid)
        signature = _signature({"semantic_task_type": "qe_pw_nscf", "purpose": "wannier", "structure": self.request.structure, "pseudopotentials": self._pseudopotential_identity(), "parameters": nscf_parameters})
        nscf = PlannedTask(id=f"{self.request.id}:qe_pw_nscf:{signature}", calculation_id="qe_pw_nscf", semantic_task_type="qe_pw_nscf", engine_id="quantum_espresso", tool_id="pw.x", parameter_signature=signature, depends_on_task_ids=(scf.id,), parameters=nscf_parameters, structure_reference="request_snapshot", artifact_inputs=("qe_charge_density", "qe_save"), artifact_outputs=("qe_wavefunctions", "qe_eigenvalues"), metadata={"purpose": "wannier", "public_calculation_id": public.calculation_id, "private_nscf_contract": {"version": "v0.21-e1", "parent_scf_task_id": scf.id, "state_inputs": ["qe_charge_density", "qe_save"], "required_outputs": ["qe_wavefunctions", "qe_eigenvalues"], "structure_reference": "request_snapshot", "requires_shared_prefix_outdir": True}})
        seed = f"qs_{self.request.id.replace('-', '_')[:16]}"
        pp = PlannedTask(id=f"{self.request.id}:wannier90_preprocess", calculation_id="wannier90_preprocess", semantic_task_type="wannier90_preprocess", engine_id="wannier90", tool_id="wannier90.x", parameter_signature=_signature({"settings": settings, "stage": "preprocess"}), depends_on_task_ids=(nscf.id,), parameters={"seedname": seed, "wannier": settings}, structure_reference="request_snapshot", artifact_inputs=("qe_wavefunctions",), artifact_outputs=("wannier_nnkp",), metadata={"command": ["wannier90.x", "-pp", seed]})
        pw2 = PlannedTask(id=f"{self.request.id}:qe_pw2wannier90", calculation_id="qe_pw2wannier90", semantic_task_type="qe_pw2wannier90", engine_id="quantum_espresso", tool_id="pw2wannier90.x", parameter_signature=_signature({"seed": seed, "stage": "pw2wannier90"}), depends_on_task_ids=(nscf.id, pp.id), parameters={"seedname": seed, "wannier": settings}, structure_reference="request_snapshot", artifact_inputs=("qe_wavefunctions", "wannier_nnkp"), artifact_outputs=("wannier_amn", "wannier_mmn", "wannier_eig"), metadata={})
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
        ph = PlannedTask(id=f"{self.request.id}:qe_ph_epw", calculation_id="qe_ph_epw", semantic_task_type="qe_ph_epw", engine_id="quantum_espresso", tool_id="ph.x", parameter_signature=_signature({"q":epw.nq_coarse}), depends_on_task_ids=(scf.id,), parameters={"qmesh":list(epw.nq_coarse),"purpose":"epw","fildvscf":"dvscf"}, structure_reference="request_snapshot", artifact_inputs=("qe_save",), artifact_outputs=("qe_dynamical_matrix","qe_dvscf","qe_qpoint_metadata"), metadata={"purpose":"epw"})
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
