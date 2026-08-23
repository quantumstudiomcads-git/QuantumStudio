"""
Vibrational Calculations
"""


from backend.calculations.definition import (
    CalculationDefinition,
)

from backend.calculations.registry import (
    registry,
)


# =============================================================
# PHONONS
# =============================================================

registry.register(

    CalculationDefinition(

        id="phonons",

        name="Phonon Dispersion",

        category="Vibrational Properties",

        description=(
            "Phonon frequencies and vibrational "
            "dispersion relations."
        ),

        requires=(

            "scf",

        ),

        workflow="vibrational.phonons",

        engine="qe",

        tags=(

            "vibrational",
            "phonons",

        ),

    )

)


# =============================================================
# PHONON DOS
# =============================================================

registry.register(

    CalculationDefinition(

        id="phonon_dos",

        name="Phonon Density of States",

        category="Vibrational Properties",

        description=(
            "Vibrational density of states."
        ),

        requires=(

            "phonons",

        ),

        workflow="vibrational.phonon_dos",

        engine="qe",

        tags=(

            "vibrational",
            "phonons",
            "dos",

        ),

    )

)
