"""C8A QE post-processing expansion; raw artifacts only."""
from __future__ import annotations
import hashlib, json
from backend.compiler.execution_plan import PlannedTask
from backend.engines.qe.models import InvalidQEParameterError
from backend.dft.functionals import resolve
from dataclasses import replace
from backend.engines.qe.hybrid_bands import hybrid_band_contract, validate_hybrid_kpoint_capacity

def _sig(value): return hashlib.sha256(json.dumps(value,sort_keys=True,default=str).encode()).hexdigest()[:16]

def _pseudo_identity(values):
    if not isinstance(values, dict): return {}
    return {str(element): ({"filename": value.get("filename"), "sha256": value.get("sha256")} if isinstance(value, dict) else {"legacy_assignment": str(value)}) for element, value in sorted(values.items())}

def _path(value, label):
    if not isinstance(value, list) or len(value) < 2: raise InvalidQEParameterError("Choose a band path before generating this Band Structure calculation.")
    points=[]
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("coordinates"), (list,tuple)) or len(item["coordinates"]) != 3: raise InvalidQEParameterError(f"{label} points require three fractional coordinates.")
        count=int(item.get("points", 0))
        if count < 1: raise InvalidQEParameterError(f"{label} points require positive interpolation counts.")
        points.append({"label":str(item.get("label","")),"coordinates":[float(x) for x in item["coordinates"]],"points":count})
    return points

def _expand_phonon_path(path, points_per_segment=24):
    if not isinstance(path, list) or len(path) < 2: return path
    expanded = []
    for index, point in enumerate(path[:-1]):
        start = point["coordinates"]; end = path[index + 1]["coordinates"]
        count = max(2, int(point.get("points", points_per_segment)))
        for step in range(count):
            if index and step == 0: continue
            fraction = step / float(count - 1)
            expanded.append({"coordinates": [float(a) + fraction * (float(b) - float(a)) for a, b in zip(start, end)]})
    expanded.append({"coordinates": [float(value) for value in path[-1]["coordinates"]]})
    return expanded

def expand(request, tasks, parameters):
    selected=set(request.selected_calculations); by={task.calculation_id:task for task in tasks}; scf=by.get("scf")
    if not scf: return tasks
    result=[task for task in tasks if task.calculation_id not in {"bands","dos","pdos","charge_density","spin_density","electron_localization","electrostatic_potential","work_function","fermi_surface","hubbard_u","band_gap","effective_mass","bader_charge","charge_transfer","mulliken_population","magnetic_moment","orbital_texture","band_decomposed_charge","hybrid_electronic","phonon_dos"}]
    def add(name, semantic, tool, deps, params, inputs, outputs, metadata=None):
        signature=_sig({"semantic":semantic,"calculation_id":name,"purpose":(metadata or {}).get("purpose"),"structure":request.structure,"pseudopotentials":_pseudo_identity(request.parameters.get("pseudopotentials",{})),"parameters":params,"dependency_signatures":[dep.parameter_signature for dep in deps]}); task=PlannedTask(id=f"{request.id}:{semantic}:{signature}",calculation_id=name,semantic_task_type=semantic,engine_id="quantum_espresso",tool_id=tool,parameter_signature=signature,depends_on_task_ids=tuple(dep.id for dep in deps),parameters=params,structure_reference="request_snapshot",artifact_inputs=tuple(inputs),artifact_outputs=tuple(outputs),metadata=metadata or {}); result.append(task); return task
    if set(selected) & {"bands", "band_gap", "effective_mass", "hybrid_electronic"}:
        values=dict(parameters["bands"]); path=_path(values.get("kpath"),"Band structure")
        bands_purpose = "band_gap" if "band_gap" in selected else "effective_mass" if "effective_mass" in selected else "hybrid_electronic" if "hybrid_electronic" in selected else "bands"
        functional=resolve(request.parameters.get("xc_functional", request.parameters.get("functional", values.get("functional", "pbe"))))
        if functional.hybrid:
            scf_parameters=dict(scf.parameters); scf_parameters.update({"xc_functional": functional.id, "hybrid_band_path": path})
            mesh=scf_parameters.get("exx_q_mesh") or scf_parameters.get("kpoints", [1,1,1])
            contract=hybrid_band_contract(path, mesh, request.structure.get("periodic"))
            validate_hybrid_kpoint_capacity(contract)
            scf_parameters["hybrid_band_contract"]=contract
            scf=replace(scf, parameters=scf_parameters, parameter_signature=_sig({"semantic":"hybrid_scf_bands","structure":request.structure,"pseudopotentials":_pseudo_identity(request.parameters.get("pseudopotentials",{})),"parameters":scf_parameters}), artifact_outputs=tuple(sorted(set(scf.artifact_outputs+("qe_band_eigenvalues",)))), metadata={**scf.metadata, "hybrid_band":contract})
            result=[scf if task.calculation_id=="scf" else task for task in result]
            add("qe_bands","qe_bands","bands.x",[scf],{"filband":"bands.dat","hybrid_band_method":contract["method"]},["qe_save","qe_band_eigenvalues"],["BAND_STRUCTURE_RAW_DATA"],{"purpose":"hybrid_bands", "hybrid_band":contract})
        else:
            pw=add("qe_pw_bands","qe_pw_bands","pw.x",[scf],{**values,"band_path":path},["qe_save"],["qe_band_eigenvalues"],{"purpose":"bands"})
            add("qe_bands","qe_bands","bands.x",[pw],{"filband":"bands.dat"},["qe_save","qe_band_eigenvalues"],["BAND_STRUCTURE_RAW_DATA"],{"purpose":bands_purpose,"band_path":path})
    for public, terminal, tool, output in (("dos","qe_dos","dos.x","DOS_RAW_DATA"),("pdos","qe_projwfc","projwfc.x","PDOS_RAW_DATA")):
        if public in selected:
            values=dict(parameters[public]); mesh=values.get("dense_kpoints");
            if not isinstance(mesh,(list,tuple)) or len(mesh)!=3: raise InvalidQEParameterError(f"{public} requires dense_kpoints mesh.")
            nscf=add(f"qe_pw_nscf_{public}","qe_pw_nscf","pw.x",[scf],{**values,"kpoints":{"mode":"automatic","mesh":list(mesh),"shifts":[0,0,0]},"occupations":"tetrahedra"},["qe_save"],["qe_wavefunctions","qe_eigenvalues"],{"purpose":public,"private_nscf_contract":{"version":"v0.21-e1","parent_scf_task_id":scf.id,"state_inputs":["qe_charge_density","qe_save"],"required_outputs":["qe_wavefunctions","qe_eigenvalues"],"structure_reference":"request_snapshot","requires_shared_prefix_outdir":True}})
            add(terminal,terminal,tool,[nscf],values,["qe_save","qe_wavefunctions"],[output],{"purpose":public})
    if "band_decomposed_charge" in selected:
        values=dict(parameters.get("band_decomposed_charge", {}))
        if int(values.get("kpoint", 0)) < 1 or int(values.get("kband", 0)) < 1: raise InvalidQEParameterError("Band-decomposed charge density requires positive kpoint and kband indices.")
        add("qe_pp_band_decomposed","qe_pp","pp.x",[scf],{**values,"plot_kind":"band_decomposed_charge","artifact":"band_decomposed_charge.cube"},["qe_save"],["VOLUMETRIC_RAW_DATA"],{"purpose":"band_decomposed_charge","field":{"kind":"band_decomposed_charge","artifact":"band_decomposed_charge.cube","periodic":list(request.structure.get("periodic",[True,True,True])),"atoms":list(request.structure.get("atoms",[]))}})
    if "fermi_surface" in selected:
        values=dict(parameters.get("fermi_surface", {})); mesh=values.get("mesh", values.get("kmesh", [8,8,8]))
        nscf=add("qe_pw_nscf_fermi_surface","qe_pw_nscf","pw.x",[scf],{**values,"kpoints":{"mode":"automatic","mesh":list(mesh),"shifts":[0,0,0]},"occupations":"tetrahedra"},["qe_save"],["qe_wavefunctions","qe_eigenvalues"],{"purpose":"fermi_surface","private_nscf_contract":{"uniform_mesh":list(mesh)}})
        add("qe_fs","qe_fs","fs.x",[nscf],{**values,"mesh":list(mesh)},["qe_save","qe_eigenvalues"],["FERMI_SURFACE_BXSF"],{"purpose":"fermi_surface","result_type":"FermiSurfaceResult"})
    if "hubbard_u" in selected:
        values=dict(parameters.get("hubbard_u", {})); add("qe_hp","qe_hp","hp.x",[scf],values,["qe_save"],["HUBBARD_PARAMETER_RAW_DATA"],{"purpose":"hubbard_u","result_type":"HubbardParameterResult"})
    if set(selected) & {"bader_charge", "charge_transfer"}:
        values=dict(parameters.get("bader_charge", parameters.get("charge_transfer", {})))
        purpose = "charge_transfer" if "charge_transfer" in selected else "bader_charge"
        pp=add("qe_pp_bader","qe_pp","pp.x",[scf],{**values,"plot_kind":"charge","artifact":"bader_charge.cube"},["qe_save"],["BADER_CHARGE_CUBE"],{"purpose":purpose,"field":{"kind":"charge","artifact":"bader_charge.cube","periodic":list(request.structure.get("periodic",[True,True,True])),"atoms":list(request.structure.get("atoms",[]))}})
        add("qe_bader","qe_bader","bader",[pp],{"density_file":"../bader_charge.cube"},["BADER_CHARGE_CUBE"],["BADER_ACF"],{"purpose":purpose,"result_type":"BaderChargeResult"})
    if set(selected) & {"mulliken_population", "magnetic_moment"}:
        values=dict(parameters.get("mulliken_population", parameters.get("magnetic_moment", {})))
        purpose="magnetic_moment" if "magnetic_moment" in selected else "lowdin_population"
        add("qe_lowdin","qe_lowdin","projwfc.x",[scf],values,["qe_save"],["LOWDIN_POPULATION"],{"purpose":purpose,"result_type":"LowdinPopulationResult","field":{"atoms":list(request.structure.get("atoms",[]))}})
    if "orbital_texture" in selected:
        values=dict(parameters.get("orbital_texture", {})); values["filproj"]="orbital_character"
        path=_path(values.get("kpath") or dict(parameters.get("bands", {})).get("kpath"),"Orbital-character band structure")
        pw=add("qe_pw_bands","qe_pw_bands","pw.x",[scf], {**dict(scf.parameters),"band_path":path},["qe_save"],["qe_band_eigenvalues"],{"purpose":"orbital_character"})
        bands_task=add("qe_bands","qe_bands","bands.x",[pw],{"filband":"bands.dat"},["qe_save","qe_band_eigenvalues"],["BAND_STRUCTURE_RAW_DATA"],{"purpose":"orbital_character","band_path":path})
        add("qe_orbital","qe_projwfc","projwfc.x",[bands_task],values,["qe_save","qe_band_eigenvalues"],["ORBITAL_CHARACTER_RAW_DATA"],{"purpose":"orbital_character","result_type":"OrbitalCharacterResult"})
    for public, kind, output in (("charge_density","charge","VOLUMETRIC_RAW_DATA"),("spin_density","spin","VOLUMETRIC_RAW_DATA"),("electron_localization","elf","VOLUMETRIC_RAW_DATA"),("electrostatic_potential","potential","VOLUMETRIC_RAW_DATA"),("work_function","potential","VOLUMETRIC_RAW_DATA")):

        if public in selected:
            values=dict(parameters[public])
            if kind=="spin" and str(values.get("spin_treatment", "")).upper() not in {"COLLINEAR_SPIN", "COLLINEAR"}: raise InvalidQEParameterError("Spin density requires collinear spin treatment.")
            analysis={key:values.pop(key) for key in ("surface_normal","macro_window_A") if key in values}
            add("qe_pp","qe_pp","pp.x",[scf],{**values,"plot_kind":kind},["qe_save"],[output],{"purpose":public,"field":{"kind":kind,"artifact":kind+".cube","periodic":list(request.structure.get("periodic",[True,True,True])),"atoms":list(request.structure.get("atoms",[]))},"analysis":analysis})
    if "phonon_dos" in selected:
        ph=by.get("phonons")
        if ph is None: raise InvalidQEParameterError("phonon_dos requires phonons.")
        result=[task for task in result if task is not ph]
        qmesh=parameters.get("phonon_dos",{}).get("qmesh") or parameters.get("qmesh") or parameters.get("phonons",{}).get("qmesh") or [2,2,2]
        phonon_config = parameters.get("phonon_dos", {}) if isinstance(parameters.get("phonon_dos", {}), dict) else {}
        if not isinstance(qmesh,(list,tuple)) or len(qmesh)!=3 or any(int(x)<1 for x in qmesh): raise InvalidQEParameterError("phonon_dos qmesh must contain three positive integers.")
        ph_values=dict(parameters["phonons"]); ph_values.pop("q_point",None); ph_values["qmesh"]=[int(x) for x in qmesh]
        if phonon_config.get("tr2_ph") is not None:
            ph_values["tr2_ph"] = float(phonon_config["tr2_ph"])
        # E2 harmonic phonons (including DFT+U) are ordinary dynamical response
        # calculations; polar/LO-TO response belongs to the explicit polar DAG.
        ph_values["epsil"]=False
        ph=add("qe_ph","qe_ph","ph.x",[scf],ph_values,["qe_save"],["QE_DYNAMICAL_MATRIX_SET"],{"purpose":"harmonic_qmesh","qmesh":list(qmesh),"expected_q_count":int(qmesh[0])*int(qmesh[1])*int(qmesh[2])})
        q2r=add("qe_q2r","qe_q2r","q2r.x",[ph],{"fildyn":"dynamical-matrix","flfrc":"force_constants","zasr":"crystal"},["QE_DYNAMICAL_MATRIX_SET"],["FORCE_CONSTANTS"],{"purpose":"harmonic_ifc","qmesh":list(qmesh),"asr":"crystal"})
        dispersion_path=phonon_config.get("phonon_path") or parameters.get("phonon_path")
        path_points=int(phonon_config.get("path_points_per_segment", parameters.get("path_points_per_segment", 24)))
        if dispersion_path:
            original_path = dispersion_path
            dispersion_path=_expand_phonon_path(dispersion_path, path_points)
            vertex_indices=[]; cursor=0
            for vertex in original_path[:-1]:
                vertex_indices.append(cursor); cursor += max(2, int(vertex.get("points", path_points))) - 1
            vertex_indices.append(len(dispersion_path) - 1)
            add("qe_matdyn_dispersion","qe_matdyn","matdyn.x",[q2r],{"mode":"dispersion","flfrc":"force_constants","flfrq":"phonon_dispersion.freq","asr":"crystal","q_path":dispersion_path},["FORCE_CONSTANTS"],["PHONON_DISPERSION_RAW_DATA"],{"purpose":"phonon_dispersion","asr":"crystal","q_coordinate":"crystal_fractional","qmesh":list(qmesh),"expected_mode_count":3 * len(request.structure.get("atoms",())),"cell_A":request.structure.get("cell"),"high_symmetry_labels":[point.get("label","") for point in original_path],"high_symmetry_indices":vertex_indices,"path_points_per_segment":path_points,"path_convention":parameters.get("phonon_path_convention", "Quantum Studio canonical path recommendation")})
        dos_values={"mode":"dos","flfrc":"force_constants","fldos":"phonon_dos.dat","asr":"crystal","mesh":list(phonon_config.get("dos_mesh") or parameters.get("dos_mesh") or [12,12,12])}
        add("qe_matdyn_dos","qe_matdyn","matdyn.x",[q2r],dos_values,["FORCE_CONSTANTS"],["PHONON_DOS_RAW_DATA"],{"purpose":"phonon_dos","asr":"crystal","normalization":"3N modes per primitive cell","frequency_unit":"cm^-1","qmesh":list(qmesh),"expected_mode_count":3 * len(request.structure.get("atoms",()))})
    return result
