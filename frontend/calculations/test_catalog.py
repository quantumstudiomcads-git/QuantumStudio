"""
Quantum Studio Calculation Catalog Test
"""

from frontend.calculations.catalog import (
    all_calculations,
    by_category,
    categories,
    by_status,
)


print()
print("=" * 60)
print(" QUANTUM STUDIO — CALCULATION CATALOG")
print("=" * 60)
print()

catalog = all_calculations()

print(f"TOTAL CALCULATIONS: {len(catalog)}")
print()

print("CATEGORY BREAKDOWN")
print("-" * 60)

for category in categories():

    calculations = by_category(category)

    print(
        f"{category:<35} "
        f"{len(calculations):>3}"
    )

print()
print("STATUS BREAKDOWN")
print("-" * 60)

for status in (
    "ready",
    "partial",
    "planned",
):

    print(
        f"{status:<35} "
        f"{len(by_status(status)):>3}"
    )

print()
print("=" * 60)
print(" SAMPLE CALCULATIONS")
print("=" * 60)

for calculation in catalog[:10]:

    print(
        f"[{calculation.id}] "
        f"{calculation.name}"
    )

print()
