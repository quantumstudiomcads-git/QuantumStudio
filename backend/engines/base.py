"""Engine-adapter boundary for derived execution-plan translations."""

from __future__ import annotations

from abc import ABC, abstractmethod


class EngineAdapter(ABC):
    """Translate an engine-agnostic ExecutionPlan without executing it."""

    engine_id: str

    @abstractmethod
    def compile_plan(self, plan):
        """Return engine-specific, in-memory task inputs for ``plan``."""

    @abstractmethod
    def write_plan(self, plan, output_root, *, overwrite: bool = False):
        """Write a validated derived export. Implementations never execute it."""
