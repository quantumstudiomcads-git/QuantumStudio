"""C6 local execution contracts; no scientific engine behavior lives here."""
from .generated import GeneratedTask, GeneratedWorkflow
from .local import LocalExecutionManager
from .models import TaskState, WorkflowState
from .normalize import normalize_adapter_tasks
from .tools import LocalToolConfiguration
__all__=["GeneratedTask","GeneratedWorkflow","LocalExecutionManager","LocalToolConfiguration","TaskState","WorkflowState"]

from .service import LocalExecutionService, LocalExecutionHandle

from .persistence import ExecutionStore, RecoveryAssessment, RecoveryState
