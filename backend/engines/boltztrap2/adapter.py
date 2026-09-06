"""Cross-engine BoltzTraP2 adapter producing shell-free executable tasks."""
from __future__ import annotations
import json, os, tempfile
from pathlib import Path
from backend.engines.qe.adapter import QuantumEspressoAdapter, _safe_identifier, structure_fingerprint
from backend.engines.qe.models import QEInputGenerationError, QEOutputExistsError, QETaskInput
from backend.engines.qe.materialization import materialize_workflow_pseudopotentials
from backend.engines.qe.writer import pw_input

class BoltzTraP2WorkflowAdapter:
    engine_id = "boltztrap2"
    def __init__(self, pseudopotentials=None, *, pseudo_dir="../pseudos"): self.qe = QuantumEspressoAdapter(pseudopotentials, pseudo_dir=pseudo_dir)
    def compile_plan(self, plan):
        intents={"boltztrap_bands","electrical_conductivity","seebeck","thermal_conductivity_electronic","power_factor","carrier_concentration"}
        if not set(plan.selected_calculations) & intents: raise QEInputGenerationError("BoltzTraP2WorkflowAdapter requires a C5C BoltzTraP2 request.")
        context,pseudos=self.qe._context_for(plan),self.qe._pseudopotentials_for(plan.structure,plan); pseudo_provenance=self.qe._validate_pseudo_compatibility(plan,pseudos); generated=[]
        for index,task in enumerate(plan.tasks,1):
            command=None
            directory=f"{index:03d}_{_safe_identifier(task.semantic_task_type or task.calculation_id, 'task')}"
            if task.semantic_task_type=="scf": text,filename,tool=pw_input("scf",task.parameters,plan.structure,context,pseudos),"scf.in","pw.x"
            elif task.semantic_task_type=="qe_pw_nscf_btp2": text,filename,tool=pw_input("qe_pw_nscf",task.parameters,plan.structure,context,pseudos),"nscf_btp2.in","pw.x"
            elif task.semantic_task_type in {"btp2_interpolate","btp2_transport"}:
                text=json.dumps(task.metadata["configuration"],indent=2,sort_keys=True)+"\n"; filename="btp2_config.json" if task.semantic_task_type=="btp2_interpolate" else "btp2_transport.json"; tool="btp2-python"; runner=str(Path(__file__).with_name("runner.py").resolve()); command=["btp2-python",runner,"interpolate","../qe_out","interpolation.bt2"] if task.semantic_task_type=="btp2_interpolate" else ["btp2-python",runner,"integrate",f"../{index-1:03d}_btp2_interpolate/interpolation.bt2","transport.json",f"../{index-1:03d}_btp2_interpolate/btp2_config.json"]
            else: raise QEInputGenerationError(f"Unsupported task in BoltzTraP2 plan: {task.semantic_task_type}.")
            generated.append(QETaskInput(task.id,task.calculation_id,tool,filename,filename+".out",directory,text,tuple(task.depends_on_task_ids),{"engine_id":task.engine_id,"semantic_task_type":task.semantic_task_type,"parameter_signature":task.parameter_signature,"artifact_inputs":list(task.artifact_inputs),"artifact_outputs":list(task.artifact_outputs),"future_api":task.metadata.get("future_api"),"generated_configuration_artifact":filename,"qe_prefix":context.prefix,"qe_outdir":context.outdir,"command":command}))
        manifest={"engine_id":"multi_engine","request_id":plan.calculation_id,"structure_fingerprint":structure_fingerprint(plan.structure),"pseudopotentials":pseudo_provenance,"workflow_context":{"prefix":context.prefix,"outdir":context.outdir,"pseudo_dir":context.pseudo_dir},"tasks":[{"task_id":item.task_id,"calculation_id":item.calculation_id,"semantic_task_type":item.metadata["semantic_task_type"],"engine_id":item.metadata["engine_id"],"tool_id":item.executable,"dependencies":list(item.depends_on_task_ids),"parameter_signature":item.metadata["parameter_signature"],"artifact_inputs":item.metadata["artifact_inputs"],"artifact_outputs":item.metadata["artifact_outputs"],"generated_configuration_artifact":item.metadata["generated_configuration_artifact"],"future_api":item.metadata["future_api"],"input_filename":item.input_filename,"working_directory":item.working_directory} for item in generated]}
        return tuple(generated),manifest
    def write_plan(self,plan,output_root,*,overwrite=False):
        if overwrite: raise QEOutputExistsError("C5C does not overwrite existing generated workflows.")
        tasks,manifest=self.compile_plan(plan); root=Path(output_root); root.mkdir(parents=True,exist_ok=True); destination=root/_safe_identifier(plan.calculation_id,"request")
        if destination.exists(): raise QEOutputExistsError(f"Workflow output already exists: {destination}")
        staging=Path(tempfile.mkdtemp(prefix=f".{destination.name}.staging-",dir=root))
        try:
            for task in tasks:
                task_dir=staging/task.working_directory; task_dir.mkdir(); (task_dir/task.input_filename).write_text(task.input_text,encoding="utf-8")
            pseudo_entries=manifest.get("pseudopotentials", {}); has_source_provenance=any(isinstance(entry, dict) and entry.get("source") for entry in pseudo_entries.values()); materials=materialize_workflow_pseudopotentials(staging, pseudo_entries) if has_source_provenance else {}; manifest["materialized_pseudopotentials"]=materials; (staging/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf-8"); os.replace(staging,destination)
        except Exception:
            for child in sorted(staging.rglob("*"),reverse=True): child.unlink() if child.is_file() else child.rmdir()
            if staging.exists(): staging.rmdir()
            raise
        return destination
