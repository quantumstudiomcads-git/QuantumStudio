"""Deterministic registry for executable calculation definitions."""

from __future__ import annotations

from dataclasses import dataclass

from backend.calculations.definition import CalculationDefinition


class RegistryValidationError(RuntimeError):
    """Raised when executable calculation definitions cannot form a valid DAG."""


@dataclass(frozen=True)
class RegistryValidationReport:
    calculation_ids: tuple[str, ...]
    dependencies: tuple[tuple[str, tuple[str, ...]], ...]


class CalculationRegistry:
    """Insertion-ordered registry; order is an explicit deterministic tie-break."""

    def __init__(self):
        self._calculations: dict[str, CalculationDefinition] = {}

    def register(self, calculation: CalculationDefinition) -> None:
        if not isinstance(calculation, CalculationDefinition):
            raise TypeError("Only CalculationDefinition instances can be registered.")
        if not isinstance(calculation.id, str) or not calculation.id.strip():
            raise ValueError("Calculation definitions require a non-empty stable ID.")
        if calculation.id in self._calculations:
            raise ValueError(f"Calculation already registered: {calculation.id}")
        self._calculations[calculation.id] = calculation

    def get(self, calculation_id: str) -> CalculationDefinition:
        try:
            return self._calculations[calculation_id]
        except KeyError as error:
            raise KeyError(f"Unknown calculation: {calculation_id}") from error

    def exists(self, calculation_id: str) -> bool:
        return calculation_id in self._calculations

    def all(self) -> list[CalculationDefinition]:
        return list(self._calculations.values())

    def index_of(self, calculation_id: str) -> int:
        try:
            return tuple(self._calculations).index(calculation_id)
        except ValueError as error:
            raise KeyError(f"Unknown calculation: {calculation_id}") from error

    def categories(self) -> list[str]:
        return sorted({calculation.category for calculation in self._calculations.values()})

    def by_category(self, category: str) -> list[CalculationDefinition]:
        return [calculation for calculation in self._calculations.values() if calculation.category == category]

    def by_tag(self, tag: str) -> list[CalculationDefinition]:
        return [calculation for calculation in self._calculations.values() if tag in calculation.tags]

    def validate(self) -> RegistryValidationReport:
        """Validate IDs, direct dependencies, schemas, and dependency cycles.

        The registry deliberately accepts only direct calculation-ID dependencies.
        Artifact names remain descriptive ``produces`` metadata, avoiding an
        ambiguous second dependency source for the planner.
        """
        order = tuple(self._calculations)
        for calculation_id, definition in self._calculations.items():
            if definition.id != calculation_id:
                raise RegistryValidationError(
                    f"Registry key '{calculation_id}' does not match definition ID '{definition.id}'."
                )
            for dependency in definition.requires:
                if not isinstance(dependency, str) or not dependency.strip():
                    raise RegistryValidationError(
                        f"Calculation '{calculation_id}' has an invalid dependency ID."
                    )
                if dependency == calculation_id:
                    raise RegistryValidationError(
                        f"Calculation '{calculation_id}' cannot depend on itself."
                    )
                if dependency not in self._calculations:
                    raise RegistryValidationError(
                        f"Calculation '{calculation_id}' requires unknown calculation '{dependency}'."
                    )
            names = tuple(definition.parameters)
            if len(set(names)) != len(names) or any(not isinstance(name, str) or not name.strip() for name in names):
                raise RegistryValidationError(
                    f"Calculation '{calculation_id}' has an invalid parameter schema reference."
                )
            for dependency, values in definition.dependency_parameters.items():
                if dependency not in definition.requires:
                    raise RegistryValidationError(
                        f"Calculation '{calculation_id}' configures non-required dependency '{dependency}'."
                    )
                if not isinstance(values, dict) or any(not isinstance(key, str) or not key for key in values):
                    raise RegistryValidationError(
                        f"Calculation '{calculation_id}' has invalid dependency parameters for '{dependency}'."
                    )

        visited: set[str] = set()
        active: list[str] = []

        def visit(calculation_id: str) -> None:
            if calculation_id in active:
                start = active.index(calculation_id)
                cycle = active[start:] + [calculation_id]
                raise RegistryValidationError("Dependency cycle detected: " + " -> ".join(cycle))
            if calculation_id in visited:
                return
            active.append(calculation_id)
            for dependency in self._calculations[calculation_id].requires:
                visit(dependency)
            active.pop()
            visited.add(calculation_id)

        for calculation_id in order:
            visit(calculation_id)
        return RegistryValidationReport(
            calculation_ids=order,
            dependencies=tuple(
                (calculation_id, tuple(self._calculations[calculation_id].requires))
                for calculation_id in order
            ),
        )


registry = CalculationRegistry()
