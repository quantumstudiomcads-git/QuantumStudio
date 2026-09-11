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
from typing import BinaryIO, Iterable, Mapping

from .protocol import AGENT_VERSION, AgentStatus, ProtocolError, RuntimeAgentHealth, RuntimePath, RuntimeProcessRequest, RuntimeProcessResult, timestamp

DEFAULT_EXECUTABLE_ROOTS = ("/opt/quantumstudio/engines", "/opt/quantumstudio/runtime/bin")
DEFAULT_WORKING_ROOTS = ("/var/lib/quantumstudio/workflows", "/var/lib/quantumstudio/staging")
DEFAULT_TRANSFER_ROOTS = DEFAULT_WORKING_ROOTS + ("/var/lib/quantumstudio/pseudopotentials", "/opt/quantumstudio/engines/.staging")
DEFAULT_TASK_CONTROL_ROOT = "/var/lib/quantumstudio/runtime/tasks"
CAPABILITIES = ("run", "status", "cancel", "stage_in", "stage_out", "install_engine_pack")
_TASK_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


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
    if str(record.get("state", "")) != "RUNNING":
        return False
    try:
        pid, pgid = int(record["pid"]), int(record["pgid"])
        expected = str(record.get("process_start_ticks", ""))
    except (KeyError, TypeError, ValueError):
        return False
    if expected and _proc_start_ticks(pid) != expected:
        return False
    try:
        (os.killpg if hasattr(os, "killpg") else os.kill)(pgid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    return True


def _signal_group(pgid: int, sig: signal.Signals) -> None:
    """Signal a POSIX process group, with a Windows single-process fallback."""
    if hasattr(os, "killpg"):
        os.killpg(pgid, sig)
    else:
        os.kill(pgid, sig)


def _result(request: RuntimeProcessRequest | None, status: AgentStatus, diagnostic: str, **values) -> RuntimeProcessResult:
    return RuntimeProcessResult(request.task_id if request else "", status, **values, diagnostic=diagnostic)


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
        try:
            process = subprocess.Popen([str(executable), *(_host_argument(value) for value in request.argv)], cwd=str(cwd), stdin=stdin or subprocess.DEVNULL,
                                       stdout=stdout or subprocess.DEVNULL, stderr=stderr or subprocess.DEVNULL,
                                       env=environment, shell=False, start_new_session=True)
        except OSError as error:
            return _result(request, AgentStatus.PROCESS_START_FAILED, str(error), started=False, finished=False)
        pid, pgid = process.pid, os.getpgid(process.pid) if hasattr(os, "getpgid") else process.pid
        if enable_task_control:
            control = _control_path(request.task_id, task_control_root)
            _atomic_json(control, {"schema_version": 1, "task_id": request.task_id, "pid": pid, "pgid": pgid,
                                   "process_start_ticks": _proc_start_ticks(pid), "state": "RUNNING", "started_at": started_at,
                                   "cwd": str(request.cwd), "executable": str(request.executable)})
        try:
            return_code = process.wait(timeout=request.timeout_seconds)
            status, diagnostic = AgentStatus.PROCESS_EXITED, ""
        except subprocess.TimeoutExpired:
            _signal_group(pgid, signal.SIGTERM)
            try: return_code = process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _signal_group(pgid, signal.SIGKILL); return_code = process.wait()
            status, diagnostic = AgentStatus.PROCESS_TIMEOUT, "Runtime task timeout exceeded."
        if control is not None:
            existing = _read_control(request.task_id, task_control_root)
            # A concurrent cancel operation may atomically update the record
            # between this waiter observing the process exit and its final
            # write. A signal exit from the owned session is terminal cancel
            # evidence unless this agent itself applied a request timeout.
            final_state = "CANCELLED" if ((existing and existing.get("state") == "CANCELLED") or (return_code is not None and return_code < 0 and status is not AgentStatus.PROCESS_TIMEOUT)) else "FINISHED"
            _atomic_json(control, {"schema_version": 1, "task_id": request.task_id, "pid": pid, "pgid": pgid,
                                   "process_start_ticks": _proc_start_ticks(pid), "state": final_state, "return_code": return_code,
                                   "started_at": started_at, "finished_at": timestamp(), "cwd": str(request.cwd),
                                   "executable": str(request.executable)})
        return RuntimeProcessResult(request.task_id, status, True, True, return_code, pid, pgid,
                                    started_at, timestamp(), time.monotonic() - timer, diagnostic)
    except (OSError, ProtocolError) as error:
        return _result(request, AgentStatus.INTERNAL_AGENT_ERROR, str(error), started=False, finished=False)
    finally:
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
    record = _read_control(_safe_task_id(task_id), task_control_root)
    if record is None: return {"schema_version": 1, "status": AgentStatus.TASK_NOT_FOUND.value, "task_id": task_id}
    state = AgentStatus.TASK_RUNNING if _record_alive(record) else (AgentStatus.TASK_CANCELLED if record.get("state") == "CANCELLED" else AgentStatus.TASK_FINISHED)
    return {"schema_version": 1, "status": state.value, "task_id": task_id, "record": record}


def cancel_task(task_id: str, *, grace_seconds: float = 2.0, task_control_root: str = DEFAULT_TASK_CONTROL_ROOT) -> dict[str, object]:
    task_id = _safe_task_id(task_id); record = _read_control(task_id, task_control_root)
    if record is None: return {"schema_version": 1, "status": AgentStatus.TASK_NOT_FOUND.value, "task_id": task_id}
    if not _record_alive(record):
        # A native Windows wrapper can finish between the caller's running
        # status observation and this check while its owned control record is
        # still RUNNING.  Preserve the user-requested lifecycle transition;
        # the executing agent will retain CANCELLED when it finalizes.
        if record.get("state") == "RUNNING":
            record = dict(record)
            record.update({"state": "CANCELLED", "cancelled_at": timestamp(), "cancellation_outcome": "TERMINATED"})
            _atomic_json(_control_path(task_id, task_control_root), record)
            return {"schema_version": 1, "status": AgentStatus.TASK_CANCELLED.value, "task_id": task_id, "outcome": "TERMINATED"}
        return {"schema_version": 1, "status": AgentStatus.TASK_FINISHED.value, "task_id": task_id}
    pgid = int(record["pgid"])
    try:
        _signal_group(pgid, signal.SIGTERM)
        deadline = time.monotonic() + max(0.0, float(grace_seconds))
        while time.monotonic() < deadline and _record_alive(record): time.sleep(0.03)
        outcome = "TERMINATED"
        if _record_alive(record):
            # Windows has no SIGKILL.  Its SIGTERM os.kill fallback is a
            # process-termination operation, so it provides the required
            # forced-cancellation step on that platform.
            _signal_group(pgid, getattr(signal, "SIGKILL", signal.SIGTERM)); outcome = "KILLED_AFTER_GRACE"
        record = dict(record); record.update({"state": "CANCELLED", "cancelled_at": timestamp(), "cancellation_outcome": outcome})
        _atomic_json(_control_path(task_id, task_control_root), record)
        return {"schema_version": 1, "status": AgentStatus.TASK_CANCELLED.value, "task_id": task_id, "outcome": outcome}
    except (OSError, ValueError) as error:
        if os.name == "nt":
            # The native wrapper may exit between the liveness check and the
            # forced termination call.  That is successful cancellation, not
            # a failed scientific task.
            record = dict(record)
            record.update({"state": "CANCELLED", "cancelled_at": timestamp(), "cancellation_outcome": "KILLED_AFTER_GRACE"})
            _atomic_json(_control_path(task_id, task_control_root), record)
            return {"schema_version": 1, "status": AgentStatus.TASK_CANCELLED.value, "task_id": task_id,
                    "outcome": "KILLED_AFTER_GRACE", "diagnostic": str(error)}
        return {"schema_version": 1, "status": "FAILED", "task_id": task_id, "diagnostic": str(error)}


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
