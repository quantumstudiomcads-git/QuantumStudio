"""Deterministic NEGF configuration export; no solver or external backend is selected."""
from __future__ import annotations
import json, os, tempfile
from dataclasses import dataclass
from pathlib import Path
from backend.engines.qe.adapter import _safe_identifier

class NEGFOutputExistsError(RuntimeError): pass
@dataclass(frozen=True)
class NEGFTaskConfiguration:
    task_id: str; semantic_task_type: str; working_directory: str; filename: str; configuration_text: str; dependencies: tuple[str, ...]; metadata: dict

class NEGFWorkflowAdapter:
    engine_id = "negf"
    def compile_plan(self, plan):
        if getattr(plan, "metadata", {}).get("engine_id") != self.engine_id: raise ValueError("NEGFWorkflowAdapter requires a C5D NEGFWorkflowPlan.")
        transport,settings=plan.transport_input.to_dict(),plan.settings.to_dict(); tasks=[]
        for index,task in enumerate(plan.tasks,1):
            payload={"quantum_studio_config_version":1,"engine_id":self.engine_id,"execution_backend":"not_selected","semantic_task_type":task.semantic_task_type,"transport_input":transport,"settings":settings,"task":{"task_id":task.id,"dependencies":list(task.depends_on_task_ids),"artifact_inputs":list(task.artifact_inputs),"artifact_outputs":list(task.artifact_outputs),"parameter_signature":task.parameter_signature,"metadata":dict(task.metadata)}}
            tasks.append(NEGFTaskConfiguration(task.id,task.semantic_task_type,f"{index:03d}_{_safe_identifier(task.semantic_task_type,'task')}","negf_config.json",json.dumps(payload,indent=2,sort_keys=True)+"\n",tuple(task.depends_on_task_ids),{"engine_id":task.engine_id,"tool_id":task.tool_id,"execution_backend":"not_selected","artifact_inputs":list(task.artifact_inputs),"artifact_outputs":list(task.artifact_outputs)}))
        manifest={"engine_id":self.engine_id,"execution_backend":"not_selected","transport_input_id":plan.transport_input.id,"tasks":[{"task_id":item.task_id,"semantic_task_type":item.semantic_task_type,"working_directory":item.working_directory,"generated_configuration_artifact":item.filename,"dependencies":list(item.dependencies),**item.metadata} for item in tasks]}
        return tuple(tasks),manifest
    def write_plan(self,plan,output_root,*,overwrite=False):
        if overwrite: raise NEGFOutputExistsError("C5D does not overwrite generated NEGF workflows.")
        tasks,manifest=self.compile_plan(plan); root=Path(output_root); root.mkdir(parents=True,exist_ok=True); destination=root/_safe_identifier(plan.transport_input.id,"transport")
        if destination.exists(): raise NEGFOutputExistsError(f"NEGF output already exists: {destination}")
        staging=Path(tempfile.mkdtemp(prefix=f".{destination.name}.staging-",dir=root))
        try:
            for task in tasks:
                directory=staging/task.working_directory; directory.mkdir(); (directory/task.filename).write_text(task.configuration_text,encoding="utf-8")
            (staging/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf-8"); os.replace(staging,destination)
        except Exception:
            for child in sorted(staging.rglob("*"),reverse=True): child.unlink() if child.is_file() else child.rmdir()
            if staging.exists(): staging.rmdir()
            raise
        return destination
