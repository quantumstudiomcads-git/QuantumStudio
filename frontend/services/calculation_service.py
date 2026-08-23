from dataclasses import dataclass


@dataclass(frozen=True)
class StructureSummary:

    name: str
    atom_count: int


class CalculationService:

    def __init__(self, calculations):
        self._calculations = tuple(calculations)
        self._calculation_map = {
            calculation.id: calculation
            for calculation in self._calculations
        }

    def get_calculation_map(self):
        return dict(self._calculation_map)

    def resolve_calculation_order(self, selected_ids):
        resolved = []
        visited = set()
        visiting = set()

        def visit(calculation_id):
            if calculation_id in visited:
                return

            if calculation_id in visiting:
                raise RuntimeError(
                    "Circular calculation dependency detected: "
                    f"{calculation_id}"
                )

            calculation = self._calculation_map.get(calculation_id)
            if calculation is None:
                raise RuntimeError(
                    "Unknown calculation: "
                    f"{calculation_id}"
                )

            visiting.add(calculation_id)

            for dependency_id in self._get_dependencies(calculation):
                visit(dependency_id)

            visiting.remove(calculation_id)
            visited.add(calculation_id)
            resolved.append(calculation_id)

        for calculation_id in selected_ids:
            visit(calculation_id)

        return resolved

    def validate_structure(self, project):
        try:
            structure = project.get_structure()
        except Exception as error:
            raise RuntimeError(
                "No active structure is available for this "
                f"workflow.\n\nDetails: {error}"
            ) from error

        if structure is None:
            raise RuntimeError(
                "No active structure is available.\n\n"
                "Import or create a structure before compiling "
                "a calculation workflow."
            )

        atoms = getattr(structure, "atoms", structure)

        try:
            atom_count = len(atoms)
        except Exception:
            atom_count = 0

        if atom_count == 0:
            raise RuntimeError(
                "The active structure contains no atoms.\n\n"
                "Import or create a valid structure before "
                "compiling the workflow."
            )

        structure_name = getattr(structure, "name", None)
        if not structure_name:
            structure_name = getattr(atoms, "name", "Active Structure")

        return structure, StructureSummary(
            name=structure_name,
            atom_count=atom_count,
        )

    @staticmethod
    def _get_dependencies(calculation):
        for attribute in (
            "dependencies",
            "depends_on",
            "requires",
        ):
            value = getattr(calculation, attribute, None)
            if value is None:
                continue
            if isinstance(value, str):
                return [value]
            try:
                return list(value)
            except TypeError:
                return []

        return []
