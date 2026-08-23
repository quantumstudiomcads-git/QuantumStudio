import json
from uuid import uuid4

import backend.calculations

from backend.compiler.calculation_compiler import (
    CalculationCompiler,
)


compiler = CalculationCompiler(

    calculation_id=str(uuid4()),

    selected_calculations=[
        "bands",
        "dos",
        "phonons",
    ],

    execution_target="local",
)


plan = compiler.compile()


print()
print("=" * 60)
print(" QUANTUM STUDIO — CALCULATION COMPILER")
print("=" * 60)

print()
print("USER SELECTED:")

for calculation in plan.selected_calculations:
    print(f"  ✓ {calculation}")

print()
print("RESOLVED EXECUTION SEQUENCE:")

for index, calculation in enumerate(
    plan.resolved_calculations,
    start=1,
):
    print(
        f"  {index}. {calculation}"
    )

print()
print("EXECUTION TARGET:")
print(
    f"  {plan.execution_target}"
)

print()
print("EXECUTION PLAN:")
print(
    json.dumps(
        plan.to_dict(),
        indent=2,
    )
)
