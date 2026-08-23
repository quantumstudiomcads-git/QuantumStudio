"""
Electronic Calculations
"""


from backend.calculations.definition import (
    CalculationDefinition,
)

from backend.calculations.registry import (
    registry,
)


# =============================================================
# SELF-CONSISTENT FIELD
# =============================================================

registry.register(

    CalculationDefinition(

        id="scf",

        name="Self-Consistent Field",

        category="Electronic Properties",

        description=(
            "Self-consistent electronic structure "
            "calculation."
        ),

        workflow="electronic.scf",

        engine="qe",

        tags=(

            "electronic",
            "ground_state",
            "scf",

        ),

    )

)


# =============================================================
# BAND STRUCTURE
# =============================================================

registry.register(

    CalculationDefinition(

        id="bands",

        name="Band Structure",

        category="Electronic Properties",

        description=(
            "Electronic band dispersion along "
            "high-symmetry k-point paths."
        ),

        requires=(

            "scf",

        ),

        workflow="electronic.bands",

        engine="qe",

        tags=(

            "electronic",
            "bands",
            "band_structure",

        ),

    )

)


# =============================================================
# DENSITY OF STATES
# =============================================================

registry.register(

    CalculationDefinition(

        id="dos",

        name="Density of States",

        category="Electronic Properties",

        description=(
            "Electronic density of states."
        ),

        requires=(

            "scf",

        ),

        workflow="electronic.dos",

        engine="qe",

        tags=(

            "electronic",
            "dos",

        ),

    )

)


# =============================================================
# PROJECTED DENSITY OF STATES
# =============================================================

registry.register(

    CalculationDefinition(

        id="pdos",

        name="Projected Density of States",

        category="Electronic Properties",

        description=(
            "Atom- and orbital-resolved "
            "electronic density of states."
        ),

        requires=(

            "scf",

        ),

        workflow="electronic.pdos",

        engine="qe",

        tags=(

            "electronic",
            "dos",
            "projected",

        ),

    )

)


# =============================================================
# CHARGE DENSITY
# =============================================================

registry.register(

    CalculationDefinition(

        id="charge_density",

        name="Charge Density",

        category="Electronic Properties",

        description=(
            "Real-space electronic charge density."
        ),

        requires=(

            "scf",

        ),

        workflow="electronic.charge_density",

        engine="qe",

        tags=(

            "electronic",
            "charge",
            "real_space",

        ),

    )

)


# =============================================================
# SPIN DENSITY
# =============================================================

registry.register(

    CalculationDefinition(

        id="spin_density",

        name="Spin Density",

        category="Electronic Properties",

        description=(
            "Real-space spin density."
        ),

        requires=(

            "scf",

        ),

        workflow="electronic.spin_density",

        engine="qe",

        tags=(

            "electronic",
            "spin",
            "real_space",

        ),

    )

)
