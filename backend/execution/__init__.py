"""C6 local execution contracts; no scientific engine behavior lives here."""
from .generated import GeneratedTask, GeneratedWorkflow
from .local import LocalExecutionManager
from .models import TaskExecutionRecord, TaskState, WorkflowExecutionRecord, WorkflowState
from .normalize import normalize_adapter_tasks
from .tools import LocalToolConfiguration, available_logical_cpus
from .discovery import QuantumEspressoInstallation, ToolDiscoveryResult, discover_quantum_espresso, discover_bader, discover_boltztrap2, validate_qe_installation
from .engine_family import EngineFamily, EngineFamilyError, require_coherent_e5_family, resolve_epw_family
__all__=["GeneratedTask","GeneratedWorkflow","LocalExecutionManager","LocalToolConfiguration","available_logical_cpus","TaskExecutionRecord","TaskState","WorkflowExecutionRecord","WorkflowState","QuantumEspressoInstallation","ToolDiscoveryResult","discover_quantum_espresso","discover_bader","discover_boltztrap2","validate_qe_installation"]

from .service import LocalExecutionService, LocalExecutionHandle

from .persistence import ExecutionStore, RecoveryAssessment, RecoveryState

from .artifacts import ArtifactError, ArtifactRegistry, ArtifactResolver, MaterializationPolicy, RequiredArtifactMissing, TaskArtifactDeclaration, TaskArtifactRequirement
from .recovery import FailureClass, RecoveryAction, DiskPreflight, IllegalTaskTransition, require_task_transition, classify_process_result, recovery_actions, disk_preflight, cleanup_disposable, recover_stale_running

from .providers import ComputeRuntime, ExecutionProvider, LocalLinuxRuntime, ManagedWSL2Runtime, RuntimeProbe, select_compute_runtime
from backend.runtime.wsl import WSLCommandRunner, WSLDiscovery, WSLHealthReport, probe_wsl_host
