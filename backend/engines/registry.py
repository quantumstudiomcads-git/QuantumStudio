"""Stable engine descriptors; discovery and execution remain outside C5E."""
from dataclasses import dataclass
from backend.core.execution_contract import ExecutionMode, GenerationSupport
@dataclass(frozen=True)
class EngineDescriptor:
    engine_id:str; display_name:str; generation_support:GenerationSupport; execution_mode:ExecutionMode; task_types:tuple[str,...]
ENGINES={
 "quantum_espresso":EngineDescriptor("quantum_espresso","Quantum ESPRESSO",GenerationSupport.CAN_GENERATE,ExecutionMode.SUBPROCESS,("scf","relax","vc_relax","qe_pw_nscf","qe_pw_nscf_btp2","qe_ph_epw","qe_pw2wannier90","qe_pw_bands","qe_bands","qe_dos","qe_projwfc","qe_pp","qe_ph","qe_q2r","qe_matdyn")),
 "wannier90":EngineDescriptor("wannier90","Wannier90",GenerationSupport.CAN_GENERATE,ExecutionMode.SUBPROCESS,("wannier90_preprocess","wannier90_run")),
 "epw":EngineDescriptor("epw","EPW",GenerationSupport.CAN_GENERATE,ExecutionMode.SUBPROCESS,("epw_run",)),
 "boltztrap2":EngineDescriptor("boltztrap2","BoltzTraP2",GenerationSupport.CAN_GENERATE,ExecutionMode.PYTHON_API,("btp2_interpolate","btp2_transport")),
 "negf":EngineDescriptor("negf","NEGF",GenerationSupport.CAN_GENERATE,ExecutionMode.NOT_SELECTED,("negf_electrode_left","negf_electrode_right","negf_self_energy_left","negf_self_energy_right","negf_device_green","negf_transmission")),
}
def engine_descriptor(engine_id): return ENGINES[engine_id]
def task_generation_support(task):
 descriptor=ENGINES.get(task.engine_id)
 return GenerationSupport.CAN_GENERATE if descriptor and task.semantic_task_type in descriptor.task_types else GenerationSupport.DEFERRED
