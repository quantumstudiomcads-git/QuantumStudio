"""Qt-free, non-persistent undo/redo history for Device domain state."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceStateCommand:
    label: str
    before: dict
    after: dict


class DeviceHistory:
    """Snapshot history deliberately separate from Builder's Structure history."""

    def __init__(self):
        self._undo_stack: list[DeviceStateCommand] = []
        self._redo_stack: list[DeviceStateCommand] = []

    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def record(self, label: str, before: dict, after: dict) -> bool:
        if before == after:
            return False
        self._undo_stack.append(DeviceStateCommand(str(label), deepcopy(before), deepcopy(after)))
        self._redo_stack.clear()
        return True

    def undo(self) -> dict | None:
        if not self._undo_stack:
            return None
        command = self._undo_stack.pop()
        self._redo_stack.append(command)
        return deepcopy(command.before)

    def redo(self) -> dict | None:
        if not self._redo_stack:
            return None
        command = self._redo_stack.pop()
        self._undo_stack.append(command)
        return deepcopy(command.after)

    def clear(self):
        self._undo_stack.clear()
        self._redo_stack.clear()
