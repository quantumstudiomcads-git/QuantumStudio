"""
Quantum Studio

Full parameter resolution integration test.
"""

from backend.core.calculation_request import (
    CalculationRequest,
)

from backend.compiler.calculation_compiler import (
    CalculationCompiler,
)


diamond = {

    "lattice": [

        [3.567, 0.000, 0.000],
        [0.000, 3.567, 0.000],
        [0.000, 0.000, 3.567],

    ],

    "species": [

        "C",
        "C",

    ],

    "positions": [

        [0.000, 0.000, 0.000],
        [0.250, 0.250, 0.250],

    ],

    "coordinate_system":
        "crystal",
}


request = CalculationRequest(

    structure=diamond,

    selected_calculations=[

        "bands",
        "dos",
        "phonons",

    ],

    parameters={

        "accuracy":
            "high",

        "functional":
            "HSE",

        "soc":
            True,

    },

    execution_target=
        "local",
)


compiler = CalculationCompiler(
    request
)

plan = compiler.compile()


print()
print("=" * 60)
print(" QUANTUM STUDIO — PARAMETER PIPELINE")
print("=" * 60)

print()
print("USER REQUEST")

for key, value in request.parameters.items():

    print(
        f"  {key:20}: {value}"
    )


print()
print("RESOLVED EXECUTION SEQUENCE")

for index, calculation in enumerate(

    plan.resolved_calculations,

    start=1,

):

    print(
        f"  {index}. {calculation}"
    )


print()
print("PER-CALCULATION PARAMETERS")

for calculation in plan.resolved_calculations:

    print()
    print(
        f"  [{calculation}]"
    )

    parameters = (
        plan.calculation_parameters[
            calculation
        ]
    )

    if not parameters:

        print(
            "    No parameters"
        )

    else:

        for key, value in (
            parameters.items()
        ):

            print(
                f"    {key:20}: {value}"
            )


print()
print("=" * 60)
print(" PARAMETER RESOLUTION SUCCESSFUL")
print("=" * 60)

print()
