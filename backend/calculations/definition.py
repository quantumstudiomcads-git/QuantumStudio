"""Engine-agnostic executable calculation definition."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CalculationDefinition:
    """One backend-supported calculation and its direct calculation prerequisites.

    ``requires`` contains stable backend calculation IDs.  The captured request
    structure is the implicit root input and is therefore not represented as a
    synthetic calculation node.
    """

    id: str
    name: str
    category: str
    description: str = ""
    requires: tuple[str, ...] = field(default_factory=tuple)
    produces: tuple[str, ...] = field(default_factory=tuple)
    workflow: str | None = None
    engine: str | None = None
    parameters: tuple[str, ...] = field(default_factory=tuple)
    tags: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    # Per-target requirements for a shared direct prerequisite.  These are
    # workflow defaults, not user overrides; conflicts are compiler errors.
    dependency_parameters: dict[str, dict[str, Any]] = field(default_factory=dict)
