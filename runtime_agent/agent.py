"""Deployable stdlib-only qs-runtime-agent implementation.

The agent is deliberately a constrained runtime endpoint, not a shell.  W5
extends W4 with named file-transfer and task-control operations only.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import subprocess
import sys
import time
import threading
import contextlib
from datetime import datetime, timezone
import uuid
from typing import BinaryIO, Iterable, Mapping

from .protocol import (AGENT_VERSION, AgentStatus, ProtocolError, RuntimeAgentHealth,
                       RuntimePath, RuntimeProcessRequest, RuntimeProcessResult,
                       is_valid_posix_process_identity,
                       is_valid_windows_process_identity, timestamp)

DEFAULT_EXECUTABLE_ROOTS = ("/opt/quantumstudio/engines", "/opt/quantumstudio/runtime/bin")
DEFAULT_WORKING_ROOTS = ("/var/lib/quantumstudio/workflows", "/var/lib/quantumstudio/staging")
DEFAULT_TRANSFER_ROOTS = DEFAULT_WORKING_ROOTS + ("/var/lib/quantumstudio/pseudopotentials", "/opt/quantumstudio/engines/.staging")
DEFAULT_TASK_CONTROL_ROOT = "/var/lib/quantumstudio/runtime/tasks"
CAPABILITIES = ("run", "status", "cancel", "stage_in", "stage_out", "install_engine_pack")
_TASK_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_UTC_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)\Z")
_CANCELLATION_EVIDENCE_VERSION = 2


def _under(path: RuntimePath, roots: Iterable[str]) -> bool:
    candidate = PurePosixPath(str(path))
    return any(candidate == (trusted := PurePosixPath(str(RuntimePath(root)))) or trusted in candidate.parents for root in roots)


def _host_path(value: str | RuntimePath) -> Path:
    """Map the POSIX wire path to a host path for source-mode Windows tests.

    Managed Linux execution keeps the wire path unchanged.  The explicit
    ``/C:/...`` form is only used when this stdlib agent is exercised directly
    on Windows; it preserves the drive instead of letting ``Path`` interpret
    the path as a root on the current drive.
    """
    text = str(value)
    if os.name == "nt" and re.match(r"^/[A-Za-z]:/", text):
        return Path(text[1:].replace("/", "\\"))
    if os.name == "nt" and text.startswith("/"):
        # Source-mode fixtures may omit a host drive when converting a path to
        # the POSIX wire namespace. Resolve against the drive containing the
        # path (without changing the managed Linux wire contract).
        suffix = text.replace("/", "\\")
        current_drive = Path.cwd().drive or os.environ.get("SystemDrive", "C:")
        drives = [current_drive] + [os.environ.get("SystemDrive", "C:")] + [f"{letter}:" for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if f"{letter}:" not in {current_drive, os.environ.get("SystemDrive", "C:")}]
        candidates = [Path(drive + suffix) for drive in drives]
        def score(candidate: Path) -> int:
            score = 0
            item = candidate
            while item != item.parent and item.exists():
                score += 1
                item = item.parent
            return score
        return max(candidates, key=score)
    return Path(text)


def _host_argument(value: str) -> str:
    """Resolve namespaced fixture paths in argv when running on Windows."""
    if os.name == "nt" and value.startswith("/"):
        return str(_host_path(value))
    return value


def _real_under(path: Path, roots: Iterable[str]) -> bool:
    candidate = path.resolve(strict=False)
    for root in roots:
        trusted = _host_path(root).resolve(strict=False)
        if candidate == trusted or trusted in candidate.parents:
            return True
    return False


def _safe_task_id(task_id: str) -> str:
    if not isinstance(task_id, str) or not _TASK_ID.fullmatch(task_id):
        raise ProtocolError("INVALID_REQUEST", "task_id is invalid.")
    return task_id


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.{threading.get_ident()}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, sort_keys=True, separators=(",", ":"))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


@contextlib.contextmanager
def _task_record_lock(task_id: str, root: str, *, timeout: float = 15.0):
    """Bounded cross-process lock for task state transitions."""
    path = _control_path(task_id, root).with_suffix(".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = path.open("a+b")
    acquired = False
    deadline = time.monotonic() + timeout
    try:
        if os.name == "nt":
            import msvcrt
            if path.stat().st_size == 0:
                stream.write(b"0"); stream.flush()
            while True:
                stream.seek(0)
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    acquired = True
                    break
                except OSError as error:
                    if error.errno not in (11, 13, 36) and getattr(error, "winerror", None) not in (33, 36):
                        raise
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Managed task record lock timed out.") from error
                    time.sleep(0.02)
        else:
            import fcntl
            while True:
                try:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except BlockingIOError as error:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Managed task record lock timed out.") from error
                    time.sleep(0.02)
        yield
    finally:
        if acquired:
            if os.name == "nt":
                import msvcrt
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        stream.close()


def _control_path(task_id: str, root: str) -> Path:
    return Path(root) / (_safe_task_id(task_id) + ".json")


def _read_control(task_id: str, root: str) -> dict[str, object] | None:
    path = _control_path(task_id, root)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError):
        raise ProtocolError("INVALID_REQUEST", "Managed task control record is malformed.")
    if not isinstance(value, dict) or value.get("task_id") != task_id:
        raise ProtocolError("INVALID_REQUEST", "Managed task control record has invalid identity.")
    return value


def _proc_start_ticks(pid: int) -> str:
    try:
        fields = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split()
        return fields[21] if len(fields) > 21 else ""
    except OSError:
        return ""


def _record_alive(record: Mapping[str, object]) -> bool:
    if str(record.get("state", "")) not in {"RUNNING", "CANCELLING"}:
        return False
    try:
        expected = str(record.get("process_start_ticks", ""))
    except (KeyError, TypeError, ValueError):
        return False
    if os.name == "nt":
        pid, pgid = record.get("pid"), record.get("pgid")
        if (not is_valid_windows_process_identity(pid)
                or not is_valid_windows_process_identity(pgid)):
            return False
        name = str(record.get("job_name", ""))
        token = str(record.get("ownership_token", ""))
        if (record.get("boundary_type") != "windows_job_object+process_group"
                or not re.fullmatch(r"Local\\QSRuntime-([0-9a-f]{32})", name)
                or not token or name.rsplit("-", 1)[-1] != token):
            return False
        try:
            from .windows_job import WindowsJob
            with WindowsJob(name, create=False) as job:
                creation = int(str(record.get("process_creation_time", "")))
                active = job.active_processes() > 0
                if not active:
                    return False
                # The named, token-bound Job Object remains authoritative if
                # a launcher exited while one of its inherited members lives.
                return True
        except (OSError, ValueError, RuntimeError):
            return False
    pid, pgid = record.get("pid"), record.get("pgid")
    if (not is_valid_posix_process_identity(pid)
            or not is_valid_posix_process_identity(pgid)):
        return False
    if not expected or _proc_start_ticks(pid) != expected:
        return False
    try:
        if pgid <= 1 or pgid == os.getpgrp() or os.getpgid(pid) != pgid:
            return False
        os.killpg(pgid, 0)
    except (ProcessLookupError, PermissionError, OSError):
        return False
    return True


def _posix_record_process_ids_valid(record: Mapping[str, object]) -> bool:
    return (is_valid_posix_process_identity(record.get("pid"))
            and is_valid_posix_process_identity(record.get("pgid")))


def _signal_group(pgid: int, sig: signal.Signals) -> None:
    """Signal a verified POSIX task group; Windows uses Job Objects."""
    if os.name == "nt":
        raise RuntimeError("Windows cancellation must use the recorded Job Object.")
    if (not is_valid_posix_process_identity(pgid)
            or pgid <= 1 or pgid == os.getpgrp()):
        raise ValueError("Refusing to signal an unowned or current process group.")
    os.killpg(pgid, sig)


def _result(request: RuntimeProcessRequest | None, status: AgentStatus, diagnostic: str, **values) -> RuntimeProcessResult:
    return RuntimeProcessResult(request.task_id if request else "", status, **values, diagnostic=diagnostic)


def _indeterminate_launch_result(request: RuntimeProcessRequest, *, task_control_root: str,
                                 started_at: str, timer: float, failure_code: str) -> RuntimeProcessResult:
    """Persist a redacted terminal result without using an unproven process ID."""
    finished_at = timestamp()
    record = {"schema_version": 1, "task_id": request.task_id,
              "state": "OUTCOME_INDETERMINATE", "failure_code": failure_code,
              "started_at": started_at, "finished_at": finished_at}
    try:
        with _task_record_lock(request.task_id, task_control_root):
            existing = _read_control(request.task_id, task_control_root)
            if existing is not None:
                raise ProtocolError("TASK_CONTROL_PERSISTENCE_FAILED",
                                    "An authoritative task record already exists.")
            path = _control_path(request.task_id, task_control_root)
            _atomic_json(path, record)
            committed = _read_control(request.task_id, task_control_root)
            if committed != record:
                raise ProtocolError("TASK_CONTROL_PERSISTENCE_FAILED",
                                    "The indeterminate launch result could not be verified after writing.")
    except ProtocolError as error:
        return _result(request, AgentStatus.TASK_CONTROL_PERSISTENCE_FAILED,
                       "task_control_persistence_failed", started=True, finished=False,
                       return_code=None, started_at=started_at, finished_at="",
                       duration_seconds=time.monotonic() - timer)
    except (OSError, TypeError, ValueError, OverflowError) as error:
        return _result(request, AgentStatus.TASK_CONTROL_PERSISTENCE_FAILED,
                       "task_control_persistence_failed", started=True, finished=False,
                       return_code=None, started_at=started_at, finished_at="",
                       duration_seconds=time.monotonic() - timer)
    return _result(request, AgentStatus.TASK_OUTCOME_INDETERMINATE,
                   "Process identity could not be proven; operator review is required.",
                   started=True, finished=True, return_code=None,
                   started_at=started_at, finished_at=finished_at,
                   duration_seconds=time.monotonic() - timer)


def _process_boundary_identity(record: Mapping[str, object]) -> tuple[str, str] | None:
    """Canonical, restart-stable identity of the owned process boundary."""
    kind = record.get("boundary_type")
    if kind == "windows_job_object+process_group":
        ownership, name = record.get("ownership_token"), record.get("job_name")
        if (not isinstance(ownership, str) or not re.fullmatch(r"[0-9a-f]{32}", ownership)
                or not isinstance(name, str) or name != "Local\\QSRuntime-" + ownership
                or not is_valid_windows_process_identity(record.get("pid"))):
            return None
        return kind, name
    if kind == "posix_session":
        if not _posix_record_process_ids_valid(record):
            return None
        return kind, str(record["pgid"])
    return None


def _cancellation_action_evidence(record: Mapping[str, object], *, ownership: str,
                                  request_id: str, pid: int,
                                  creation_time: int) -> str | None:
    """Return a verified action only when its evidence binds to this task process."""
    attempts = record.get("cancellation_action_attempts", [])
    receipts = record.get("cancellation_action_receipts", [])
    if not isinstance(attempts, list) or not isinstance(receipts, list):
        return None
    if isinstance(record.get("cancellation_action_intent"), dict):
        current_intent = record["cancellation_action_intent"]
        if current_intent.get("state") in {"prepared", "confirmed"}:
            attempts = [current_intent]
        else:
            attempts = [*attempts, current_intent]
    if isinstance(record.get("cancellation_action_evidence"), dict):
        receipts = [*receipts, record["cancellation_action_evidence"]]
    if (not re.fullmatch(r"[0-9a-f]{32}", request_id)
            or record.get("cancel_requested") is not True
            or record.get("cancel_token") != request_id):
        return None
    if (not isinstance(ownership, str) or not re.fullmatch(r"[0-9a-f]{32}", ownership)
            or record.get("ownership_token") != ownership
            or type(record.get("pid")) is not int or record.get("pid") != pid
            or record.get("process_creation_time") != str(creation_time)):
        return None
    boundary = _process_boundary_identity(record)
    if boundary is None:
        return None
    for evidence in reversed(receipts):
        if not isinstance(evidence, dict):
            continue
        action = evidence.get("action")
        if not isinstance(action, str) or action not in {"graceful", "terminated", "forced"}:
            continue
        for intent in reversed(attempts):
            if not isinstance(intent, dict) or intent.get("state") != "confirmed":
                continue
            prepared_at = _parse_utc_timestamp(intent.get("prepared_at"))
            action_at = _parse_utc_timestamp(evidence.get("action_at"))
            if (type(evidence.get("version")) is int and evidence.get("version") == _CANCELLATION_EVIDENCE_VERSION
                    and type(intent.get("version")) is int and intent.get("version") == _CANCELLATION_EVIDENCE_VERSION
                    and isinstance(record.get("task_id"), str) and record.get("task_id")
                    and evidence.get("task_id") == record.get("task_id") == intent.get("task_id")
                    and evidence.get("request_id") == intent.get("request_id") == request_id
                    and evidence.get("attempt_id") == intent.get("attempt_id")
                    and isinstance(intent.get("attempt_id"), str)
                    and re.fullmatch(r"[0-9a-f]{32}", intent["attempt_id"])
                    and evidence.get("ownership_token") == intent.get("ownership_token") == ownership
                    and type(evidence.get("pid")) is int and type(intent.get("pid")) is int
                    and evidence.get("pid") == intent.get("pid") == pid
                    and evidence.get("process_creation_time") == intent.get("process_creation_time") == str(creation_time)
                    and evidence.get("boundary_type") == intent.get("boundary_type") == boundary[0]
                    and evidence.get("boundary_id") == intent.get("boundary_id") == boundary[1]
                    and evidence.get("action") == intent.get("action")
                    and prepared_at is not None and action_at is not None and action_at >= prepared_at):
                return action
    return None


def _parse_utc_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or len(value) > 32 or not _UTC_TIMESTAMP.fullmatch(value):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        return None
    return parsed


def _valid_utc_timestamp(value: object) -> bool:
    return _parse_utc_timestamp(value) is not None


def _prepare_cancellation_action(record: Mapping[str, object], *, action: str,
                                 ownership: str, request_id: str, pid: int,
                                 creation_time: int) -> dict[str, object]:
    updated = dict(record)
    boundary = _process_boundary_identity(updated)
    if (boundary is None or updated.get("ownership_token") != ownership
            or type(updated.get("pid")) is not int or updated.get("pid") != pid
            or updated.get("process_creation_time") != str(creation_time)):
        raise ValueError("Managed process boundary identity could not be verified.")
    intent = {
        "version": _CANCELLATION_EVIDENCE_VERSION, "state": "prepared", "task_id": updated.get("task_id"),
        "request_id": request_id, "attempt_id": uuid.uuid4().hex,
        "ownership_token": ownership, "pid": pid,
        "process_creation_time": str(creation_time), "action": action,
        "boundary_type": boundary[0], "boundary_id": boundary[1],
        "prepared_at": timestamp(),
    }
    updated["cancellation_action_intent"] = intent
    updated["cancellation_action_attempts"] = [
        *[item for item in updated.get("cancellation_action_attempts", []) if isinstance(item, dict)], intent]
    return updated


def _finish_cancellation_intent(record: Mapping[str, object], *, state: str) -> dict[str, object]:
    updated = dict(record)
    intent = updated.get("cancellation_action_intent")
    if isinstance(intent, dict):
        intent = dict(intent); intent["state"] = state
        updated["cancellation_action_intent"] = intent
        attempts = updated.get("cancellation_action_attempts", [])
        if isinstance(attempts, list):
            updated["cancellation_action_attempts"] = [
                intent if isinstance(item, dict) and item.get("attempt_id") == intent.get("attempt_id") else item
                for item in attempts]
    return updated


def _persist_cancellation_action_receipt(path: Path, payload: Mapping[str, object]) -> None:
    """Retry only bounded Windows sharing violations; never resend the action."""
    for attempt in range(3):
        try:
            _atomic_json(path, payload)
            return
        except OSError as error:
            sharing_violation = getattr(error, "winerror", None) in {32, 33}
            if not sharing_violation or attempt == 2:
                raise
            time.sleep(0.02)


def _with_cancellation_action(record: Mapping[str, object], *, action: str,
                              ownership: str, request_id: str, pid: int,
                              creation_time: int) -> dict[str, object]:
    updated = dict(record)
    intent = updated.get("cancellation_action_intent")
    if not isinstance(intent, dict) or intent.get("state") != "prepared" or intent.get("action") != action:
        raise ValueError("Cancellation action has no matching prepared intent.")
    boundary = _process_boundary_identity(updated)
    if boundary is None:
        raise ValueError("Managed process boundary identity could not be verified.")
    updated["cancellation_action_evidence"] = {
        "version": _CANCELLATION_EVIDENCE_VERSION,
        "task_id": updated.get("task_id"),
        "request_id": request_id,
        "attempt_id": intent.get("attempt_id"),
        "ownership_token": ownership,
        "pid": pid,
        "process_creation_time": str(creation_time),
        "boundary_type": boundary[0], "boundary_id": boundary[1],
        "action": action,
        "action_at": timestamp(),
    }
    updated = _finish_cancellation_intent(updated, state="confirmed")
    updated["cancellation_action_receipts"] = [
        *[item for item in updated.get("cancellation_action_receipts", []) if isinstance(item, dict)],
        updated["cancellation_action_evidence"]]
    updated["cancellation_outcome"] = action
    return updated


def execute_request(request: RuntimeProcessRequest, *, trusted_executable_roots=DEFAULT_EXECUTABLE_ROOTS,
                    trusted_working_roots=DEFAULT_WORKING_ROOTS, task_control_root: str = DEFAULT_TASK_CONTROL_ROOT,
                    enable_task_control: bool = False) -> RuntimeProcessResult:
    if not _under(request.executable, trusted_executable_roots):
        return _result(request, AgentStatus.EXECUTABLE_REJECTED, "Executable is outside trusted runtime roots.", started=False, finished=False)
    if not _under(request.cwd, trusted_working_roots):
        return _result(request, AgentStatus.CWD_REJECTED, "Working directory is outside trusted runtime roots.", started=False, finished=False)
    executable, cwd = _host_path(request.executable), _host_path(request.cwd)
    host_launcher = os.name == "nt" and executable.resolve() == Path(sys.executable).resolve()
    script_is_trusted = bool(request.argv) and _real_under(Path(_host_argument(request.argv[0])), trusted_executable_roots)
    trusted = _real_under(executable, trusted_executable_roots) or (host_launcher and script_is_trusted)
    if not executable.is_file() or not os.access(executable, os.X_OK) or not trusted:
        return _result(request, AgentStatus.EXECUTABLE_REJECTED, "Trusted executable is missing, unexecutable, or escapes its trusted root.", started=False, finished=False)
    if not cwd.is_dir() or not _real_under(cwd, trusted_working_roots):
        return _result(request, AgentStatus.CWD_REJECTED, "Trusted runtime working directory is missing or escapes its root.", started=False, finished=False)
    stdin = stdout = stderr = None
    control = None
    process = None
    job = None
    ownership_token = uuid.uuid4().hex
    process_creation_time = None
    try:
        if request.stdin_path:
            stdin_target = _host_path(request.stdin_path)
            if not _under(request.stdin_path, trusted_working_roots) or not stdin_target.is_file() or not _real_under(stdin_target, trusted_working_roots):
                return _result(request, AgentStatus.STDIN_MISSING, "Runtime-local stdin file is missing or untrusted.", started=False, finished=False)
            stdin = stdin_target.open("rb")
        for field, current in (("stdout_path", "stdout"), ("stderr_path", "stderr")):
            target = getattr(request, field)
            if target:
                target_path = _host_path(target)
                if not _under(target, trusted_working_roots) or not _real_under(target_path.parent, trusted_working_roots):
                    return _result(request, AgentStatus.CWD_REJECTED, f"{current} destination is outside trusted runtime roots.", started=False, finished=False)
                target_path.parent.mkdir(parents=True, exist_ok=True)
                if field == "stdout_path": stdout = target_path.open("wb")
                else: stderr = target_path.open("wb")
        started_at, timer = timestamp(), time.monotonic()
        environment = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", **request.environment}
        process_start_ticks = ""
        try:
            if os.name == "nt":
                from .windows_job import WindowsJob, SuspendedProcess, windows_creation_flags
                job = WindowsJob("Local\\QSRuntime-" + ownership_token)
                process = SuspendedProcess(
                    str(executable), tuple(_host_argument(value) for value in request.argv), str(cwd), environment,
                    stdin or subprocess.DEVNULL, stdout or subprocess.DEVNULL, stderr or subprocess.DEVNULL,
                    windows_creation_flags())
                pid = process.pid
                if not is_valid_windows_process_identity(pid):
                    # The process handle is authoritative here; never use the
                    # malformed PID for cleanup or for a native lookup.
                    try:
                        process.terminate()
                        process.wait(timeout=5)
                    except OSError:
                        pass
                    return _indeterminate_launch_result(
                        request, task_control_root=task_control_root, started_at=started_at,
                        timer=timer, failure_code="invalid_launch_process_identity")
                process_creation_time = job.assign_suspended_process(process)
                pgid = pid
            else:
                process = subprocess.Popen([str(executable), *(_host_argument(value) for value in request.argv)], cwd=str(cwd), stdin=stdin or subprocess.DEVNULL,
                                           stdout=stdout or subprocess.DEVNULL, stderr=stderr or subprocess.DEVNULL,
                                           env=environment, shell=False, start_new_session=True)
                # Validate the value as returned by Popen before any native
                # API, /proc lookup, or cleanup can interpret it as a PID.
                pid = process.pid
                if not is_valid_posix_process_identity(pid):
                    # CPython's Popen destructor otherwise polls waitpid(pid)
                    # and may enqueue the object for later PID-based reaping.
                    # No process identity is trusted here. Disable that implicit
                    # cleanup without inventing a return code or signalling.
                    process._child_created = False
                    return _indeterminate_launch_result(
                        request, task_control_root=task_control_root, started_at=started_at,
                        timer=timer, failure_code="invalid_launch_process_identity")
                try:
                    pgid = os.getpgid(pid)
                except (OSError, TypeError, ValueError, OverflowError):
                    return _indeterminate_launch_result(
                        request, task_control_root=task_control_root, started_at=started_at,
                        timer=timer, failure_code="launch_process_group_identity_unproven")
                if not is_valid_posix_process_identity(pgid):
                    return _indeterminate_launch_result(
                        request, task_control_root=task_control_root, started_at=started_at,
                        timer=timer, failure_code="launch_process_group_identity_unproven")
                # start_new_session=True must make the child its own session
                # and process-group leader. Refuse a mismatched or unsafe group.
                try:
                    if pgid <= 1 or pgid != pid or pgid == os.getpgrp():
                        return _indeterminate_launch_result(
                            request, task_control_root=task_control_root, started_at=started_at,
                            timer=timer, failure_code="launch_process_group_identity_unproven")
                except (OSError, TypeError, ValueError, OverflowError):
                    return _indeterminate_launch_result(
                        request, task_control_root=task_control_root, started_at=started_at,
                        timer=timer, failure_code="launch_process_group_identity_unproven")
                process_start_ticks = _proc_start_ticks(pid)
                if not process_start_ticks:
                    return _indeterminate_launch_result(
                        request, task_control_root=task_control_root, started_at=started_at,
                        timer=timer, failure_code="launch_process_creation_identity_unproven")
            if enable_task_control:
                control = _control_path(request.task_id, task_control_root)
                record = {"schema_version": 1, "task_id": request.task_id, "pid": pid, "pgid": pgid,
                          "process_start_ticks": process_start_ticks or _proc_start_ticks(pid), "state": "RUNNING", "started_at": started_at,
                          "cwd": str(request.cwd), "executable": str(request.executable),
                          "ownership_token": ownership_token}
                if job is not None:
                    record.update({"boundary_type": "windows_job_object+process_group",
                                   "job_name": job.name, "process_creation_time": str(process_creation_time)})
                else:
                    record["boundary_type"] = "posix_session"
                    record["process_creation_time"] = record["process_start_ticks"]
                with _task_record_lock(request.task_id, task_control_root):
                    _atomic_json(control, record)
                    if job is not None:
                        job.resume_process(process, process_creation_time)
            elif job is not None:
                job.resume_process(process, process_creation_time)
        except (OSError, RuntimeError, TimeoutError) as error:
            cleanup_error = None
            if process is not None:
                try:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=5)
                except Exception as failure:
                    cleanup_error = failure
            if job is not None:
                job.close()
            if cleanup_error is not None:
                error.add_note("Owned process cleanup also failed: " + type(cleanup_error).__name__)
            if control is not None:
                with _task_record_lock(request.task_id, task_control_root):
                    existing = _read_control(request.task_id, task_control_root)
                    if existing and existing.get("ownership_token") == ownership_token:
                        failed = dict(existing); failed.update({"state": "FAILED", "finished_at": timestamp()})
                        _atomic_json(control, failed)
            return _result(request, AgentStatus.PROCESS_START_FAILED,
                           type(error).__name__ + ("; cleanup failed: " + type(cleanup_error).__name__ if cleanup_error else ""),
                           started=False, finished=False)
        try:
            return_code = process.wait(timeout=request.timeout_seconds)
            status, diagnostic = AgentStatus.PROCESS_EXITED, ""
        except subprocess.TimeoutExpired:
            if job is not None:
                from .windows_job import windows_cancel_exit_codes
                event_sent = job.send_ctrl_break(pid, process_creation_time, current_pid=os.getpid())
                try:
                    return_code = process.wait(timeout=5 if event_sent else 0.05)
                except subprocess.TimeoutExpired:
                    job.terminate(0xD1F3)
                    if not job.wait_empty(5.0):
                        job.terminate()
                        if not job.wait_empty(5.0):
                            raise TimeoutError("Timed-out Windows runtime task did not exit after bounded termination.")
                    return_code = process.wait(timeout=5)
                status = AgentStatus.PROCESS_TIMEOUT
                diagnostic = "Runtime task timeout exceeded."
            else:
                _signal_group(pgid, signal.SIGTERM)
                try: return_code = process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    _signal_group(pgid, signal.SIGKILL); return_code = process.wait()
                status, diagnostic = AgentStatus.PROCESS_TIMEOUT, "Runtime task timeout exceeded."
        if job is not None and not job.wait_empty(0.25):
            job.terminate(0xD1F2)
            job.wait_empty(5.0)
        if control is not None:
            with _task_record_lock(request.task_id, task_control_root):
                existing = _read_control(request.task_id, task_control_root)
                if not existing or existing.get("ownership_token") != ownership_token:
                    final_state = "FAILED"
                else:
                    if existing.get("state") in {"FINISHED", "FAILED", "CANCELLED", "CANCELLATION_INDETERMINATE", "OUTCOME_INDETERMINATE"}:
                        final_state = str(existing["state"])
                    elif job is not None:
                        action = _cancellation_action_evidence(
                            existing, ownership=ownership_token,
                            request_id=str(existing.get("cancel_token", "")), pid=pid,
                            creation_time=int(process_creation_time or 0))
                        if action:
                            final_state = "CANCELLED"
                        elif _has_unresolved_action_intent(existing):
                            final_state = "CANCELLATION_INDETERMINATE"
                        else:
                            final_state = "FINISHED" if return_code == 0 else "FAILED"
                    else:
                        action = _cancellation_action_evidence(
                            existing, ownership=ownership_token,
                            request_id=str(existing.get("cancel_token", "")), pid=pid,
                            creation_time=int(str(existing.get("process_creation_time", "0"))))
                        if action is not None:
                            final_state = "CANCELLED"
                        elif _has_unresolved_action_intent(existing):
                            final_state = "CANCELLATION_INDETERMINATE"
                        else:
                            final_state = "FINISHED" if return_code == 0 else "FAILED"
                final_record = dict(existing or {})
                final_record.update({"state": final_state, "return_code": return_code,
                                     "finished_at": timestamp()})
                if final_state == "CANCELLATION_INDETERMINATE":
                    final_record["failure_code"] = "cancellation_action_outcome_unproven"
                _atomic_json(control, final_record)
        return RuntimeProcessResult(request.task_id, status, True, True, return_code, pid, pgid,
                                    started_at, timestamp(), time.monotonic() - timer, diagnostic)
    except (OSError, ProtocolError) as error:
        return _result(request, AgentStatus.INTERNAL_AGENT_ERROR, str(error), started=False, finished=False)
    finally:
        if job is not None:
            job.close()
        if process is not None and os.name == "nt" and hasattr(process, "close"):
            process.close()
        for stream in (stdin, stdout, stderr):
            if stream is not None: stream.close()


def _transfer_path(value: object, roots: Iterable[str]) -> Path:
    runtime_path = RuntimePath(str(value))
    path = _host_path(runtime_path)
    if not _under(runtime_path, roots) or not _real_under(path.parent, roots):
        raise ProtocolError("INVALID_REQUEST", "Transfer path is outside managed roots.")
    return path


def stage_in(header: Mapping[str, object], stream: BinaryIO, *, trusted_roots=DEFAULT_TRANSFER_ROOTS) -> dict[str, object]:
    """Atomically stream a declared host artifact into a trusted runtime path."""
    if header.get("schema_version") != 1 or header.get("operation") != "stage_in":
        raise ProtocolError("UNSUPPORTED_SCHEMA", "Unsupported stage-in request.")
    destination = _transfer_path(header.get("destination"), trusted_roots)
    expected = str(header.get("sha256", ""))
    if expected and not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ProtocolError("INVALID_REQUEST", "stage-in SHA-256 is invalid.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".qs-stage.tmp")
    digest, size = hashlib.sha256(), 0
    try:
        with temporary.open("wb") as target:
            while block := stream.read(1024 * 1024):
                target.write(block); digest.update(block); size += len(block)
            target.flush(); os.fsync(target.fileno())
        actual = digest.hexdigest()
        if expected and actual != expected:
            raise ProtocolError("INVALID_REQUEST", "stage-in SHA-256 does not match declared artifact.")
        os.replace(temporary, destination)
        return {"schema_version": 1, "status": "TRANSFERRED", "destination": str(destination), "size": size, "sha256": actual}
    except Exception:
        try: temporary.unlink()
        except OSError: pass
        raise


def stage_out(request: Mapping[str, object], output: BinaryIO, *, trusted_roots=DEFAULT_TRANSFER_ROOTS) -> None:
    if request.get("schema_version") != 1 or request.get("operation") != "stage_out":
        raise ProtocolError("UNSUPPORTED_SCHEMA", "Unsupported stage-out request.")
    source = _transfer_path(request.get("source"), trusted_roots)
    if not source.is_file() or not _real_under(source, trusted_roots):
        raise ProtocolError("INVALID_REQUEST", "Declared runtime output is missing or untrusted.")
    with source.open("rb") as stream:
        while block := stream.read(1024 * 1024): output.write(block)


def install_engine_pack(request: Mapping[str, object], *, engine_root: str = "/opt/quantumstudio/engines") -> dict[str, object]:
    """Activate only a fully staged, manifest-verified Engine Pack.

    The host can transfer files only to the fixed `.staging` root. This agent
    verifies the staged manifest and hashes before the single atomic rename.
    """
    if request.get("schema_version") != 1 or request.get("operation") != "install_engine_pack":
        raise ProtocolError("UNSUPPORTED_SCHEMA", "Unsupported Engine Pack install request.")
    pack_id, version = _safe_task_id(str(request.get("pack_id", ""))), _safe_task_id(str(request.get("version", "")))
    expected = str(request.get("manifest_sha256", ""))
    if not re.fullmatch(r"[0-9a-f]{64}", expected): raise ProtocolError("INVALID_REQUEST", "Engine Pack manifest digest is invalid.")
    root = Path(engine_root); stage = root / ".staging" / f"{pack_id}-{version}"; manifest_file = stage / "engine-pack.json"
    if not manifest_file.is_file() or _sha256(manifest_file) != expected: raise ProtocolError("INVALID_REQUEST", "Staged Engine Pack manifest is missing or mismatched.")
    try: manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error: raise ProtocolError("INVALID_REQUEST", "Staged Engine Pack manifest is malformed.") from error
    if not isinstance(manifest, dict) or manifest.get("schema_version") != "1" or str(manifest.get("engine_pack_version")) != version:
        raise ProtocolError("INVALID_REQUEST", "Staged Engine Pack identity is invalid.")
    if manifest.get("platform") not in {"linux", "any"} or manifest.get("architecture") not in {"x86_64", "any", os.uname().machine}:
        raise ProtocolError("INVALID_REQUEST", "Staged Engine Pack platform or architecture is incompatible.")
    for item in manifest.get("engines", []):
        if not isinstance(item, dict): raise ProtocolError("INVALID_REQUEST", "Staged Engine Pack tool entry is invalid.")
        relative, digest = str(item.get("relative_path", "")), str(item.get("sha256", ""))
        candidate = (stage / relative).resolve()
        if not relative or stage not in candidate.parents or not candidate.is_file() or _sha256(candidate) != digest:
            raise ProtocolError("INVALID_REQUEST", "Staged Engine Pack tool verification failed.")
    marker = root / "quantumstudio-engine-packs.json"
    root.mkdir(parents=True, exist_ok=True)
    if marker.exists():
        try: owned = json.loads(marker.read_text(encoding="utf-8")).get("owner") == "QuantumStudio"
        except (OSError, json.JSONDecodeError): owned = False
        if not owned: raise ProtocolError("INVALID_REQUEST", "Engine Pack root ownership marker is invalid.")
    elif any(item.name != ".staging" for item in root.iterdir()):
        raise ProtocolError("INVALID_REQUEST", "Engine Pack root contains unknown content.")
    else: _atomic_json(marker, {"schema_version": 1, "owner": "QuantumStudio", "kind": "managed-engine-packs"})
    target = root / "packs" / f"{pack_id}-{version}"; target.parent.mkdir(exist_ok=True)
    if target.exists():
        existing = target / "engine-pack.json"
        if not existing.is_file() or _sha256(existing) != expected: raise ProtocolError("INVALID_REQUEST", "Installed Engine Pack version conflicts with staged identity.")
    else: os.replace(stage, target)
    _atomic_json(root / "active.json", {"schema_version": 1, "pack_id": pack_id, "version": version, "manifest_sha256": expected, "relative_root": str(target.relative_to(root))})
    return {"schema_version": 1, "status": "ACTIVATED", "pack_id": pack_id, "version": version, "manifest_sha256": expected}


def task_status(task_id: str, *, task_control_root: str = DEFAULT_TASK_CONTROL_ROOT) -> dict[str, object]:
    task_id = _safe_task_id(task_id)
    with _task_record_lock(task_id, task_control_root):
        record = _read_control(task_id, task_control_root)
        if record is None:
            return {"schema_version": 1, "status": AgentStatus.TASK_NOT_FOUND.value, "task_id": task_id}
        terminal = {"FINISHED", "FAILED", "CANCELLED", "CANCELLATION_INDETERMINATE", "OUTCOME_INDETERMINATE"}
        if record.get("state") not in terminal:
            try:
                action = _cancellation_action_evidence(
                    record, ownership=str(record.get("ownership_token", "")),
                    request_id=str(record.get("cancel_token", "")),
                    pid=int(record.get("pid", 0)),
                    creation_time=int(str(record.get("process_creation_time", "0"))))
            except (TypeError, ValueError):
                action = None
            alive = _record_alive(record)
            if record.get("state") not in {"RUNNING", "CANCELLING"}:
                updated = dict(record)
                updated.update({"state": "OUTCOME_INDETERMINATE",
                                "failure_code": "task_control_state_unknown",
                                "finished_at": timestamp()})
            elif _has_unresolved_action_intent(record):
                updated = _mark_cancellation_indeterminate(record, error_type="restart_reconciliation")
            elif os.name != "nt" and not _posix_record_process_ids_valid(record):
                updated = dict(record)
                updated.update({"state": "OUTCOME_INDETERMINATE",
                                "failure_code": "task_process_identity_unproven",
                                "finished_at": timestamp()})
            elif alive:
                updated = None
            elif action is not None:
                updated = dict(record)
                updated.update({"state": "CANCELLED", "cancellation_outcome": action,
                                "cancelled_at": timestamp(), "finished_at": timestamp()})
            else:
                code = _known_return_code(record)
                updated = dict(record)
                updated["return_code"] = code
                updated["finished_at"] = timestamp()
                if code is None:
                    updated.update({"state": "OUTCOME_INDETERMINATE",
                                    "failure_code": "task_exit_outcome_unproven"})
                else:
                    updated["state"] = "FINISHED" if code == 0 else "FAILED"
            if updated is not None:
                _atomic_json(_control_path(task_id, task_control_root), updated)
                record = _read_control(task_id, task_control_root)
                if record is None:
                    raise ProtocolError("INVALID_REQUEST", "Committed task record disappeared.")
    states = {"FINISHED": AgentStatus.TASK_FINISHED, "FAILED": AgentStatus.TASK_FAILED,
              "CANCELLED": AgentStatus.TASK_CANCELLED,
              "CANCELLATION_INDETERMINATE": AgentStatus.TASK_CANCELLATION_INDETERMINATE,
              "OUTCOME_INDETERMINATE": AgentStatus.TASK_OUTCOME_INDETERMINATE}
    state = states.get(record.get("state"), AgentStatus.TASK_RUNNING)
    return {"schema_version": 1, "status": state.value, "task_id": task_id,
            "failure_code": record.get("failure_code"), "return_code": record.get("return_code"),
            "diagnostic": ("Task outcome is unproven; operator review is required."
                           if state in {AgentStatus.TASK_CANCELLATION_INDETERMINATE,
                                        AgentStatus.TASK_OUTCOME_INDETERMINATE} else ""),
            "record": record}


def _known_return_code(record: Mapping[str, object]) -> int | None:
    code = record.get("return_code")
    if type(code) is int:
        return code
    if os.name != "nt" or _process_boundary_identity(record) is None:
        return None
    pid, created = record.get("pid"), record.get("process_creation_time")
    if type(pid) is not int or not isinstance(created, str) or not created.isdecimal():
        return None
    from .windows_job import process_exit_code
    try:
        return process_exit_code(pid, int(created))
    except OSError:
        return None


def _natural_terminal_record(record: Mapping[str, object]) -> dict[str, object]:
    final = dict(record)
    code = _known_return_code(record)
    final.update({"return_code": code, "finished_at": timestamp(),
                  "state": "FINISHED" if code == 0 else "FAILED" if code is not None else "OUTCOME_INDETERMINATE"})
    if code is None:
        final["failure_code"] = "task_exit_outcome_unproven"
    return final


def _has_unresolved_action_intent(record: Mapping[str, object]) -> bool:
    attempts = record.get("cancellation_action_attempts", [])
    intent = record.get("cancellation_action_intent")
    if isinstance(intent, dict):
        attempts = [*attempts, intent] if isinstance(attempts, list) else [intent]
    if not isinstance(attempts, list) or not any(isinstance(item, dict) for item in attempts):
        return False
    try:
        if _cancellation_action_evidence(
                record, ownership=str(record.get("ownership_token", "")),
                request_id=str(record.get("cancel_token", "")),
                pid=int(record.get("pid", 0)),
                creation_time=int(str(record.get("process_creation_time", "0")))) is not None:
            return False
    except (TypeError, ValueError, KeyError):
        pass
    return any(isinstance(item, dict) and item.get("state") != "failed" for item in attempts)


def _mark_cancellation_indeterminate(record: Mapping[str, object], *, error_type: str) -> dict[str, object]:
    final = dict(record)
    final.update({"state": "CANCELLATION_INDETERMINATE",
                  "failure_code": "cancellation_action_outcome_unproven",
                  "cancellation_persistence_error": error_type})
    return final


def cancel_task(task_id: str, *, grace_seconds: float = 2.0, task_control_root: str = DEFAULT_TASK_CONTROL_ROOT) -> dict[str, object]:
    task_id = _safe_task_id(task_id)
    try:
        force_sent = False
        with _task_record_lock(task_id, task_control_root):
            record = _read_control(task_id, task_control_root)
            if record is None:
                return {"schema_version": 1, "status": AgentStatus.TASK_NOT_FOUND.value, "task_id": task_id}
            state = str(record.get("state", ""))
            if state == "CANCELLED":
                return {"schema_version": 1, "status": AgentStatus.TASK_CANCELLED.value,
                        "task_id": task_id, "outcome": record.get("cancellation_outcome", "ALREADY_CANCELLED")}
            if state in {"FINISHED", "FAILED", "OUTCOME_INDETERMINATE"}:
                return _cancel_terminal_result(task_id, record)
            if state == "CANCELLATION_INDETERMINATE" or _has_unresolved_action_intent(record):
                if state != "CANCELLATION_INDETERMINATE":
                    record = _mark_cancellation_indeterminate(record, error_type="cancel_reconciliation")
                    _atomic_json(_control_path(task_id, task_control_root), record)
                return _cancel_terminal_result(task_id, record)
            if os.name != "nt" and state in {"RUNNING", "CANCELLING"} \
                    and not _posix_record_process_ids_valid(record):
                record = dict(record)
                record.update({"state": "OUTCOME_INDETERMINATE",
                               "failure_code": "task_process_identity_unproven",
                               "finished_at": timestamp()})
                _atomic_json(_control_path(task_id, task_control_root), record)
                return _cancel_terminal_result(task_id, record)
            if state == "CANCELLING":
                if not _record_alive(record):
                    try:
                        action = _cancellation_action_evidence(
                            record, ownership=str(record.get("ownership_token", "")),
                            request_id=str(record.get("cancel_token", "")),
                            pid=int(record.get("pid", 0)),
                            creation_time=int(str(record.get("process_creation_time", "0"))))
                    except (TypeError, ValueError):
                        action = None
                    final = (dict(record) if action is not None else _natural_terminal_record(record))
                    if action is not None:
                        final.update({"state": "CANCELLED", "cancellation_outcome": action,
                                      "cancelled_at": timestamp(), "finished_at": timestamp()})
                    _atomic_json(_control_path(task_id, task_control_root), final)
                    return _cancel_terminal_result(task_id, final)
                return {"schema_version": 1, "status": AgentStatus.TASK_RUNNING.value,
                        "task_id": task_id, "outcome": "CANCELLATION_IN_PROGRESS"}
            if state != "RUNNING":
                return {"schema_version": 1, "status": "FAILED", "task_id": task_id,
                        "diagnostic": "Managed task state is not cancellable."}
            ownership = str(record.get("ownership_token", ""))
            if not re.fullmatch(r"[0-9a-f]{32}", ownership):
                return {"schema_version": 1, "status": "FAILED", "task_id": task_id,
                        "diagnostic": "Managed task ownership could not be verified."}
            cancel_token = uuid.uuid4().hex
            pid = int(record.get("pid", 0))
            if os.name == "nt":
                from .windows_job import WindowsJob, process_exit_state
                name = str(record.get("job_name", ""))
                if (record.get("boundary_type") != "windows_job_object+process_group"
                        or not re.fullmatch(r"Local\\QSRuntime-([0-9a-f]{32})", name)
                        or name.rsplit("-", 1)[-1] != ownership):
                    return {"schema_version": 1, "status": "FAILED", "task_id": task_id,
                            "diagnostic": "Managed Windows process ownership could not be verified."}
                job = WindowsJob(name, create=False)
                try:
                    if job.active_processes() == 0:
                        final = _natural_terminal_record(record)
                        _atomic_json(_control_path(task_id, task_control_root), final)
                        return _cancel_terminal_result(task_id, final)
                    creation = int(str(record.get("process_creation_time", "")))
                    process_state = process_exit_state(pid, creation)
                    if process_state is None:
                        final = _natural_terminal_record(record)
                        _atomic_json(_control_path(task_id, task_control_root), final)
                        return _cancel_terminal_result(task_id, final)
                    if process_state:
                        final = _natural_terminal_record(record)
                        _atomic_json(_control_path(task_id, task_control_root), final)
                        return _cancel_terminal_result(task_id, final)
                    if not job.is_process_member(pid, creation):
                        return {"schema_version": 1, "status": "FAILED", "task_id": task_id,
                                "diagnostic": "Managed process identity changed; no signal was sent."}
                    cancelling = dict(record); cancelling.update({"state": "CANCELLING", "cancel_requested": True,
                                                                  "cancel_token": cancel_token,
                                                                   "cancel_requested_at": timestamp(),
                                                                   "cancel_started_at": timestamp()})
                    _atomic_json(_control_path(task_id, task_control_root), cancelling)
                    process_state = process_exit_state(pid, creation)
                    if process_state is None:
                        final = _natural_terminal_record(cancelling)
                        _atomic_json(_control_path(task_id, task_control_root), final)
                        return _cancel_terminal_result(task_id, final)
                    if process_state:
                        final = _natural_terminal_record(cancelling)
                        final["cancellation_outcome"] = "lost_natural_completion_race"
                        _atomic_json(_control_path(task_id, task_control_root), final)
                        return _cancel_terminal_result(task_id, final)
                    prepared = _prepare_cancellation_action(
                        cancelling, action="graceful", ownership=ownership,
                        request_id=cancel_token, pid=pid, creation_time=creation)
                    _atomic_json(_control_path(task_id, task_control_root), prepared)
                    cancelling = prepared
                    event_sent = job.send_ctrl_break(pid, creation, current_pid=os.getpid())
                    if event_sent:
                        acted = _with_cancellation_action(
                            cancelling, action="graceful", ownership=ownership,
                            request_id=cancel_token, pid=pid, creation_time=creation)
                        _persist_cancellation_action_receipt(_control_path(task_id, task_control_root), acted)
                    else:
                        failed = _finish_cancellation_intent(cancelling, state="failed")
                        _atomic_json(_control_path(task_id, task_control_root), failed)
                finally:
                    job.close()
            else:
                # POSIX keeps its new session/process group and verifies the
                # recorded process identity before requesting cancellation.
                pgid = int(record.get("pgid", 0))
                if not _record_alive(record):
                    final = _natural_terminal_record(record)
                    _atomic_json(_control_path(task_id, task_control_root), final)
                    return _cancel_terminal_result(task_id, final)
                cancelling = dict(record); cancelling.update({"state": "CANCELLING", "cancel_requested": True,
                                                              "cancel_token": cancel_token,
                                                              "cancel_started_at": timestamp()})
                _atomic_json(_control_path(task_id, task_control_root), cancelling)
                creation = int(str(record.get("process_creation_time", "")))
                prepared = _prepare_cancellation_action(
                    cancelling, action="graceful", ownership=ownership,
                    request_id=cancel_token, pid=pid, creation_time=creation)
                _atomic_json(_control_path(task_id, task_control_root), prepared)
                try:
                    _signal_group(pgid, signal.SIGTERM)
                except (OSError, ValueError):
                    _atomic_json(_control_path(task_id, task_control_root),
                                 _finish_cancellation_intent(prepared, state="failed"))
                    raise
                acted = _with_cancellation_action(
                    prepared, action="graceful", ownership=ownership,
                    request_id=cancel_token, pid=pid, creation_time=creation)
                acted["cancellation_outcome"] = "TERMINATED"
                _persist_cancellation_action_receipt(_control_path(task_id, task_control_root), acted)
        if os.name == "nt":
            # Wait outside the record lock so natural completion can win.
            if event_sent:
                deadline = time.monotonic() + max(0.0, float(grace_seconds))
                while True:
                    with _task_record_lock(task_id, task_control_root):
                        latest = _read_control(task_id, task_control_root)
                        if not latest or latest.get("ownership_token") != ownership:
                            return {"schema_version": 1, "status": "FAILED", "task_id": task_id,
                                    "diagnostic": "Managed task ownership changed during graceful cancellation."}
                        if latest.get("state") in {"FINISHED", "FAILED", "CANCELLED", "CANCELLATION_INDETERMINATE", "OUTCOME_INDETERMINATE"}:
                            return _cancel_terminal_result(task_id, latest)
                        if latest.get("state") != "CANCELLING" or latest.get("cancel_token") != cancel_token:
                            return {"schema_version": 1, "status": "FAILED", "task_id": task_id,
                                    "diagnostic": "Managed cancellation ownership changed."}
                        with WindowsJob(name, create=False) as wait_job:
                            active = wait_job.active_processes()
                    remaining = deadline - time.monotonic()
                    if active == 0 or remaining <= 0:
                        break
                    time.sleep(min(0.02, remaining))
            with _task_record_lock(task_id, task_control_root):
                latest = _read_control(task_id, task_control_root)
                if not latest or latest.get("ownership_token") != ownership:
                    return {"schema_version": 1, "status": "FAILED", "task_id": task_id,
                            "diagnostic": "Managed task ownership changed during cancellation."}
                if latest.get("state") in {"FINISHED", "FAILED", "CANCELLED", "CANCELLATION_INDETERMINATE", "OUTCOME_INDETERMINATE"}:
                    return _cancel_terminal_result(task_id, latest)
                if latest.get("cancel_token") != cancel_token or latest.get("state") != "CANCELLING":
                    return {"schema_version": 1, "status": "FAILED", "task_id": task_id,
                            "diagnostic": "Managed task state changed during cancellation."}
                with WindowsJob(name, create=False) as job:
                    if job.active_processes() == 0:
                        code = _known_return_code(latest)
                        action = _cancellation_action_evidence(
                            latest, ownership=ownership, request_id=cancel_token,
                            pid=pid, creation_time=creation)
                        final_state = ("CANCELLED" if action is not None else
                                       "FINISHED" if code == 0 else
                                       "FAILED" if code is not None else "OUTCOME_INDETERMINATE")
                        outcome = action or "lost_natural_completion_race"
                    else:
                        prepared = _prepare_cancellation_action(
                            latest, action="terminated", ownership=ownership,
                            request_id=cancel_token, pid=pid, creation_time=creation)
                        _atomic_json(_control_path(task_id, task_control_root), prepared)
                        latest = prepared
                        terminated = job.terminate()
                        if terminated:
                            acted = _with_cancellation_action(
                                latest, action="terminated", ownership=ownership,
                                request_id=cancel_token, pid=pid, creation_time=creation)
                            _persist_cancellation_action_receipt(_control_path(task_id, task_control_root), acted)
                            outcome = "terminated"
                        else:
                            failed = _finish_cancellation_intent(latest, state="failed")
                            _atomic_json(_control_path(task_id, task_control_root), failed)
                            latest = failed
                            outcome = _cancellation_action_evidence(
                                latest, ownership=ownership, request_id=cancel_token,
                                pid=pid, creation_time=creation) or "lost_natural_completion_race"
                        final_state = "CANCELLING"
            if final_state == "CANCELLING":
                deadline = time.monotonic() + 5.0
                while True:
                    with _task_record_lock(task_id, task_control_root):
                        latest = _read_control(task_id, task_control_root)
                        if not latest or latest.get("ownership_token") != ownership:
                            return {"schema_version": 1, "status": "FAILED", "task_id": task_id,
                                    "diagnostic": "Managed task ownership changed during termination."}
                        if latest.get("state") in {"FINISHED", "FAILED", "CANCELLED", "CANCELLATION_INDETERMINATE", "OUTCOME_INDETERMINATE"}:
                            return _cancel_terminal_result(task_id, latest)
                        if latest.get("cancel_token") != cancel_token:
                            return {"schema_version": 1, "status": "FAILED", "task_id": task_id,
                                    "diagnostic": "Managed cancellation ownership changed."}
                        with WindowsJob(name, create=False) as wait_job:
                            active = wait_job.active_processes()
                    remaining = deadline - time.monotonic()
                    if active == 0 or remaining <= 0:
                        break
                    time.sleep(min(0.02, remaining))
                emptied = active == 0
                with _task_record_lock(task_id, task_control_root):
                    latest = _read_control(task_id, task_control_root)
                    if not latest or latest.get("ownership_token") != ownership:
                        return {"schema_version": 1, "status": "FAILED", "task_id": task_id,
                                "diagnostic": "Managed task ownership changed during termination."}
                    if latest.get("state") in {"FINISHED", "FAILED", "CANCELLED", "CANCELLATION_INDETERMINATE", "OUTCOME_INDETERMINATE"}:
                        return _cancel_terminal_result(task_id, latest)
                    if latest.get("cancel_token") != cancel_token:
                        return {"schema_version": 1, "status": "FAILED", "task_id": task_id,
                                "diagnostic": "Managed cancellation ownership changed."}
                    with WindowsJob(name, create=False) as job:
                        if not emptied or job.active_processes():
                            prepared = _prepare_cancellation_action(
                                latest, action="forced", ownership=ownership,
                                request_id=cancel_token, pid=pid, creation_time=creation)
                            _atomic_json(_control_path(task_id, task_control_root), prepared)
                            latest = prepared
                            if job.terminate(0xD1F3):
                                latest = _with_cancellation_action(
                                    latest, action="forced", ownership=ownership,
                                    request_id=cancel_token, pid=pid, creation_time=creation)
                                _persist_cancellation_action_receipt(_control_path(task_id, task_control_root), latest)
                                outcome = "forced"
                            else:
                                failed = _finish_cancellation_intent(latest, state="failed")
                                _atomic_json(_control_path(task_id, task_control_root), failed)
                                latest = failed
                deadline = time.monotonic() + 5.0
                while True:
                    with _task_record_lock(task_id, task_control_root):
                        latest = _read_control(task_id, task_control_root)
                        if not latest or latest.get("ownership_token") != ownership:
                            return {"schema_version": 1, "status": "FAILED", "task_id": task_id,
                                    "diagnostic": "Managed task ownership changed during force termination."}
                        if latest.get("state") in {"FINISHED", "FAILED", "CANCELLED", "CANCELLATION_INDETERMINATE", "OUTCOME_INDETERMINATE"}:
                            return _cancel_terminal_result(task_id, latest)
                        if latest.get("cancel_token") != cancel_token:
                            return {"schema_version": 1, "status": "FAILED", "task_id": task_id,
                                    "diagnostic": "Managed cancellation ownership changed."}
                        with WindowsJob(name, create=False) as wait_job:
                            active = wait_job.active_processes()
                    remaining = deadline - time.monotonic()
                    if active == 0:
                        break
                    if remaining <= 0:
                        raise TimeoutError("Owned Windows task did not exit after bounded force termination.")
                    time.sleep(min(0.02, remaining))
                final_state = "CANCELLED"
            with _task_record_lock(task_id, task_control_root):
                latest = _read_control(task_id, task_control_root)
                if latest and latest.get("ownership_token") == ownership and latest.get("cancel_token") == cancel_token and latest.get("state") == "CANCELLING":
                    action = _cancellation_action_evidence(
                        latest, ownership=ownership, request_id=cancel_token,
                        pid=pid, creation_time=creation)
                    if action is not None:
                        final_state, outcome = "CANCELLED", action
                    elif _has_unresolved_action_intent(latest):
                        final_state, outcome = "CANCELLATION_INDETERMINATE", "cancellation_action_outcome_unproven"
                    elif final_state == "CANCELLED":
                        code = _known_return_code(latest)
                        final_state, outcome = ("FINISHED" if code == 0 else
                                                "FAILED" if code is not None else
                                                "OUTCOME_INDETERMINATE"), "lost_natural_completion_race"
                    final = dict(latest); final.update({"state": final_state,
                                                        "cancellation_outcome": outcome,
                                                        "cancelled_at": timestamp() if final_state == "CANCELLED" else None})
                    if final_state == "CANCELLATION_INDETERMINATE":
                        final["failure_code"] = "cancellation_action_outcome_unproven"
                    elif final_state in {"FINISHED", "FAILED", "OUTCOME_INDETERMINATE"}:
                        final["return_code"] = _known_return_code(latest)
                        if final_state == "OUTCOME_INDETERMINATE":
                            final["failure_code"] = "task_exit_outcome_unproven"
                    _atomic_json(_control_path(task_id, task_control_root), final)
                else:
                    final = latest or {}
            return _cancel_terminal_result(task_id, final)
        deadline = time.monotonic() + max(0.0, float(grace_seconds))
        while time.monotonic() < deadline:
            with _task_record_lock(task_id, task_control_root):
                latest = _read_control(task_id, task_control_root)
                if not latest or latest.get("ownership_token") != ownership or latest.get("state") in {"FINISHED", "FAILED", "CANCELLED", "CANCELLATION_INDETERMINATE", "OUTCOME_INDETERMINATE"}:
                    return _cancel_terminal_result(task_id, latest or {})
                if latest.get("cancel_token") != cancel_token:
                    return {"schema_version": 1, "status": "FAILED", "task_id": task_id,
                            "diagnostic": "Managed cancellation ownership changed."}
                alive = _record_alive(latest)
            if not alive:
                break
            time.sleep(min(0.03, max(0.0, deadline-time.monotonic())))
        with _task_record_lock(task_id, task_control_root):
            latest = _read_control(task_id, task_control_root)
            if not latest or latest.get("ownership_token") != ownership or latest.get("state") in {"FINISHED", "FAILED", "CANCELLED", "CANCELLATION_INDETERMINATE", "OUTCOME_INDETERMINATE"}:
                return _cancel_terminal_result(task_id, latest or {})
            if latest.get("cancel_token") != cancel_token:
                return {"schema_version": 1, "status": "FAILED", "task_id": task_id,
                        "diagnostic": "Managed cancellation ownership changed."}
            if _record_alive(latest):
                prepared = _prepare_cancellation_action(
                    latest, action="forced", ownership=ownership,
                    request_id=cancel_token, pid=pid, creation_time=creation)
                _atomic_json(_control_path(task_id, task_control_root), prepared)
                try:
                    _signal_group(pgid, signal.SIGKILL)
                except (OSError, ValueError):
                    _atomic_json(_control_path(task_id, task_control_root),
                                 _finish_cancellation_intent(prepared, state="failed"))
                    raise
                acted = _with_cancellation_action(
                    prepared, action="forced", ownership=ownership,
                    request_id=cancel_token, pid=pid, creation_time=creation)
                acted["cancellation_outcome"] = "KILLED_AFTER_GRACE"
                _persist_cancellation_action_receipt(_control_path(task_id, task_control_root), acted)
                outcome = "KILLED_AFTER_GRACE"
                force_sent = True
        if force_sent:
            deadline = time.monotonic() + 5.0
            while True:
                with _task_record_lock(task_id, task_control_root):
                    latest = _read_control(task_id, task_control_root)
                    if not latest or latest.get("ownership_token") != ownership:
                        return {"schema_version": 1, "status": "FAILED", "task_id": task_id,
                                "diagnostic": "Managed task ownership changed during force termination."}
                    if latest.get("state") in {"FINISHED", "FAILED", "CANCELLED", "CANCELLATION_INDETERMINATE", "OUTCOME_INDETERMINATE"}:
                        return _cancel_terminal_result(task_id, latest)
                    if latest.get("cancel_token") != cancel_token:
                        return {"schema_version": 1, "status": "FAILED", "task_id": task_id,
                                "diagnostic": "Managed cancellation ownership changed."}
                    alive = _record_alive(latest)
                if not alive:
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Owned POSIX task did not exit after bounded force termination.")
                time.sleep(min(0.03, remaining))
        with _task_record_lock(task_id, task_control_root):
            latest = _read_control(task_id, task_control_root)
            if not latest or latest.get("ownership_token") != ownership:
                return {"schema_version": 1, "status": "FAILED", "task_id": task_id,
                        "diagnostic": "Managed task ownership changed before finalization."}
            if latest.get("state") in {"FINISHED", "FAILED", "CANCELLED", "CANCELLATION_INDETERMINATE", "OUTCOME_INDETERMINATE"}:
                return _cancel_terminal_result(task_id, latest)
            if latest.get("cancel_token") != cancel_token or latest.get("state") != "CANCELLING":
                return {"schema_version": 1, "status": "FAILED", "task_id": task_id,
                        "diagnostic": "Managed cancellation ownership changed before finalization."}
            action = _cancellation_action_evidence(
                latest, ownership=ownership, request_id=cancel_token,
                pid=pid, creation_time=creation)
            if action is not None:
                final = dict(latest)
                final.update({"state": "CANCELLED",
                              "cancellation_outcome": "KILLED_AFTER_GRACE" if action == "forced" else "TERMINATED",
                              "cancelled_at": timestamp()})
            elif _has_unresolved_action_intent(latest):
                final = _mark_cancellation_indeterminate(latest, error_type="cancel_finalization")
            else:
                final = _natural_terminal_record(latest)
            _atomic_json(_control_path(task_id, task_control_root), final)
        return _cancel_terminal_result(task_id, final)
    except (OSError, ValueError, RuntimeError, TimeoutError, KeyError, TypeError) as error:
        try:
            with _task_record_lock(task_id, task_control_root):
                latest = _read_control(task_id, task_control_root)
                if latest and _has_unresolved_action_intent(latest):
                    indeterminate = _mark_cancellation_indeterminate(
                        latest, error_type=type(error).__name__)
                    try:
                        _atomic_json(_control_path(task_id, task_control_root), indeterminate)
                    except (OSError, TypeError, ValueError):
                        # The durable prepared intent still prevents ordinary
                        # completion on finalization/restart; retain its record.
                        pass
                    return {"schema_version": 1,
                            "status": AgentStatus.TASK_CANCELLATION_INDETERMINATE.value,
                            "task_id": task_id,
                            "failure_code": "cancellation_action_outcome_unproven",
                            "diagnostic": type(error).__name__}
        except (OSError, ValueError, RuntimeError, TimeoutError, KeyError, TypeError):
            pass
        return {"schema_version": 1, "status": "FAILED", "task_id": task_id,
                "diagnostic": type(error).__name__}


def _cancel_terminal_result(task_id: str, record: Mapping[str, object]) -> dict[str, object]:
    state = str(record.get("state", ""))
    if state == "CANCELLATION_INDETERMINATE" or _has_unresolved_action_intent(record):
        return {"schema_version": 1, "status": AgentStatus.TASK_CANCELLATION_INDETERMINATE.value,
                "task_id": task_id, "failure_code": "cancellation_action_outcome_unproven",
                "return_code": record.get("return_code"),
                "diagnostic": "Cancellation outcome is unproven; operator review is required."}
    if state == "CANCELLED":
        return {"schema_version": 1, "status": AgentStatus.TASK_CANCELLED.value,
                "task_id": task_id, "outcome": record.get("cancellation_outcome", "TERMINATED")}
    if state == "OUTCOME_INDETERMINATE":
        return {"schema_version": 1, "status": AgentStatus.TASK_OUTCOME_INDETERMINATE.value,
                "task_id": task_id, "failure_code": record.get("failure_code"),
                "return_code": record.get("return_code")}
    if state in {"FINISHED", "FAILED"}:
        return {"schema_version": 1,
                "status": (AgentStatus.TASK_FINISHED if state == "FINISHED" else AgentStatus.TASK_FAILED).value,
                "task_id": task_id, "return_code": record.get("return_code")}
    return {"schema_version": 1, "status": AgentStatus.TASK_RUNNING.value,
            "task_id": task_id, "outcome": "CANCELLATION_IN_PROGRESS"}


def _read_json_stdin() -> Mapping[str, object]:
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProtocolError("INVALID_REQUEST", "Agent control request is malformed.") from error
    if not isinstance(data, dict): raise ProtocolError("INVALID_REQUEST", "Agent control request must be an object.")
    return data


def _write_json(payload: Mapping[str, object]) -> None:
    sys.stdout.buffer.write((json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))


def run_stdio() -> int:
    request = None
    try:
        request = RuntimeProcessRequest.from_json(sys.stdin.buffer.read())
        result = execute_request(request, enable_task_control=True)
    except ProtocolError as error:
        result = RuntimeProcessResult(request.task_id if request else "", AgentStatus.UNSUPPORTED_SCHEMA if error.code == "UNSUPPORTED_SCHEMA" else AgentStatus.INVALID_REQUEST, False, False, diagnostic=str(error))
    except Exception:
        result = RuntimeProcessResult(request.task_id if request else "", AgentStatus.INTERNAL_AGENT_ERROR, False, False, diagnostic="Unexpected runtime-agent internal error.")
    sys.stdout.buffer.write(result.to_json()); return 0


def main(argv: list[str] | None = None) -> int:
    command = argv or sys.argv[1:]
    if command == ["health"] or command == ["version"]:
        _write_json(json.loads(RuntimeAgentHealth(True, AGENT_VERSION, 1, capabilities=CAPABILITIES).to_json())); return 0
    if command == ["run"]: return run_stdio()
    try:
        if command == ["stage-in"]:
            line = sys.stdin.buffer.readline(65537)
            if not line or len(line) > 65536: raise ProtocolError("INVALID_REQUEST", "stage-in header is invalid.")
            _write_json(stage_in(json.loads(line.decode("utf-8")), sys.stdin.buffer)); return 0
        if command == ["stage-out"]:
            stage_out(_read_json_stdin(), sys.stdout.buffer); return 0
        if command == ["install-engine-pack"]:
            _write_json(install_engine_pack(_read_json_stdin())); return 0
        if command == ["status"]:
            data = _read_json_stdin(); _write_json(task_status(str(data.get("task_id", "")))); return 0
        if command == ["cancel"]:
            data = _read_json_stdin(); _write_json(cancel_task(str(data.get("task_id", "")), grace_seconds=float(data.get("grace_seconds", 2.0)))); return 0
    except ProtocolError as error:
        _write_json({"schema_version": 1, "status": AgentStatus.TRANSFER_REJECTED.value, "diagnostic": str(error)}); return 1
    except Exception:
        _write_json({"schema_version": 1, "status": AgentStatus.TRANSFER_FAILED.value, "diagnostic": "Runtime-agent operation failed."}); return 1
    return 2


if __name__ == "__main__": raise SystemExit(main())
