from dataclasses import dataclass
import unittest

from frontend.services.calculation_service import CalculationService


@dataclass(frozen=True)
class Calculation:
    id: str
    requires: tuple[str, ...] = ()


class Project:

    def __init__(self, structure):
        self.structure = structure

    def get_structure(self):
        return self.structure


class CalculationServiceTest(unittest.TestCase):

    def test_resolve_calculation_order_places_dependencies_first(self):
        service = CalculationService(
            [
                Calculation("scf"),
                Calculation("bands", ("scf",)),
            ]
        )

        self.assertEqual(
            service.resolve_calculation_order(["bands"]),
            ["scf", "bands"],
        )

    def test_resolve_calculation_order_rejects_cycles(self):
        service = CalculationService(
            [
                Calculation("a", ("b",)),
                Calculation("b", ("a",)),
            ]
        )

        with self.assertRaisesRegex(RuntimeError, "Circular"):
            service.resolve_calculation_order(["a"])

    def test_validate_structure_returns_summary(self):
        structure = type(
            "Structure",
            (),
            {"name": "Diamond", "atoms": [1, 2]},
        )()

        _, summary = CalculationService([]).validate_structure(
            Project(structure)
        )

        self.assertEqual(summary.name, "Diamond")
        self.assertEqual(summary.atom_count, 2)

    def test_validate_structure_rejects_empty_structure(self):
        structure = type(
            "Structure",
            (),
            {"name": "Empty", "atoms": []},
        )()

        with self.assertRaisesRegex(RuntimeError, "contains no atoms"):
            CalculationService([]).validate_structure(Project(structure))


if __name__ == "__main__":
    unittest.main()
