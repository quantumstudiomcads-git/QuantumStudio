"""
Quantum Studio Request Compiler Test
"""

from backend.compiler.request_compiler import (
    RequestCompiler,
)

from backend.core.calculation_request import (
    CalculationRequest,
)


diamond = {
    "lattice": [
        [3.567, 0.0, 0.0],
        [0.0, 3.567, 0.0],
        [0.0, 0.0, 3.567],
    ],

    "species": [
        "C",
        "C",
    ],

    "positions": [
        [0.0, 0.0, 0.0],
        [0.25, 0.25, 0.25],
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


compiler = RequestCompiler(
    request
)

plan = compiler.compile()


print()
print("=" * 60)
print(" QUANTUM STUDIO — REQUEST COMPILER TEST")
print("=" * 60)

print()
print("REQUEST")
print(f"ID      : {request.id}")
print(f"Target  : {request.execution_target}")

print()
print("USER SELECTED")

for calculation in request.selected_calculations:
    print(f"  ✓ {calculation}")


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
print("RESOLVED PARAMETERS")

parameters = plan.metadata[
    "parameters"
]

for calculation, values in parameters.items():

    print()
    print(f"  [{calculation}]")

    for key, value in values.items():

        print(
            f"    {key:20}: {value}"
        )


print()
print("STRUCTURE")

structure = plan.metadata[
    "structure"
]

print(
    f"  atoms : "
    f"{len(structure['species'])}"
)

print(
    f"  species : "
    f"{', '.join(structure['species'])}"
)


print()
print("=" * 60)
print(" EXECUTION PLAN CREATED SUCCESSFULLY")
print("=" * 60)
