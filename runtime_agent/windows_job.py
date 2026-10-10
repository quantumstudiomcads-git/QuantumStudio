"""Windows Job Object ownership for managed runtime subprocess trees.

The initial process is created suspended, assigned to a named Job Object, and
only then resumed. Descendants inherit Job membership, including interpreter
launchers. Closing the launcher's last Job handle kills any remaining members.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import subprocess
import time
import uuid

_CREATE_NEW_PROCESS_GROUP = 0x00000200
_CREATE_SUSPENDED = 0x00000004
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION = 1
_JOB_OBJECT_TERMINATE = 0x0008
_JOB_OBJECT_QUERY = 0x0004
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_WAIT_OBJECT_0 = 0
_WAIT_TIMEOUT = 258
_STARTF_USESTDHANDLES = 0x00000100
_DUPLICATE_SAME_ACCESS = 0x00000002
_GENERIC_READ = 0x80000000
_GENERIC_WRITE = 0x40000000
_FILE_SHARE_READ = 1
_FILE_SHARE_WRITE = 2
_OPEN_EXISTING = 3
_FILE_ATTRIBUTE_NORMAL = 0x80
_PROC_THREAD_ATTRIBUTE_HANDLE_LIST = 0x00020002
_EXTENDED_STARTUPINFO_PRESENT = 0x00080000
_CTRL_BREAK_EVENT = 1
_CANCEL_EXIT_CODE = 0xD1F1
_STATUS_CONTROL_C_EXIT = 0xC000013A


class _FileTime(ctypes.Structure):
    _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]


class _BasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class _ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _BasicAccountingInformation(ctypes.Structure):
    _fields_ = [
        ("TotalUserTime", ctypes.c_longlong),
        ("TotalKernelTime", ctypes.c_longlong),
        ("ThisPeriodTotalUserTime", ctypes.c_longlong),
        ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
        ("TotalPageFaults", wintypes.DWORD),
        ("TotalProcesses", wintypes.DWORD),
        ("ActiveProcesses", wintypes.DWORD),
        ("TotalTerminatedProcesses", wintypes.DWORD),
    ]


class _SecurityAttributes(ctypes.Structure):
    _fields_ = [("nLength", wintypes.DWORD), ("lpSecurityDescriptor", ctypes.c_void_p),
                ("bInheritHandle", wintypes.BOOL)]


class _StartupInfo(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR),
                ("lpDesktop", wintypes.LPWSTR), ("lpTitle", wintypes.LPWSTR),
                ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
                ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD),
                ("dwXCountChars", wintypes.DWORD), ("dwYCountChars", wintypes.DWORD),
                ("dwFillAttribute", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD),
                ("lpReserved2", ctypes.POINTER(ctypes.c_ubyte)),
                ("hStdInput", wintypes.HANDLE), ("hStdOutput", wintypes.HANDLE),
                ("hStdError", wintypes.HANDLE)]


class _StartupInfoEx(ctypes.Structure):
    _fields_ = [("StartupInfo", _StartupInfo), ("lpAttributeList", ctypes.c_void_p)]


class _ProcessInformation(ctypes.Structure):
    _fields_ = [("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE),
                ("dwProcessId", wintypes.DWORD), ("dwThreadId", wintypes.DWORD)]


def _kernel32():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.OpenJobObjectW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.OpenJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                                 wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    kernel.QueryInformationJobObject.restype = wintypes.BOOL
    kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.TerminateJobObject.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.IsProcessInJob.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
    kernel.IsProcessInJob.restype = wintypes.BOOL
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, ctypes.POINTER(_FileTime), ctypes.POINTER(_FileTime),
                                       ctypes.POINTER(_FileTime), ctypes.POINTER(_FileTime)]
    kernel.GetProcessTimes.restype = wintypes.BOOL
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                   ctypes.POINTER(_SecurityAttributes), wintypes.DWORD,
                                   wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.DuplicateHandle.argtypes = [wintypes.HANDLE, wintypes.HANDLE, wintypes.HANDLE,
                                       ctypes.POINTER(wintypes.HANDLE), wintypes.DWORD,
                                       wintypes.BOOL, wintypes.DWORD]
    kernel.DuplicateHandle.restype = wintypes.BOOL
    kernel.CreateProcessW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p,
                                      ctypes.c_void_p, wintypes.BOOL, wintypes.DWORD, ctypes.c_void_p,
                                      wintypes.LPCWSTR, ctypes.POINTER(_StartupInfo),
                                      ctypes.POINTER(_ProcessInformation)]
    kernel.CreateProcessW.restype = wintypes.BOOL
    kernel.InitializeProcThreadAttributeList.argtypes = [ctypes.c_void_p, wintypes.DWORD,
                                                         wintypes.DWORD, ctypes.POINTER(ctypes.c_size_t)]
    kernel.InitializeProcThreadAttributeList.restype = wintypes.BOOL
    kernel.UpdateProcThreadAttribute.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.c_size_t,
                                                 ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p,
                                                 ctypes.POINTER(ctypes.c_size_t)]
    kernel.UpdateProcThreadAttribute.restype = wintypes.BOOL
    kernel.DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]
    kernel.DeleteProcThreadAttributeList.restype = None
    kernel.ResumeThread.argtypes = [wintypes.HANDLE]
    kernel.ResumeThread.restype = wintypes.DWORD
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.TerminateProcess.restype = wintypes.BOOL
    kernel.GenerateConsoleCtrlEvent.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.GenerateConsoleCtrlEvent.restype = wintypes.BOOL
    return kernel


def _winerror(operation: str) -> OSError:
    return ctypes.WinError(ctypes.get_last_error(), operation)


def process_creation_time(pid: int) -> int:
    kernel = _kernel32()
    handle = kernel.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        raise _winerror("OpenProcess")
    try:
        created, exited, kernel_time, user_time = _FileTime(), _FileTime(), _FileTime(), _FileTime()
        if not kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited),
                                      ctypes.byref(kernel_time), ctypes.byref(user_time)):
            raise _winerror("GetProcessTimes")
        return (created.high << 32) | created.low
    finally:
        kernel.CloseHandle(handle)


def process_exit_code(pid: int, creation_time: int) -> int | None:
    kernel = _kernel32()
    handle = kernel.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return None
    try:
        created, exited, kernel_time, user_time = _FileTime(), _FileTime(), _FileTime(), _FileTime()
        if not kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited),
                                      ctypes.byref(kernel_time), ctypes.byref(user_time)):
            return None
        if ((created.high << 32) | created.low) != int(creation_time):
            return None
        code = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259:
            return None
        return int(code.value)
    finally:
        kernel.CloseHandle(handle)


def process_has_exited(pid: int, creation_time: int) -> bool:
    """Check a specific process generation through a query-only handle."""
    return process_exit_state(pid, creation_time) is not False


def process_exit_state(pid: int, creation_time: int) -> bool | None:
    """Return exited/live for the exact process generation, or None if unverifiable."""
    kernel = _kernel32()
    handle = kernel.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return None
    try:
        created, exited, kernel_time, user_time = _FileTime(), _FileTime(), _FileTime(), _FileTime()
        if not kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited),
                                      ctypes.byref(kernel_time), ctypes.byref(user_time)):
            return None
        identity = (created.high << 32) | created.low
        if identity != int(creation_time):
            return None
        code = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
            return None
        return code.value != 259
    finally:
        kernel.CloseHandle(handle)


class SuspendedProcess:
    """Small Popen-compatible owner for documented CreateProcessW handles."""
    def __init__(self, executable: str, argv: tuple[str, ...], cwd: str,
                 environment: dict[str, str], stdin, stdout, stderr, creationflags: int):
        self.args = [executable, *argv]
        self.returncode = None
        self._kernel = _kernel32()
        self._handle = None
        self._thread_handle = None
        self.pid = 0
        duplicated: list[int] = []
        null_handles: list[int] = []
        try:
            streams = []
            for stream, access in ((stdin, _GENERIC_READ), (stdout, _GENERIC_WRITE), (stderr, _GENERIC_WRITE)):
                if stream is __import__("subprocess").DEVNULL:
                    security = _SecurityAttributes(ctypes.sizeof(_SecurityAttributes), None, True)
                    handle = self._kernel.CreateFileW("NUL", access, _FILE_SHARE_READ | _FILE_SHARE_WRITE,
                                                      ctypes.byref(security), _OPEN_EXISTING,
                                                      _FILE_ATTRIBUTE_NORMAL, None)
                    if handle == wintypes.HANDLE(-1).value:
                        raise _winerror("CreateFileW(NUL)")
                    null_handles.append(int(handle))
                    streams.append(int(handle))
                else:
                    source = int(__import__("msvcrt").get_osfhandle(stream.fileno()))
                    duplicate = wintypes.HANDLE()
                    current = self._kernel.GetCurrentProcess()
                    if not self._kernel.DuplicateHandle(current, source, current, ctypes.byref(duplicate),
                                                        0, True, _DUPLICATE_SAME_ACCESS):
                        raise _winerror("DuplicateHandle(stdio)")
                    duplicated.append(int(duplicate.value))
                    streams.append(int(duplicate.value))
            startup = _StartupInfo()
            startup.cb = ctypes.sizeof(startup)
            startup.dwFlags = _STARTF_USESTDHANDLES
            startup.hStdInput, startup.hStdOutput, startup.hStdError = streams
            info = _ProcessInformation()
            command = __import__("subprocess").list2cmdline(self.args)
            command_buffer = ctypes.create_unicode_buffer(command)
            environment_items = sorted((str(k) + "=" + str(v) for k, v in environment.items()), key=str.upper)
            environment_block = ctypes.create_unicode_buffer("\0".join(environment_items) + "\0\0")
            attribute_size = ctypes.c_size_t()
            self._kernel.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(attribute_size))
            attribute_buffer = ctypes.create_string_buffer(attribute_size.value)
            attribute_list = ctypes.cast(attribute_buffer, ctypes.c_void_p)
            if not self._kernel.InitializeProcThreadAttributeList(attribute_list, 1, 0, ctypes.byref(attribute_size)):
                raise _winerror("InitializeProcThreadAttributeList")
            handles = (wintypes.HANDLE * len(streams))(*(wintypes.HANDLE(item) for item in streams))
            try:
                if not self._kernel.UpdateProcThreadAttribute(attribute_list, 0,
                        _PROC_THREAD_ATTRIBUTE_HANDLE_LIST, ctypes.byref(handles), ctypes.sizeof(handles), None, None):
                    raise _winerror("UpdateProcThreadAttribute(handle list)")
                startup_ex = _StartupInfoEx(startup, attribute_list)
                startup_ex.StartupInfo.cb = ctypes.sizeof(startup_ex)
                startup_pointer = ctypes.cast(ctypes.byref(startup_ex), ctypes.POINTER(_StartupInfo))
                if not self._kernel.CreateProcessW(executable, command_buffer, None, None, True,
                                                   creationflags | _EXTENDED_STARTUPINFO_PRESENT | 0x00000400,
                                                   ctypes.cast(environment_block, ctypes.c_void_p),
                                                   cwd, startup_pointer, ctypes.byref(info)):
                    raise _winerror("CreateProcessW")
            finally:
                self._kernel.DeleteProcThreadAttributeList(attribute_list)
            self._handle = int(info.hProcess)
            self._thread_handle = int(info.hThread)
            self.pid = int(info.dwProcessId)
        except BaseException:
            self.close()
            raise
        finally:
            for handle in duplicated + null_handles:
                self._kernel.CloseHandle(handle)

    def poll(self):
        if self.returncode is not None:
            return self.returncode
        code = wintypes.DWORD()
        if not self._kernel.GetExitCodeProcess(self._handle, ctypes.byref(code)):
            raise _winerror("GetExitCodeProcess")
        if code.value == 259:  # STILL_ACTIVE
            return None
        self.returncode = int(code.value)
        return self.returncode

    def wait(self, timeout: float | None = None):
        started = time.monotonic()
        while True:
            code = self.poll()
            if code is not None:
                return code
            remaining = None if timeout is None else timeout - (time.monotonic() - started)
            if remaining is not None and remaining <= 0:
                raise __import__("subprocess").TimeoutExpired(self.args, timeout)
            time.sleep(0.02 if remaining is None else min(0.02, remaining))

    def terminate(self):
        if self.poll() is None and not self._kernel.TerminateProcess(self._handle, 1):
            raise _winerror("TerminateProcess")

    kill = terminate

    def close(self):
        for field in ("_thread_handle", "_handle"):
            handle = getattr(self, field, None)
            if handle:
                self._kernel.CloseHandle(handle)
                setattr(self, field, None)


class WindowsJob:
    """A verified, named Job Object that owns a managed process tree."""

    def __init__(self, name: str | None = None, *, create: bool = True):
        self.name = name or ("Local\\QSRuntime-" + uuid.uuid4().hex)
        self._kernel = _kernel32()
        access = _JOB_OBJECT_QUERY | _JOB_OBJECT_TERMINATE
        if create:
            ctypes.set_last_error(0)
            self.handle = self._kernel.CreateJobObjectW(None, self.name)
            if not self.handle:
                raise _winerror("CreateJobObjectW")
            if ctypes.get_last_error() == 183:
                self.close()
                raise FileExistsError("Managed Job Object name already exists.")
            info = _ExtendedLimitInformation()
            info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not self._kernel.SetInformationJobObject(
                    self.handle, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                    ctypes.byref(info), ctypes.sizeof(info)):
                error = _winerror("SetInformationJobObject")
                self.close()
                raise error
        else:
            self.handle = self._kernel.OpenJobObjectW(access, False, self.name)
            if not self.handle:
                raise _winerror("OpenJobObjectW")

    def assign_suspended_process(self, process: subprocess.Popen) -> int:
        if os.name != "nt" or process.poll() is not None:
            raise RuntimeError("Managed Windows process is not live and suspended.")
        handle = getattr(process, "_handle", None)
        if handle is None or not self._kernel.AssignProcessToJobObject(self.handle, int(handle)):
            raise _winerror("AssignProcessToJobObject")
        creation = process_creation_time(process.pid)
        if not self.is_process_member(process.pid, creation):
            raise RuntimeError("Managed process identity was not verified in its Job Object.")
        return creation

    def resume_process(self, process: SuspendedProcess, creation_time: int) -> None:
        if not self.is_process_member(process.pid, creation_time):
            raise RuntimeError("Managed suspended process identity changed before resume.")
        thread = process._thread_handle
        if not thread:
            raise RuntimeError("Managed primary thread handle is unavailable.")
        previous_count = self._kernel.ResumeThread(thread)
        if previous_count == 0xFFFFFFFF:
            raise _winerror("ResumeThread")
        if previous_count != 1:
            raise RuntimeError("Managed primary thread was not in its expected suspended state.")
        self._kernel.CloseHandle(thread)
        process._thread_handle = None

    def is_process_member(self, pid: int, creation_time: int) -> bool:
        try:
            if process_creation_time(pid) != int(creation_time):
                return False
        except OSError:
            return False
        kernel = self._kernel
        process = kernel.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not process:
            return False
        try:
            member = wintypes.BOOL()
            if not kernel.IsProcessInJob(process, self.handle, ctypes.byref(member)):
                return False
            return bool(member.value)
        finally:
            kernel.CloseHandle(process)

    def contains_process(self, pid: int) -> bool:
        process = self._kernel.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not process:
            return False
        try:
            member = wintypes.BOOL()
            return bool(self._kernel.IsProcessInJob(process, self.handle, ctypes.byref(member)) and member.value)
        finally:
            self._kernel.CloseHandle(process)

    def active_processes(self) -> int:
        info = _BasicAccountingInformation()
        if not self._kernel.QueryInformationJobObject(
                self.handle, _JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION,
                ctypes.byref(info), ctypes.sizeof(info), None):
            raise _winerror("QueryInformationJobObject")
        return int(info.ActiveProcesses)

    def send_ctrl_break(self, pid: int, creation_time: int, *, current_pid: int) -> bool:
        """Send only to the verified group created with the process boundary."""
        if pid <= 1 or pid == current_pid or not self.is_process_member(pid, creation_time):
            return False
        # CREATE_NEW_PROCESS_GROUP makes the process PID the group ID. The
        # group target is never zero and cannot be the caller's new group.
        if not self.active_processes():
            return False
        if not self._kernel.GenerateConsoleCtrlEvent(_CTRL_BREAK_EVENT, int(pid)):
            return False
        return True

    def terminate(self, exit_code: int = _CANCEL_EXIT_CODE) -> bool:
        if not self.active_processes():
            return False
        if not self._kernel.TerminateJobObject(self.handle, int(exit_code)):
            raise _winerror("TerminateJobObject")
        return True

    def wait_empty(self, timeout: float) -> bool:
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            if self.active_processes() == 0:
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            time.sleep(min(0.02, remaining))

    def close(self) -> None:
        handle = getattr(self, "handle", None)
        if handle:
            self._kernel.CloseHandle(handle)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()


def windows_creation_flags() -> int:
    return _CREATE_NEW_PROCESS_GROUP | _CREATE_SUSPENDED


def windows_cancel_exit_codes() -> frozenset[int]:
    # Keep the documented per-phase Job termination codes classified as
    # cancellation if the execution thread wins the task-record write race.
    return frozenset({_CANCEL_EXIT_CODE, 0xD1F2, 0xD1F3, _STATUS_CONTROL_C_EXIT})


def windows_graceful_exit_codes() -> frozenset[int]:
    return frozenset({_STATUS_CONTROL_C_EXIT})
