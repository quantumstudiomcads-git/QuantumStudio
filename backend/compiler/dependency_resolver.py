"""Deterministic direct-ID dependency DAG resolver for calculation planning."""

from __future__ import annotations

from dataclasses import dataclass

from backend.calculations.registry import CalculationRegistry, RegistryValidationError, registry


class DependencyResolutionError(RuntimeError):
    """Raised when a selected calculation cannot be expanded into a valid DAG."""


@dataclass(frozen=True)
class ResolvedDependencyGraph:
    selected_calculations: tuple[str, ...]
    ordered_calculations: tuple[str, ...]
    dependencies: tuple[tuple[str, tuple[str, ...]], ...]
    levels: tuple[tuple[str, int], ...]

    def dependencies_for(self, calculation_id: str) -> tuple[str, ...]:
        return dict(self.dependencies).get(calculation_id, ())

    def level_for(self, calculation_id: str) -> int:
        return dict(self.levels)[calculation_id]


class DependencyResolver:
    """Build one shared-prerequisite DAG from selected executable calculations."""

    def __init__(self, selected_calculations: list[str], registry_instance: CalculationRegistry | None = None):
        self.selected_calculations = tuple(str(item) for item in selected_calculations)
        self.registry = registry if registry_instance is None else registry_instance

    def resolve(self) -> list[str]:
        return list(self.build().ordered_calculations)

    def build(self) -> ResolvedDependencyGraph:
        try:
            self.registry.validate()
        except RegistryValidationError as error:
            raise DependencyResolutionError(str(error)) from error
        if not self.selected_calculations:
            raise DependencyResolutionError("Select at least one calculation before compiling a plan.")

        registry_order = {calculation.id: index for index, calculation in enumerate(self.registry.all())}
        selected = tuple(sorted(set(self.selected_calculations), key=lambda item: (registry_order.get(item, len(registry_order)), item)))
        for calculation_id in selected:
            if not self.registry.exists(calculation_id):
                raise DependencyResolutionError(f"Unknown calculation: {calculation_id}")

        dependencies: dict[str, tuple[str, ...]] = {}
        visiting: list[str] = []

        def collect(calculation_id: str) -> None:
            if calculation_id in dependencies:
                return
            if calculation_id in visiting:
                cycle = visiting[visiting.index(calculation_id):] + [calculation_id]
                raise DependencyResolutionError("Dependency cycle detected: " + " -> ".join(cycle))
            visiting.append(calculation_id)
            direct = tuple(self.registry.get(calculation_id).requires)
            dependencies[calculation_id] = direct
            for dependency_id in direct:
                collect(dependency_id)
            visiting.pop()

        for calculation_id in selected:
            collect(calculation_id)

        levels: dict[str, int] = {}
        def level(calculation_id: str) -> int:
            if calculation_id not in levels:
                direct = dependencies[calculation_id]
                levels[calculation_id] = 0 if not direct else 1 + max(level(item) for item in direct)
            return levels[calculation_id]

        for calculation_id in dependencies:
            level(calculation_id)

        remaining = set(dependencies)
        ordered: list[str] = []
        while remaining:
            ready = [
                calculation_id for calculation_id in remaining
                if all(dependency in ordered for dependency in dependencies[calculation_id])
            ]
            if not ready:
                raise DependencyResolutionError("Dependency graph has no valid topological order.")
            ready.sort(key=lambda item: (levels[item], registry_order[item], item))
            calculation_id = ready[0]
            ordered.append(calculation_id)
            remaining.remove(calculation_id)

        return ResolvedDependencyGraph(
            selected_calculations=selected,
            ordered_calculations=tuple(ordered),
            dependencies=tuple((item, dependencies[item]) for item in ordered),
            levels=tuple((item, levels[item]) for item in ordered),
        )
