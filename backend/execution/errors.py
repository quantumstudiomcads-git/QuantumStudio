class ExecutionError(RuntimeError): pass
class ExecutionPreflightError(ExecutionError): pass
class ExecutableNotFoundError(ExecutionPreflightError): pass
class UnsupportedExecutionModeError(ExecutionPreflightError): pass
class ArtifactUnavailableError(ExecutionPreflightError): pass
class TaskExecutionError(ExecutionError): pass
class ExecutionCancelledError(TaskExecutionError): pass
