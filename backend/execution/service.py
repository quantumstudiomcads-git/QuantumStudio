"""Qt-free asynchronous ownership for an active local workflow execution."""
from __future__ import annotations

from dataclasses import dataclass, field
import threading

from .local import LocalExecutionManager


@dataclass
class LocalExecutionHandle:
    manager: LocalExecutionManager
    thread: threading.Thread
    result: object | None = None
    error: Exception | None = None
    done: threading.Event = field(default_factory=threading.Event)

    def cancel(self) -> None:
        self.manager.cancel()


class LocalExecutionService:
    """Owns one session-local execution independently from a Qt widget callback."""

    def __init__(self, manager: LocalExecutionManager):
        self.manager = manager
        self._handle: LocalExecutionHandle | None = None

    @property
    def active(self) -> LocalExecutionHandle | None:
        return self._handle if self._handle and not self._handle.done.is_set() else None

    def start(self, workflow) -> LocalExecutionHandle:
        if self.active is not None:
            raise RuntimeError("A local workflow is already running.")
        holder: dict[str, LocalExecutionHandle] = {}

        def run() -> None:
            handle = holder["handle"]
            try:
                handle.result = self.manager.execute(workflow)
            except Exception as error:  # converted to concise UI text by the caller
                handle.error = error
            finally:
                handle.done.set()

        thread = threading.Thread(target=run, name="quantum-studio-local-execution", daemon=True)
        handle = LocalExecutionHandle(self.manager, thread)
        holder["handle"] = handle
        self._handle = handle
        thread.start()
        return handle
