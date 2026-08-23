from backend.core.calculation_request import (
    CalculationRequest,
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

    "coordinate_system": "crystal",

}


request = CalculationRequest(

    structure=diamond,

    selected_calculations=[

        "bands",
        "dos",
        "phonons",

    ],

    parameters={

        "accuracy": "high",

        "functional": "HSE",

        "soc": True,

    },

    execution_target="local",

)


print("=" * 60)
print(" QUANTUM STUDIO — CALCULATION REQUEST")
print("=" * 60)

print()
print("REQUEST ID:")
print(request.id)

print()
print("SELECTED CALCULATIONS:")

for calculation in request.selected_calculations:

    print(
        f"  ✓ {calculation}"
    )

print()
print("PARAMETERS:")

for key, value in request.parameters.items():

    print(
        f"  {key:20}: {value}"
    )

print()
print("EXECUTION TARGET:")
print(
    f"  {request.execution_target}"
)

print()
print("=" * 60)
print(" DONE")
print("=" * 60)
