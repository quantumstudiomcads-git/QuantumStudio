"""Qt-free Quantum ESPRESSO derived input models and domain errors."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class QEInputGenerationError(RuntimeError):
    """Base error for QE input translation and export failures."""


class MissingPseudopotentialError(QEInputGenerationError):
    """Raised when a structure species has no explicit pseudo assignment."""


class InvalidQEParameterError(QEInputGenerationError):
    """Raised when an engine-neutral value cannot be translated safely to QE."""


class UnsupportedQECalculationError(QEInputGenerationError):
    """Raised for a compiler-supported calculation lacking a sound C4 writer."""


class QEOutputExistsError(QEInputGenerationError):
    """Raised instead of silently overwriting a generated request workspace."""


@dataclass(frozen=True)
class PseudopotentialSelection:
    """Logical per-element pseudo selection; runtime location is separate."""

    element: str
    filename: str
    source: str | None = None
    family: str | None = None
    functional: str | None = None
    relativistic: str | None = None
    sha256: str | None = None
    library_id: str | None = None
    library_version: str | None = None
    pseudo_type: str | None = None
    collection: str | None = None
    z_valence: float | None = None
    recommended_ecutwfc_ry: float | None = None
    recommended_ecutrho_ry: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.element, str) or not self.element.strip():
            raise InvalidQEParameterError("Pseudopotential element must be non-empty.")
        if not isinstance(self.filename, str) or not self.filename.strip():
            raise InvalidQEParameterError(f"Pseudopotential filename for {self.element!r} must be non-empty.")

    @classmethod
    def from_value(cls, element: str, value: object) -> "PseudopotentialSelection":
        if isinstance(value, cls):
            if value.element != element:
                raise InvalidQEParameterError(
                    f"Pseudopotential assignment key {element!r} contradicts element {value.element!r}."
                )
            return value
        if isinstance(value, str):
            return cls(element=element, filename=value)
        if isinstance(value, dict):
            if "filename" not in value:
                raise InvalidQEParameterError(
                    f"Pseudopotential assignment for {element!r} requires 'filename'."
                )
            return cls(
                element=str(value.get("element", element)), filename=value["filename"],
                source=value.get("source"), family=value.get("family"),
                functional=value.get("functional", value.get("xc_functional")), relativistic=value.get("relativistic"),
                sha256=value.get("sha256"), library_id=value.get("library_id"), library_version=value.get("library_version"), pseudo_type=value.get("pseudo_type"), collection=value.get("collection"), z_valence=value.get("z_valence"), recommended_ecutwfc_ry=value.get("recommended_ecutwfc_ry"), recommended_ecutrho_ry=value.get("recommended_ecutrho_ry"),
            )
        raise InvalidQEParameterError(
            f"Pseudopotential assignment for {element!r} must be a filename or mapping."
        )

    def provenance(self) -> dict[str, object]:
        return {key: value for key, value in {"element": self.element, "filename": self.filename, "source": self.source, "library_id": self.library_id, "library_version": self.library_version, "sha256": self.sha256, "xc_functional": self.functional, "pseudo_type": self.pseudo_type, "relativity": self.relativistic, "collection": self.collection, "z_valence": self.z_valence, "recommended_ecutwfc_ry": self.recommended_ecutwfc_ry, "recommended_ecutrho_ry": self.recommended_ecutrho_ry}.items() if value is not None}

@dataclass(frozen=True)
class QEWorkflowContext:
    """Stable request-level runtime state shared by dependent QE tasks."""

    request_id: str
    prefix: str
    outdir: str
    pseudo_dir: str


@dataclass(frozen=True)
class QETaskInput:
    """Derived, non-persistent QE input specification for one planned task."""

    task_id: str
    calculation_id: str
    executable: str
    input_filename: str
    output_filename: str
    working_directory: str
    input_text: str
    depends_on_task_ids: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class QEGeneration:
    """In-memory QE export that may be previewed or explicitly written."""

    engine_id: str
    context: QEWorkflowContext
    tasks: tuple[QETaskInput, ...]
    manifest: dict[str, Any]

    def task_for_calculation(self, calculation_id: str) -> QETaskInput:
        for task in self.tasks:
            if task.calculation_id == calculation_id:
                return task
        raise KeyError(f"No QE task for calculation: {calculation_id}")
