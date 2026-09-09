"""Small, Qt-free contracts for failure and recovery handling (B2)."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path
import shutil

from .models import TaskState, now


class FailureClass(str, Enum):
    RETRYABLE_TRANSIENT = "RETRYABLE_TRANSIENT"
    NONRETRYABLE_INPUT = "NONRETRYABLE_INPUT"
    NONRETRYABLE_RESOURCE = "NONRETRYABLE_RESOURCE"
    NONRETRYABLE_SCIENTIFIC = "NONRETRYABLE_SCIENTIFIC"
    USER_CANCELLED = "USER_CANCELLED"
    PARSER_FAILURE = "PARSER_FAILURE"
    REQUIRED_ARTIFACT_MISSING = "REQUIRED_ARTIFACT_MISSING"
    PREPARATION_FAILURE = "PREPARATION_FAILURE"
    PROCESS_KILLED = "PROCESS_KILLED"


class RecoveryAction(str, Enum):
    RETRY = "RETRY"
    REPARSE = "REPARSE"
    EDIT_CONFIGURATION = "EDIT_CONFIGURATION"
    CHANGE_RESOURCES = "CHANGE_RESOURCES"
    CONFIGURE_ENGINE = "CONFIGURE_ENGINE"
    ACQUIRE_PSEUDO = "ACQUIRE_PSEUDO"
    RUN_AGAIN = "RUN_AGAIN"


LEGAL_TASK_TRANSITIONS = {
    TaskState.PENDING: {TaskState.READY, TaskState.CANCELLED, TaskState.BLOCKED},
    TaskState.READY: {TaskState.RUNNING, TaskState.CANCELLED, TaskState.BLOCKED},
    TaskState.RUNNING: {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED, TaskState.INTERRUPTED},
    TaskState.FAILED: set(),
    TaskState.CANCELLED: set(),
    TaskState.BLOCKED: set(),
    TaskState.INTERRUPTED: set(),
    TaskState.COMPLETED: set(),
}


class IllegalTaskTransition(RuntimeError):
    pass


def require_task_transition(current: TaskState, target: TaskState, *, new_attempt: bool = False) -> None:
    """Reject mutation of historical terminal truth; retries are new attempts."""
    current, target = TaskState(current), TaskState(target)
    if current == target:
        return
    if current in {TaskState.FAILED, TaskState.CANCELLED, TaskState.INTERRUPTED} and target in {TaskState.READY, TaskState.RUNNING} and new_attempt:
        return
    if target not in LEGAL_TASK_TRANSITIONS[current]:
        raise IllegalTaskTransition(f"Illegal task transition {current.value} -> {target.value}.")


def classify_process_result(return_code: int | None, *, cancelled: bool = False, timeout: bool = False, oom_evidence: bool = False) -> FailureClass | None:
    if cancelled:
        return FailureClass.USER_CANCELLED
    if timeout:
        return FailureClass.RETRYABLE_TRANSIENT
    if return_code in (None, 0):
        return None
    if oom_evidence:
        return FailureClass.NONRETRYABLE_RESOURCE
    if return_code < 0:
        return FailureClass.PROCESS_KILLED
    return FailureClass.RETRYABLE_TRANSIENT


def recovery_actions(failure: FailureClass) -> tuple[RecoveryAction, ...]:
    return {
        FailureClass.PARSER_FAILURE: (RecoveryAction.REPARSE,),
        FailureClass.REQUIRED_ARTIFACT_MISSING: (RecoveryAction.RETRY,),
        FailureClass.PREPARATION_FAILURE: (RecoveryAction.EDIT_CONFIGURATION,),
        FailureClass.NONRETRYABLE_INPUT: (RecoveryAction.EDIT_CONFIGURATION,),
        FailureClass.NONRETRYABLE_RESOURCE: (RecoveryAction.CHANGE_RESOURCES,),
        FailureClass.USER_CANCELLED: (RecoveryAction.RUN_AGAIN,),
        FailureClass.PROCESS_KILLED: (RecoveryAction.RETRY, RecoveryAction.CHANGE_RESOURCES),
    }.get(failure, (RecoveryAction.RETRY,))


@dataclass(frozen=True)
class DiskPreflight:
    required_bytes: int
    available_bytes: int
    adequate: bool
    reason: str = ""


def disk_preflight(path: str | os.PathLike[str], required_bytes: int, *, usage=shutil.disk_usage) -> DiskPreflight:
    available = int(usage(path).free)
    required = max(0, int(required_bytes))
    return DiskPreflight(required, available, available >= required, "" if available >= required else "INSUFFICIENT_DISK_SPACE")


def cleanup_disposable(root: str | os.PathLike[str], target: str | os.PathLike[str]) -> None:
    """Delete only a disposable child under an owned root; never follow symlinks."""
    root_path = Path(root).resolve()
    target_path = Path(target)
    lexical = target_path.absolute()
    if lexical == root_path or root_path not in lexical.parents:
        raise ValueError("Cleanup target is outside the owned workflow root.")
    # NTFS directory junctions are reparse points just like symlinks for the
    # purpose of safe cleanup.  Never let rmtree traverse either one.
    is_link = target_path.is_symlink() or (hasattr(target_path, "is_junction") and target_path.is_junction())
    if is_link:
        target_path.unlink()
    elif target_path.is_dir():
        shutil.rmtree(target_path)
    elif target_path.exists():
        target_path.unlink()


def recover_stale_running(record, *, live_process=lambda _pid: False) -> bool:
    """Mark unowned RUNNING tasks interrupted without attaching to a PID."""
    changed = False
    for task in record.tasks.values():
        if task.state is TaskState.RUNNING and not live_process(task.process_id):
            task.state = TaskState.INTERRUPTED
            task.finished_at = now()
            task.error_type = "INTERRUPTED"
            task.error_message = "Prior runtime ownership was lost; process identity was not proven."
            changed = True
    return changed
