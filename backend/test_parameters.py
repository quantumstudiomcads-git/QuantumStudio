from backend.parameters.resolver import (
    ParameterResolver,
)


print()
print("============================================================")
print(" QUANTUM STUDIO — PARAMETER RESOLUTION TEST")
print("============================================================")


resolver = ParameterResolver(

    calculation_id="scf",

    accuracy="high",

    overrides={

        "functional": "HSE",

        "soc": True,

        "ecutwfc": 100,

    },
)


parameters = resolver.resolve()


print()
print("RESOLVED PARAMETERS")
print("------------------------------------------------------------")

for key, value in parameters.items():

    print(
        f"{key:<20}: {value}"
    )


print()
print("============================================================")
print(" DONE")
print("============================================================")
