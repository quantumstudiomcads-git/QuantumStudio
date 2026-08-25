"""Qt-free C5E global architecture and artifact-DAG validation."""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass
from backend.calculations.semantics import SEMANTICS
from backend.engines.registry import ENGINES

ARTIFACT_ALIASES={"qe_save":"QE_SAVE_DIRECTORY","qe_wavefunctions":"QE_WAVEFUNCTIONS","qe_eigenvalues":"ELECTRONIC_EIGENVALUES","ElectronicBandsData":"ELECTRONIC_BANDS_DATA","qe_dynamical_matrix":"QE_DYNAMICAL_MATRIX","qe_dvscf":"QE_DVSCF","wannier_nnkp":"WANNIER_NNKP","wannier_amn":"WANNIER_AMN","wannier_mmn":"WANNIER_MMN","wannier_eig":"WANNIER_EIG","wannier_hr":"WANNIER_HAMILTONIAN","epw_electron_phonon_data":"EPW_COUPLING_DATA","epw_scattering_rates":"EPW_SCATTERING_RATE","LEFT_ELECTRODE_SELF_ENERGY":"ELECTRODE_SELF_ENERGY","RIGHT_ELECTRODE_SELF_ENERGY":"ELECTRODE_SELF_ENERGY"}
EXTERNAL_ARTIFACTS=frozenset({"WANNIER_HAMILTONIAN","wannier_hr","TRANSPORT_HAMILTONIAN","TRANSPORT_OVERLAP"})
@dataclass(frozen=True)
class ArchitectureReport:
 public_count:int; semantic_count:int; kind_counts:dict; support_counts:dict; errors:tuple[str,...]
 def diagnostic(self): return "Public calculations: %d\nClassified: %d\n%s\nInvalid semantic dependencies: %d"%(self.public_count,self.semantic_count,", ".join(f"{k}: {v}" for k,v in sorted(self.kind_counts.items())),len(self.errors))
TASK_FAMILY_ALIASES={"qe_pw_nscf_btp2":"qe_pw_nscf","qe_ph_epw":"qe_ph","negf_electrode_left":"negf_electrode","negf_electrode_right":"negf_electrode","negf_self_energy_left":"negf_self_energy","negf_self_energy_right":"negf_self_energy"}
def task_family(name): return TASK_FAMILY_ALIASES.get(name,name)
def canonical_artifact(name): return ARTIFACT_ALIASES.get(name,name)
def validate_task_artifacts(tasks):
 by_id={task.id:task for task in tasks}; errors=[]; producers={}
 for task in tasks:
  for artifact in task.artifact_outputs:
   producers.setdefault(canonical_artifact(artifact),[]).append(task.id)
 def ancestors(task_id):
  result=set(); stack=list(by_id[task_id].depends_on_task_ids)
  while stack:
   current=stack.pop()
   if current in result: continue
   result.add(current); stack.extend(by_id[current].depends_on_task_ids if current in by_id else ())
  return result
 for task in tasks:
  if task.engine_id not in ENGINES: errors.append(f"Unknown engine: {task.engine_id}")
  for artifact in task.artifact_inputs:
   key=canonical_artifact(artifact); candidates=producers.get(key,[])
   if key in EXTERNAL_ARTIFACTS: continue
   if not candidates: errors.append(f"{task.id} consumes unproduced artifact {artifact}")
   elif not set(candidates)&ancestors(task.id): errors.append(f"{task.id} consumes {artifact} without producer dependency")
  if set(task.artifact_inputs)&set(task.artifact_outputs): errors.append(f"{task.id} consumes its own output")
 return tuple(errors)
def validate_calculation_architecture(catalog=None):
 from frontend.calculations.catalog import CALCULATIONS
 entries=tuple(CALCULATIONS if catalog is None else catalog); ids=[item.id for item in entries]; errors=[]
 if len(ids)!=147: errors.append(f"Expected 147 public calculations, found {len(ids)}")
 if len(ids)!=len(set(ids)): errors.append("Duplicate public calculation IDs")
 if set(ids)!=set(SEMANTICS): errors.append("Catalog IDs and semantic map IDs differ")
 for item in entries:
  descriptor=SEMANTICS.get(item.id)
  if descriptor is None: continue
  for prerequisite in descriptor.prerequisites:
   if prerequisite not in SEMANTICS: errors.append(f"{item.id} requires unknown {prerequisite}")
  if prerequisite_cycle(item.id): errors.append(f"Semantic dependency cycle at {item.id}")
 kinds=Counter(value.kind.value for value in SEMANTICS.values()); supports=Counter(item.status for item in entries)
 return ArchitectureReport(len(entries),len(SEMANTICS),dict(kinds),dict(supports),tuple(errors))
def prerequisite_cycle(root):
 seen=set(); active=set()
 def visit(node):
  if node in active:return True
  if node in seen:return False
  seen.add(node); active.add(node); value=any(visit(child) for child in SEMANTICS[node].prerequisites); active.remove(node); return value
 return visit(root)
