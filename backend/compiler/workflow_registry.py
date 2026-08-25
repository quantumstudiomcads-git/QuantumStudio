"""C5E workflow-builder registry: planning families are separate from C6 execution."""
from dataclasses import dataclass
@dataclass(frozen=True)
class WorkflowBuilderDescriptor: workflow_family:str; builder_name:str; generation_ready:bool
WORKFLOW_BUILDERS={name:WorkflowBuilderDescriptor(name,builder,True) for name,builder in {"wannier":"CalculationCompiler._expand_wannierization","electron_phonon":"CalculationCompiler._expand_electron_phonon","boltzmann_transport":"compiler.boltztrap2.expand_boltztrap2","negf_transport":"compiler.negf.compile_transport_workflow"}.items()}
