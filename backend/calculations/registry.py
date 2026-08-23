"""
Quantum Studio Calculation Registry

The registry is the single source of truth for all calculations
available in Quantum Studio.

The GUI queries this registry.

The calculation compiler queries this registry.

The workflow system queries this registry.

The execution backend may query this registry.

No component should need to maintain its own independent list
of supported calculations.
"""


from backend.calculations.definition import (
    CalculationDefinition,
)


class CalculationRegistry:

    def __init__(self):

        self._calculations: dict[
            str,
            CalculationDefinition
        ] = {}


    # ---------------------------------------------------------
    # Registration
    # ---------------------------------------------------------

    def register(
        self,
        calculation: CalculationDefinition,
    ) -> None:

        if calculation.id in self._calculations:

            raise ValueError(
                f"Calculation already registered: "
                f"{calculation.id}"
            )

        self._calculations[
            calculation.id
        ] = calculation


    # ---------------------------------------------------------
    # Retrieval
    # ---------------------------------------------------------

    def get(
        self,
        calculation_id: str,
    ) -> CalculationDefinition:

        try:

            return self._calculations[
                calculation_id
            ]

        except KeyError:

            raise KeyError(
                f"Unknown calculation: "
                f"{calculation_id}"
            )


    def exists(
        self,
        calculation_id: str,
    ) -> bool:

        return calculation_id in self._calculations


    # ---------------------------------------------------------
    # Listing
    # ---------------------------------------------------------

    def all(
        self,
    ) -> list[CalculationDefinition]:

        return list(
            self._calculations.values()
        )


    # ---------------------------------------------------------
    # Categories
    # ---------------------------------------------------------

    def categories(
        self,
    ) -> list[str]:

        return sorted(
            {
                calculation.category

                for calculation
                in self._calculations.values()
            }
        )


    def by_category(
        self,
        category: str,
    ) -> list[CalculationDefinition]:

        return [

            calculation

            for calculation
            in self._calculations.values()

            if calculation.category == category
        ]


    # ---------------------------------------------------------
    # Tags
    # ---------------------------------------------------------

    def by_tag(
        self,
        tag: str,
    ) -> list[CalculationDefinition]:

        return [

            calculation

            for calculation
            in self._calculations.values()

            if tag in calculation.tags
        ]


# -------------------------------------------------------------
# Global registry
#
# Quantum Studio imports this object everywhere.
# -------------------------------------------------------------

registry = CalculationRegistry()
