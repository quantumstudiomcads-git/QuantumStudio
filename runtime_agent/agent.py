"""Deployable stdlib-only qs-runtime-agent implementation."""
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import time
from typing import Iterable

from .protocol import AGENT_VERSION, AgentStatus, ProtocolError, RuntimeAgentHealth, RuntimePath, RuntimeProcessRequest, RuntimeProcessResult, timestamp

DEFAULT_EXECUTABLE_ROOTS = ("/opt/quantumstudio/engines", "/opt/quantumstudio/runtime/bin")
DEFAULT_WORKING_ROOTS = ("/var/lib/quantumstudio/workflows", "/var/lib/quantumstudio/staging")


def _under(path: RuntimePath, roots: Iterable[str]) -> bool:
    candidate = PurePosixPath(str(path))
    for root in roots:
        trusted = PurePosixPath(str(RuntimePath(root)))
        if candidate == trusted or trusted in candidate.parents:
            return True
    return False


def _real_under(path: Path, roots: Iterable[str]) -> bool:
    """Resolve inside the Linux runtime before enforcing a trusted root.

    The host must not resolve runtime paths, but the agent can detect a
    symlink escape in its own filesystem namespace before it opens/executes.
    """
    candidate = path.resolve(strict=False)
    for root in roots:
        trusted = Path(root).resolve(strict=False)
        if candidate == trusted or trusted in candidate.parents:
            return True
    return False


def _result(request: RuntimeProcessRequest | None, status: AgentStatus, diagnostic: str, **values) -> RuntimeProcessResult:
    return RuntimeProcessResult(request.task_id if request else "", status, **values, diagnostic=diagnostic)


def execute_request(request: RuntimeProcessRequest, *, trusted_executable_roots=DEFAULT_EXECUTABLE_ROOTS,
                    trusted_working_roots=DEFAULT_WORKING_ROOTS) -> RuntimeProcessResult:
    if not _under(request.executable, trusted_executable_roots):
        return _result(request, AgentStatus.EXECUTABLE_REJECTED, "Executable is outside trusted runtime roots.", started=False, finished=False)
    if not _under(request.cwd, trusted_working_roots):
        return _result(request, AgentStatus.CWD_REJECTED, "Working directory is outside trusted runtime roots.", started=False, finished=False)
    executable, cwd = Path(str(request.executable)), Path(str(request.cwd))
    if not executable.is_file() or not os.access(executable, os.X_OK) or not _real_under(executable, trusted_executable_roots):
        return _result(request, AgentStatus.EXECUTABLE_REJECTED, "Trusted executable is missing, unexecutable, or escapes its trusted root.", started=False, finished=False)
    if not cwd.is_dir() or not _real_under(cwd, trusted_working_roots):
        return _result(request, AgentStatus.CWD_REJECTED, "Trusted runtime working directory is missing or escapes its root.", started=False, finished=False)
    stdin = stdout = stderr = None
    try:
        if request.stdin_path:
            stdin_target = Path(str(request.stdin_path))
            if not _under(request.stdin_path, trusted_working_roots) or not stdin_target.is_file() or not _real_under(stdin_target, trusted_working_roots):
                return _result(request, AgentStatus.STDIN_MISSING, "Runtime-local stdin file is missing or untrusted.", started=False, finished=False)
            stdin = stdin_target.open("rb")
        if request.stdout_path:
            stdout_target = Path(str(request.stdout_path))
            if not _under(request.stdout_path, trusted_working_roots) or not _real_under(stdout_target, trusted_working_roots):
                return _result(request, AgentStatus.CWD_REJECTED, "stdout destination is outside trusted runtime roots.", started=False, finished=False)
            stdout_target.parent.mkdir(parents=True, exist_ok=True)
            stdout = stdout_target.open("wb")
        if request.stderr_path:
            stderr_target = Path(str(request.stderr_path))
            if not _under(request.stderr_path, trusted_working_roots) or not _real_under(stderr_target, trusted_working_roots):
                return _result(request, AgentStatus.CWD_REJECTED, "stderr destination is outside trusted runtime roots.", started=False, finished=False)
            stderr_target.parent.mkdir(parents=True, exist_ok=True)
            stderr = stderr_target.open("wb")
        started_at, timer = timestamp(), time.monotonic()
        environment = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", **request.environment}
        try:
            process = subprocess.Popen([str(executable), *request.argv], cwd=str(cwd), stdin=stdin or subprocess.DEVNULL,
                                       stdout=stdout or subprocess.DEVNULL, stderr=stderr or subprocess.DEVNULL,
                                       env=environment, shell=False, start_new_session=True)
        except OSError as error:
            return _result(request, AgentStatus.PROCESS_START_FAILED, str(error), started=False, finished=False)
        pid, pgid = process.pid, os.getpgid(process.pid)
        try:
            return_code = process.wait(timeout=request.timeout_seconds)
            status, diagnostic = AgentStatus.PROCESS_EXITED, ""
        except subprocess.TimeoutExpired:
            # Cancellation protocol is W5; this bounded explicit task policy only
            # prevents an agent subprocess from becoming detached in W4 tests.
            process.terminate()
            return_code = process.wait(timeout=5)
            status, diagnostic = AgentStatus.PROCESS_TIMEOUT, "Runtime task timeout exceeded."
        return RuntimeProcessResult(request.task_id, status, True, True, return_code, pid, pgid,
                                    started_at, timestamp(), time.monotonic() - timer, diagnostic)
    except OSError as error:
        return _result(request, AgentStatus.INTERNAL_AGENT_ERROR, str(error), started=False, finished=False)
    finally:
        for stream in (stdin, stdout, stderr):
            if stream is not None:
                stream.close()


def run_stdio() -> int:
    request = None
    try:
        request = RuntimeProcessRequest.from_json(sys.stdin.buffer.read())
        result = execute_request(request)
    except ProtocolError as error:
        result = RuntimeProcessResult(request.task_id if request else "", AgentStatus.UNSUPPORTED_SCHEMA if error.code == "UNSUPPORTED_SCHEMA" else AgentStatus.INVALID_REQUEST,
                                      False, False, diagnostic=str(error))
    except Exception:
        result = RuntimeProcessResult(request.task_id if request else "", AgentStatus.INTERNAL_AGENT_ERROR, False, False,
                                      diagnostic="Unexpected runtime-agent internal error.")
    sys.stdout.buffer.write(result.to_json())
    return 0


def main(argv: list[str] | None = None) -> int:
    command = (argv or sys.argv[1:])
    if command == ["health"] or command == ["version"]:
        sys.stdout.buffer.write(RuntimeAgentHealth(True, AGENT_VERSION, 1).to_json())
        return 0
    if command == ["run"]:
        return run_stdio()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
