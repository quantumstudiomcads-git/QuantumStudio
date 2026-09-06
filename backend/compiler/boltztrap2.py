"""Private C5C task expansion, isolated from public calculation definitions."""
from __future__ import annotations
from dataclasses import replace
from backend.compiler.calculation_compiler import _signature
from backend.compiler.execution_plan import PlannedTask
from backend.engines.boltztrap2.models import BoltzTraP2Settings, BTP2SettingsError, RelaxationTimeModel

INTENTS=frozenset({"boltztrap_bands","electrical_conductivity","seebeck","thermal_conductivity_electronic","power_factor","carrier_concentration"})

def _outputs(intents, model):
    absolute=model is RelaxationTimeModel.CONSTANT_RELAXATION_TIME
    names={"seebeck":"SEEBECK_DATA","carrier_concentration":"CARRIER_CONCENTRATION_DATA","electrical_conductivity":"SIGMA" if absolute else "SIGMA_OVER_TAU","thermal_conductivity_electronic":"KAPPA_E" if absolute else "KAPPA_E_OVER_TAU","power_factor":"POWER_FACTOR" if absolute else "POWER_FACTOR_OVER_TAU"}
    return tuple(dict.fromkeys(names[item] for item in intents))

def expand_boltztrap2(request,tasks,parameters):
    selected=tuple(item for item in request.selected_calculations if item in INTENTS); transport=tuple(item for item in selected if item!="boltztrap_bands")
    settings=BoltzTraP2Settings.from_parameters(request.parameters,require_transport=bool(transport))
    periodic=tuple(bool(item) for item in request.structure.get("periodic",()))
    if len(periodic)!=3: raise BTP2SettingsError("Structure PBC must contain three Boolean components.")
    if any(not enabled and settings.transport_k_mesh[index]!=1 for index,enabled in enumerate(periodic)): raise BTP2SettingsError("BoltzTraP2 transport_k_mesh must use 1 along every non-periodic axis.")
    is_2d=periodic==(True,True,False); absolute_intents={"electrical_conductivity","thermal_conductivity_electronic","power_factor"}&set(transport)
    if is_2d and absolute_intents and settings.relaxation_time_model is RelaxationTimeModel.CONSTANT_RELAXATION_TIME and settings.effective_thickness is None: raise BTP2SettingsError("Absolute 2D transport coefficients require explicit effective_thickness in angstrom; vacuum is not physical thickness.")
    scf=next(task for task in tasks if task.calculation_id=="scf")
    scf_parameters=dict(scf.parameters); scf_mesh=scf_parameters.get("kpoints", [1,1,1])
    if isinstance(scf_mesh,dict): scf_mesh=list(scf_mesh.get("mesh", [1,1,1]))
    else: scf_mesh=list(scf_mesh)
    for index,enabled in enumerate(periodic):
        if not enabled: scf_mesh[index]=1
    if scf_parameters.get("kpoints") != scf_mesh:
        scf_parameters["kpoints"]=scf_mesh; scf=replace(scf,parameters=scf_parameters,parameter_signature=_signature(scf_parameters)); tasks=[scf if task.calculation_id=="scf" else task for task in tasks]
    nscf_parameters=dict(scf_parameters); nscf_parameters.update({"kpoints":{"mode":"automatic","mesh":list(settings.transport_k_mesh),"shifts":[0,0,0]},"nbnd":settings.num_bands,"transport_k_mesh":list(settings.transport_k_mesh)})
    signature=_signature({"semantic_task_type":"qe_pw_nscf_btp2","purpose":"boltztrap2_transport","parameters":nscf_parameters})
    nscf=PlannedTask(id=f"{request.id}:qe_pw_nscf_btp2:{signature}",calculation_id="qe_pw_nscf_btp2",semantic_task_type="qe_pw_nscf_btp2",engine_id="quantum_espresso",tool_id="pw.x",parameter_signature=signature,depends_on_task_ids=(scf.id,),parameters=nscf_parameters,structure_reference="request_snapshot",artifact_inputs=("qe_charge_density","qe_save"),artifact_outputs=("ElectronicBandsData",),metadata={"purpose":"boltztrap2_transport","electronic_bands_data_contract":{"future_fields":["kpoint_coordinates","eigenvalues","fermi_or_reference_energy","cell","reciprocal_cell","electron_count_or_occupations","spin_information"],"populated_during_execution":True}})
    warning="2D conductivity-type quantities are vacuum-volume-normalized until an explicit effective thickness is supplied; no physical thickness is inferred." if is_2d and settings.effective_thickness is None else None
    api={"identity":"boltztrap2.isolated_runner","execution":"subprocess"}
    config={"quantum_studio_config_version":1,"stage":"interpolation","engine_id":"boltztrap2","input_artifact":"ElectronicBandsData","output_artifact":"BTP2_INTERPOLATED_BANDS","settings":settings.to_dict(),"future_api":api}
    interpolate=PlannedTask(id=f"{request.id}:btp2_interpolate",calculation_id="btp2_interpolate",semantic_task_type="btp2_interpolate",engine_id="boltztrap2",tool_id="boltztrap2.python_api",parameter_signature=_signature({"settings":settings.to_dict(),"stage":"interpolate"}),depends_on_task_ids=(nscf.id,),parameters={"btp2":settings},structure_reference="request_snapshot",artifact_inputs=("ElectronicBandsData",),artifact_outputs=("BTP2_INTERPOLATED_BANDS",),metadata={"configuration":config,"future_api":api,"normalization_warning":warning})
    result=[task for task in tasks if task.calculation_id not in INTENTS]+[nscf,interpolate]
    if not transport: return result
    outputs=_outputs(transport,settings.relaxation_time_model); config={"quantum_studio_config_version":1,"stage":"transport_integration","engine_id":"boltztrap2","input_artifact":"BTP2_INTERPOLATED_BANDS","output_artifacts":list(outputs),"observable_intents":list(transport),"settings":settings.to_dict(),"normalization_warning":warning,"future_api":api}
    task=PlannedTask(id=f"{request.id}:btp2_transport",calculation_id="btp2_transport",semantic_task_type="btp2_transport",engine_id="boltztrap2",tool_id="boltztrap2.python_api",parameter_signature=_signature({"settings":settings.to_dict(),"intents":transport,"stage":"transport"}),depends_on_task_ids=(interpolate.id,),parameters={"btp2":settings,"observable_intents":transport},structure_reference="request_snapshot",artifact_inputs=("BTP2_INTERPOLATED_BANDS",),artifact_outputs=outputs,metadata={"configuration":config,"future_api":api,"normalization_warning":warning})
    return result+[task]
