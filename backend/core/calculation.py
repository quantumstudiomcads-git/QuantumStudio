"""
Quantum Studio Calculation Object.

This object wraps a calculation manifest and provides a stable internal
interface for workflows, engines, executors, and parsers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.core.manifest import create_manifest


@dataclass
class Calculation:
    """
    Universal representation of a Quantum Studio calculation.
    """

    workflow: str

    structure: dict[str, Any]

    parameters: dict[str, Any] = field(
        default_factory=dict
    )

    execution_target: str = "local"

    dependencies: list[str] = field(
        default_factory=list
    )

    manifest: dict[str, Any] = field(
        init=False
    )

    def __post_init__(self) -> None:

        self.manifest = create_manifest(
            workflow=self.workflow,
            structure=self.structure,
            parameters=self.parameters,
            execution_target=self.execution_target,
            dependencies=self.dependencies,
        )

    @property
    def id(self) -> str:
        return self.manifest["calculation"]["id"]

    @property
    def status(self) -> str:
        return self.manifest["calculation"]["status"]

    def set_status(
        self,
        status: str,
    ) -> None:

        self.manifest[
            "calculation"
        ]["status"] = status

    def set_engine(
        self,
        name: str,
        version: str,
    ) -> None:

        self.manifest["engine"] = {
            "resolved": name,
            "version": version,
        }
