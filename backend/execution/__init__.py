"""C6 local execution contracts; no scientific engine behavior lives here."""
from .generated import GeneratedTask, GeneratedWorkflow
from .local import LocalExecutionManager
from .models import TaskState, WorkflowState
from .normalize import normalize_adapter_tasks
from .tools import LocalToolConfiguration, available_logical_cpus
from .discovery import QuantumEspressoInstallation, ToolDiscoveryResult, discover_quantum_espresso, discover_bader, validate_qe_installation
__all__=["GeneratedTask","GeneratedWorkflow","LocalExecutionManager","LocalToolConfiguration","available_logical_cpus","TaskState","WorkflowState","QuantumEspressoInstallation","ToolDiscoveryResult","discover_quantum_espresso","discover_bader","validate_qe_installation"]

from .service import LocalExecutionService, LocalExecutionHandle

from .persistence import ExecutionStore, RecoveryAssessment, RecoveryState
