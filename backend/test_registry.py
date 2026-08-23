from backend.calculations import registry


print()
print("=" * 60)
print(" QUANTUM STUDIO — CALCULATION REGISTRY")
print("=" * 60)


print()

for category in registry.categories():

    print()
    print(category)
    print("-" * len(category))

    calculations = registry.by_category(
        category
    )

    for calculation in calculations:

        print(
            f"  [{calculation.id}] "
            f"{calculation.name}"
        )

        if calculation.requires:

            print(
                f"      requires: "
                f"{', '.join(calculation.requires)}"
            )

        print(
            f"      workflow: "
            f"{calculation.workflow}"
        )


print()
print("=" * 60)
print(
    f"TOTAL CALCULATIONS: "
    f"{len(registry.all())}"
)
print("=" * 60)
