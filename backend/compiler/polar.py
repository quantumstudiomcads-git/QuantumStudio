"""E3B shared polar Gamma DFPT expansion."""
from __future__ import annotations
import hashlib, json
from backend.compiler.execution_plan import PlannedTask
from backend.engines.qe.models import InvalidQEParameterError

def expand_polar(request, tasks, parameters):
    if not (set(request.selected_calculations) & {"born_charges", "lo_to_splitting", "infrared", "dielectric_phonon"}):
        return tasks
    scf = next((task for task in tasks if task.calculation_id == "scf"), None)
    public = next((task for task in tasks if task.calculation_id == "born_charges"), None)
    if scf is None or public is None:
        raise InvalidQEParameterError("Born effective charges require a compatible SCF task.")
    values = dict(parameters.get("born_charges", {}))
    q = values.get("q_point", [0.0, 0.0, 0.0])
    if not isinstance(q, (list, tuple)) or len(q) != 3 or any(abs(float(item)) > 1e-12 for item in q):
        raise InvalidQEParameterError("Born effective charges require q = Gamma (0 0 0).")
    scf_values = dict(scf.parameters)
    occupation = str(scf_values.get("occupations", "fixed")).lower()
    if occupation in {"smearing", "tetrahedra", "tetrahedra_opt"} or scf_values.get("degauss") is not None:
        raise InvalidQEParameterError("Electric-field response requires fixed occupations; smearing is unsupported.")
    method = str(scf_values.get("spin_treatment", "SCALAR_NONSPIN")).upper()
    if method != "SCALAR_NONSPIN" or scf_values.get("soc") or scf_values.get("noncolin") or scf_values.get("hubbard_terms"):
        raise InvalidQEParameterError("E3B supports only scalar non-spin, non-SOC, non-DFT+U response.")
    polar_values = {**scf_values, **values, "q_point": [0.0, 0.0, 0.0], "epsil": True, "zeu": True, "trans": True, "ldisp": False, "fildyn": "polar_gamma"}
    signature = hashlib.sha256(json.dumps({"purpose":"polar_gamma_dfpt","structure":request.structure,"parameters":polar_values,"scf_signature":scf.parameter_signature}, sort_keys=True, default=str).encode()).hexdigest()[:16]
    task = PlannedTask(id=f"{request.id}:polar_gamma_dfpt:{signature}", calculation_id="qe_polar_gamma", semantic_task_type="qe_polar_gamma", engine_id="quantum_espresso", tool_id="ph.x", parameter_signature=signature, depends_on_task_ids=(scf.id,), parameters=polar_values, structure_reference="request_snapshot", artifact_inputs=("qe_save","qe_charge_density"), artifact_outputs=("POLAR_GAMMA_DFPT","QE_POLAR_DYNAMICAL_MATRIX"), metadata={"purpose":"polar_gamma_dfpt","q_point":[0.0,0.0,0.0],"polar_fildyn":"polar_gamma","expected_atom_count":len(request.structure.get("atoms",())),"atom_elements":[str(atom.get("element", "")) for atom in request.structure.get("atoms", ()) if isinstance(atom, dict)],"response_contract":{"epsil":True,"zeu":True,"trans":True,"ldisp":False}})
    result = [item for item in tasks if item is not public and item.calculation_id not in {"lo_to_splitting", "infrared", "dielectric_phonon"}] + [task]
    if {"lo_to_splitting", "dielectric_phonon"} & set(request.selected_calculations):
        ref_sig = hashlib.sha256(json.dumps({"purpose":"analytic_reference","polar":task.parameter_signature,"asr":"crystal"},sort_keys=True).encode()).hexdigest()[:16]
        result.append(PlannedTask(id=f"{request.id}:dynmat_polar:analytic_reference:{ref_sig}", calculation_id="qe_dynmat_analytic_reference", semantic_task_type="qe_dynmat", engine_id="quantum_espresso", tool_id="dynmat.x", parameter_signature=ref_sig, depends_on_task_ids=(task.id,), parameters={"direction":[0.0,0.0,0.0],"original_direction":[0.0,0.0,0.0],"asr":"crystal","fildyn":"polar_gamma","filout":"analytic_reference.dynmat.out","fileig":"analytic_reference.modes.eig","purpose":"analytic_reference"}, structure_reference="request_snapshot", artifact_inputs=("POLAR_GAMMA_DFPT",), artifact_outputs=("DYNMAT_ANALYTIC_REFERENCE",), metadata={"purpose":"analytic_reference","direction_unit_cartesian":[0.0,0.0,0.0],"parent_polar_task_id":task.id,"expected_mode_count":3*len(request.structure.get("atoms",()))}))
    for calculation_id, purpose in (("lo_to_splitting", "lo_to"), ("infrared", "infrared"), ("dielectric_phonon", "phonon_dielectric")):
        if calculation_id not in request.selected_calculations: continue
        values = dict(parameters.get(calculation_id, {}))
        values.update(dict((request.parameters or {}).get(calculation_id, {})))
        requested = values.get("directions") if purpose == "lo_to" else None
        directions = requested or ([[0.0, 0.0, 0.0]] if purpose == "phonon_dielectric" else [values.get("direction", [1.0, 0.0, 0.0])])
        if not isinstance(directions, (list, tuple)) or not directions:
            raise InvalidQEParameterError("Polar postprocessing directions must be a non-empty list.")
        for direction_index, original in enumerate(directions, start=1):
            if not isinstance(original, (list, tuple)) or len(original) != 3:
                raise InvalidQEParameterError("Polar postprocessing direction requires three components.")
            original = [float(x) for x in original]
            norm = sum(x*x for x in original) ** 0.5
            if purpose != "phonon_dielectric" and (norm <= 1e-15 or not all(__import__("math").isfinite(x) for x in original)):
                raise InvalidQEParameterError("Polar postprocessing direction must be finite and nonzero.")
            direction = [0.0, 0.0, 0.0] if purpose == "phonon_dielectric" else [x / norm for x in original]
            sig = hashlib.sha256(json.dumps({"purpose":purpose,"polar":task.parameter_signature,"direction":direction},sort_keys=True).encode()).hexdigest()[:16]
            stem = purpose if len(directions) == 1 else f"{purpose}_{direction_index}"
            result.append(PlannedTask(id=f"{request.id}:dynmat_polar:{purpose}:{sig}", calculation_id=f"qe_dynmat_{purpose}_{direction_index}", semantic_task_type="qe_dynmat", engine_id="quantum_espresso", tool_id="dynmat.x", parameter_signature=sig, depends_on_task_ids=(task.id,), parameters={"direction":direction,"original_direction":original,"asr":"crystal","fildyn":"polar_gamma","filout":f"{stem}.dynmat.out","fileig":f"{stem}.modes.eig","purpose":purpose}, structure_reference="request_snapshot", artifact_inputs=("POLAR_GAMMA_DFPT",), artifact_outputs=("DYNMAT_POLAR_OUTPUT",), metadata={"purpose":purpose,"direction_unit_cartesian":direction,"original_requested_direction":original,"parent_polar_task_id":task.id,"expected_mode_count":3*len(request.structure.get("atoms",()))}))
    return result
