"""
Structural Calculations
"""


from backend.calculations.definition import (
    CalculationDefinition,
)

from backend.calculations.registry import (
    registry,
)


# =============================================================
# RELAXATION
# =============================================================

registry.register(

    CalculationDefinition(

        id="relax",

        name="Geometry Relaxation",

        category="Structural Properties",

        description=(
            "Relax atomic positions while keeping "
            "the simulation cell fixed."
        ),

        workflow="structural.relax",

        engine="qe",

        tags=(

            "structural",
            "relaxation",

        ),

    )

)


# =============================================================
# VARIABLE CELL RELAXATION
# =============================================================

registry.register(

    CalculationDefinition(

        id="vc_relax",

        name="Variable Cell Relaxation",

        category="Structural Properties",

        description=(
            "Relax atomic positions and lattice "
            "parameters simultaneously."
        ),

        workflow="structural.vc_relax",

        engine="qe",

        tags=(

            "structural",
            "relaxation",
            "cell",

        ),

    )

)
