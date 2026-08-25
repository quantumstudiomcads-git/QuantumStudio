"""Common C5E generated-workflow manifest contract for C6-facing validation."""
from __future__ import annotations
from backend.core.execution_contract import ExecutionReadiness, GenerationSupport

REQUIRED_TASK_FIELDS=frozenset({"task_id","semantic_task_type","engine_id","tool_id","dependencies","artifact_inputs","artifact_outputs","working_directory"})
def manifest_task_contract(task, *, working_directory, input_file, execution_readiness=ExecutionReadiness.GENERATION_READY):
    return {"task_id":task.id,"semantic_task_type":task.semantic_task_type,"engine_id":task.engine_id,"tool_id":task.tool_id,"dependencies":list(task.depends_on_task_ids),"parameter_signature":task.parameter_signature,"artifact_inputs":list(task.artifact_inputs),"artifact_outputs":list(task.artifact_outputs),"working_directory":working_directory,"input_or_config_file":input_file,"generation_support":GenerationSupport.CAN_GENERATE.value,"execution_readiness":execution_readiness.value}
def execution_readiness_for_task(task):
 if task.engine_id == "negf": return ExecutionReadiness.EXECUTION_BACKEND_MISSING
 if any(item in {"WANNIER_HAMILTONIAN","wannier_hr","TRANSPORT_HAMILTONIAN","TRANSPORT_OVERLAP"} for item in task.artifact_inputs): return ExecutionReadiness.EXTERNAL_ARTIFACT_REQUIRED
 return ExecutionReadiness.GENERATION_READY
def manifest_contract_errors(manifest):
    errors=[]
    for task in manifest.get("tasks",()):
        missing=REQUIRED_TASK_FIELDS-set(task)
        if missing: errors.append("Manifest task missing " + ", ".join(sorted(missing)))
    return tuple(errors)
