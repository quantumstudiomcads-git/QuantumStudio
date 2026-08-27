"""Qt-free reconciliation between the discoverability catalog and executable registry."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from backend.calculations.registry import CalculationRegistry
from frontend.calculations.catalog import CalculationInfo


class ExecutionSupport(str, Enum):
    IMPLEMENTED = "implemented"
    PLANNED = "planned"
    PARTIAL = "partial"
    EXTERNAL_BACKEND_REQUIRED = "external_backend_required"
    UNSUPPORTED = "unsupported"
    UNAVAILABLE = "unavailable"


class CatalogReconciliationError(RuntimeError):
    """Raised when catalog metadata makes executable support ambiguous."""


@dataclass(frozen=True)
class CalculationDescriptor:
    info: CalculationInfo
    execution_support: ExecutionSupport
    backend_supported: bool
    dependencies: tuple[str, ...] = ()

    @property
    def id(self) -> str:
        return self.info.id

    @property
    def status_label(self) -> str:
        return {
            ExecutionSupport.IMPLEMENTED: "Ready",
            ExecutionSupport.PLANNED: "Planned",
            ExecutionSupport.PARTIAL: "Partial",
            ExecutionSupport.EXTERNAL_BACKEND_REQUIRED: "External backend required",
            ExecutionSupport.UNSUPPORTED: "Unsupported",
            ExecutionSupport.UNAVAILABLE: "Unavailable",
        }[self.execution_support]


@dataclass(frozen=True)
class CatalogReconciliationReport:
    frontend_count: int
    backend_count: int
    descriptors: tuple[CalculationDescriptor, ...]
    frontend_only_ids: tuple[str, ...]
    backend_only_ids: tuple[str, ...]
    invalid_mappings: tuple[str, ...]

    @property
    def implemented_ids(self) -> tuple[str, ...]:
        return tuple(item.id for item in self.descriptors if item.execution_support is ExecutionSupport.IMPLEMENTED)

    @property
    def planned_ids(self) -> tuple[str, ...]:
        return tuple(item.id for item in self.descriptors if item.execution_support is ExecutionSupport.PLANNED)


def reconcile_catalog(
    catalog: Iterable[CalculationInfo], registry: CalculationRegistry, *, strict: bool = True,
) -> CatalogReconciliationReport:
    """Return the formal catalog/registry mapping without involving Qt widgets."""
    entries = tuple(catalog)
    backend = tuple(registry.all())
    errors: list[str] = []
    by_id: dict[str, CalculationInfo] = {}
    for entry in entries:
        if entry.id in by_id:
            errors.append(f"Duplicate frontend calculation ID: {entry.id}")
        else:
            by_id[entry.id] = entry

    backend_ids = {definition.id for definition in backend}
    descriptors: list[CalculationDescriptor] = []
    for entry in entries:
        raw_status = str(entry.status).lower()
        has_backend = entry.id in backend_ids
        if raw_status == "ready":
            support = ExecutionSupport.IMPLEMENTED if has_backend else ExecutionSupport.UNAVAILABLE
            if not has_backend:
                errors.append(f"Frontend implemented calculation '{entry.id}' has no backend definition.")
        elif raw_status == "planned":
            support = ExecutionSupport.PLANNED
            if has_backend:
                errors.append(f"Backend calculation '{entry.id}' is marked planned in the frontend catalog.")
        elif raw_status == "partial":
            support = ExecutionSupport.PARTIAL
        elif raw_status == "external_backend_required":
            support = ExecutionSupport.EXTERNAL_BACKEND_REQUIRED
        elif raw_status == "unsupported":
            support = ExecutionSupport.UNSUPPORTED
        else:
            support = ExecutionSupport.UNAVAILABLE
            errors.append(f"Frontend calculation '{entry.id}' has unknown support status '{entry.status}'.")
        dependencies = tuple(registry.get(entry.id).requires) if has_backend else ()
        descriptors.append(CalculationDescriptor(entry, support, support is ExecutionSupport.IMPLEMENTED, dependencies))

    report = CatalogReconciliationReport(
        frontend_count=len(entries), backend_count=len(backend), descriptors=tuple(descriptors),
        frontend_only_ids=tuple(sorted(set(by_id) - backend_ids)),
        backend_only_ids=tuple(sorted(backend_ids - set(by_id))),
        invalid_mappings=tuple(errors),
    )
    if strict and report.invalid_mappings:
        raise CatalogReconciliationError("Catalog/registry reconciliation failed: " + "; ".join(report.invalid_mappings))
    return report
