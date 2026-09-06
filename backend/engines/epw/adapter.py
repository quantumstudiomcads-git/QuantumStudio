from backend.engines.qe.adapter import QuantumEspressoAdapter,_safe_identifier
from backend.engines.qe.materialization import materialize_workflow_pseudopotentials
from backend.engines.qe.adapter import structure_fingerprint
import json, os, tempfile
from pathlib import Path
from backend.engines.qe.writer import pw_input,phonon_input
from backend.engines.wannier90.writer import win_input,pw2wannier90_input
from backend.engines.epw.writer import epw_input
from backend.engines.qe.models import QETaskInput
class EPWWorkflowAdapter:
 def __init__(self,pseudopotentials=None,*,pseudo_dir='../pseudos'): self.qe=QuantumEspressoAdapter(pseudopotentials,pseudo_dir=pseudo_dir)
 def compile_plan(self,plan):
  c,p=self.qe._context_for(plan),self.qe._pseudopotentials_for(plan.structure,plan); out=[]
  for i,t in enumerate(plan.tasks,1):
   d=f'{i:03d}_{_safe_identifier(t.semantic_task_type,"task")}'
   if t.semantic_task_type=='scf': x,f,e=pw_input('scf',t.parameters,plan.structure,c,p),'scf.in','pw.x'
   elif t.semantic_task_type=='qe_pw_nscf': x,f,e=pw_input('qe_pw_nscf',t.parameters,plan.structure,c,p),'nscf.in','pw.x'
   elif t.semantic_task_type=='qe_ph_epw': x,f,e=phonon_input(t.parameters,c),'ph_epw.in','ph.x'
   elif t.semantic_task_type in ('wannier90_preprocess','wannier90_run'): x,f,e=win_input(t.parameters['wannier'],plan.structure),t.parameters['seedname']+'.win','wannier90.x'
   elif t.semantic_task_type=='qe_pw2wannier90': x,f,e=pw2wannier90_input(c.prefix,c.outdir,t.parameters['seedname'],t.parameters.get('wannier')),'pw2wannier90.in','pw2wannier90.x'
   elif t.semantic_task_type=='epw_run': x,f,e=epw_input(t.parameters['epw'],c.prefix,c.outdir,next(a.parameters['seedname'] for a in plan.tasks if a.semantic_task_type=='wannier90_run'),dvscf_dir='../qe_out/_ph0/'),'epw.in','epw.x'
   else: raise ValueError(t.semantic_task_type)
   seed=t.parameters.get('seedname', '')
   declarations=[]; requirements=[]
   # The SCF save tree is a first-class logical artifact.  ph.x consumes it
   # through a child-owned copy-on-write workspace when a derived execution
   # reuses the electronic parent state.
   if t.semantic_task_type=='scf':
    declarations=[{'logical_name':'QE_SAVE','relative_path':'../qe_out/'+c.prefix+'.save','artifact_type':'QE_SAVE','materialization_policy':'COPY_ON_WRITE'}]
   if t.semantic_task_type=='qe_ph_epw':
    requirements=[{'logical_name':'QE_SAVE','relative_path':'../qe_out/'+c.prefix+'.save','artifact_type':'QE_SAVE','materialization_policy':'COPY_ON_WRITE'}]
    declarations=[{'logical_name':'EPW_PHONON_DATASET','relative_path':'../qe_out/_ph0','artifact_type':'PHONON_DVSCF_SET','materialization_policy':'REFERENCE'}]
   if t.semantic_task_type=='epw_run': requirements=[{'logical_name':'EPW_PHONON_DATASET','relative_path':'../qe_out/_ph0','artifact_type':'PHONON_DVSCF_SET','materialization_policy':'REFERENCE'}]
   if t.semantic_task_type=='wannier90_preprocess': declarations=[{'logical_name':'WANNIER_NNKP','relative_path':seed+'.nnkp','artifact_type':'WANNIER_NNKP','materialization_policy':'COPY'}]
   elif t.semantic_task_type=='qe_pw2wannier90':
    requirements=[{'logical_name':'WANNIER_NNKP','relative_path':seed+'.nnkp','artifact_type':'WANNIER_NNKP','materialization_policy':'COPY'}]
    declarations=[{'logical_name':'WANNIER_AMN','relative_path':seed+'.amn','artifact_type':'WANNIER_AMN','materialization_policy':'COPY'},{'logical_name':'WANNIER_MMN','relative_path':seed+'.mmn','artifact_type':'WANNIER_MMN','materialization_policy':'COPY'},{'logical_name':'WANNIER_EIG','relative_path':seed+'.eig','artifact_type':'WANNIER_EIG','materialization_policy':'COPY'}]
   elif t.semantic_task_type=='wannier90_run':
    requirements=[{'logical_name':name,'relative_path':seed+suffix,'artifact_type':name,'materialization_policy':'COPY'} for name,suffix in (('WANNIER_AMN','.amn'),('WANNIER_MMN','.mmn'),('WANNIER_EIG','.eig'))]
    declarations=[{'logical_name':'WANNIER_HR','relative_path':seed+'_hr.dat','artifact_type':'WANNIER_HR','required':False,'materialization_policy':'COPY'}]
   metadata={'engine_id':t.engine_id,'semantic_task_type':t.semantic_task_type,'artifact_inputs':list(t.artifact_inputs),'artifact_outputs':list(t.artifact_outputs),'artifact_declarations':declarations,'artifact_requirements':requirements,'qe_prefix':c.prefix,'qe_outdir':c.outdir,'qe_pseudo_dir':Path(os.path.relpath('pseudos',start=d)).as_posix(),'command':t.metadata.get('command')}
   out.append(QETaskInput(t.id,t.calculation_id,e,f,f.removesuffix('.in')+'.out',d,x,tuple(t.depends_on_task_ids),metadata))
  return tuple(out)

 def write_plan(self, plan, output_root, *, overwrite=False):
  if overwrite:
   raise ValueError("E5C product workflows are never overwritten; choose a new output root.")
  tasks = self.compile_plan(plan)
  root = Path(output_root)
  root.mkdir(parents=True, exist_ok=True)
  destination = root / _safe_identifier(plan.calculation_id, "request")
  if destination.exists():
   raise ValueError(f"Generated workflow already exists: {destination}")
  staging = Path(tempfile.mkdtemp(prefix=".e5c.staging-", dir=root))
  try:
   for task in tasks:
    directory = staging / task.working_directory
    directory.mkdir(parents=True)
    (directory / task.input_filename).write_text(task.input_text, encoding="utf-8")
   pseudo_provenance = self.qe._validate_pseudo_compatibility(plan, self.qe._pseudopotentials_for(plan.structure, plan))
   materials = materialize_workflow_pseudopotentials(staging, pseudo_provenance)
   manifest = {
    "engine_id": "multi_engine",
    "request_id": plan.calculation_id,
    "structure_fingerprint": structure_fingerprint(plan.structure),
    "pseudopotentials": pseudo_provenance,
    "tasks": [{"task_id": task.task_id, "calculation_id": task.calculation_id, "semantic_task_type": task.metadata["semantic_task_type"], "engine_id": task.metadata["engine_id"], "executable": task.executable, "input_filename": task.input_filename, "output_filename": task.output_filename, "working_directory": task.working_directory, "dependencies": list(task.depends_on_task_ids), "metadata": task.metadata} for task in tasks],
    "materialized_pseudopotentials": materials,
   }
   (staging / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + chr(10), encoding="utf-8")
   os.replace(staging, destination)
  except Exception:
   for child in sorted(staging.rglob("*"), reverse=True):
    if child.is_file() or child.is_symlink(): child.unlink()
    elif child.is_dir(): child.rmdir()
   if staging.exists(): staging.rmdir()
   raise
  return destination
