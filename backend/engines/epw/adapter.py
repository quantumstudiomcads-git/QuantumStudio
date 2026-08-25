from backend.engines.qe.adapter import QuantumEspressoAdapter,_safe_identifier
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
   elif t.semantic_task_type=='qe_pw2wannier90': x,f,e=pw2wannier90_input(c.prefix,c.outdir,t.parameters['seedname']),'pw2wannier90.in','pw2wannier90.x'
   elif t.semantic_task_type=='epw_run': x,f,e=epw_input(t.parameters['epw'],c.prefix,c.outdir,next(a.parameters['seedname'] for a in plan.tasks if a.semantic_task_type=='wannier90_run')),'epw.in','epw.x'
   else: raise ValueError(t.semantic_task_type)
   out.append(QETaskInput(t.id,t.calculation_id,e,f,f+'.out',d,x,tuple(t.depends_on_task_ids),{'engine_id':t.engine_id,'artifact_inputs':list(t.artifact_inputs),'artifact_outputs':list(t.artifact_outputs)}))
  return tuple(out)
