"""
Quantum Studio Dependency Resolver

Resolves the complete execution sequence required for a set
of user-selected calculations.

A calculation dependency may refer to:

1. Another calculation ID

Example:

    bands.requires = ("scf",)

2. An artifact produced by another calculation

Example:

    bands.requires = ("scf_result",)

3. An external project input

Example:

    scf.requires = ("structure",)

External inputs do not need another calculation to produce them.
"""


from backend.calculations.registry import registry


class DependencyResolver:

    # ---------------------------------------------------------
    # External inputs
    #
    # These are supplied directly by the Quantum Studio project
    # and therefore do not require another calculation.
    # ---------------------------------------------------------

    EXTERNAL_INPUTS = {

        "structure",

        "initial_structure",

        "device_structure",

        "transport_structure",

    }


    def __init__(
        self,
        selected_calculations: list[str],
    ):

        self.selected_calculations = (
            selected_calculations
        )

        self.resolved = []

        self.resolving = set()


    # ---------------------------------------------------------
    # Public API
    # ---------------------------------------------------------

    def resolve(self) -> list[str]:

        for calculation_id in (
            self.selected_calculations
        ):

            calculation = registry.get(
                calculation_id
            )

            self._resolve_calculation(
                calculation
            )

        return self.resolved


    # ---------------------------------------------------------
    # Recursive dependency resolution
    # ---------------------------------------------------------

    def _resolve_calculation(
        self,
        calculation,
    ):

        # Already resolved
        if calculation.id in self.resolved:

            return


        # Detect circular dependencies
        if calculation.id in self.resolving:

            raise RuntimeError(
                "Circular dependency detected involving "
                f"'{calculation.id}'"
            )


        self.resolving.add(
            calculation.id
        )


        # -----------------------------------------------------
        # Resolve all requirements first
        # -----------------------------------------------------

        for requirement in (
            calculation.requires
        ):

            dependency = (
                self._find_dependency(
                    requirement
                )
            )


            # External input
            #
            # Example:
            #
            # structure
            #
            # No calculation needs to be inserted.
            if dependency is None:

                continue


            self._resolve_calculation(
                dependency
            )


        # -----------------------------------------------------
        # All dependencies are resolved.
        #
        # Remove this calculation from the active recursion
        # stack and add it to the execution sequence.
        # -----------------------------------------------------

        self.resolving.remove(
            calculation.id
        )

        self.resolved.append(
            calculation.id
        )


    # ---------------------------------------------------------
    # Dependency lookup
    #
    # Resolution order:
    #
    # 1. External input
    # 2. Calculation ID
    # 3. Produced artifact
    # ---------------------------------------------------------

    def _find_dependency(
        self,
        requirement: str,
    ):

        # -----------------------------------------------------
        # External input
        # -----------------------------------------------------

        if requirement in self.EXTERNAL_INPUTS:

            return None


        # -----------------------------------------------------
        # Direct calculation dependency
        #
        # Example:
        #
        # requires = ("scf",)
        # -----------------------------------------------------

        try:

            return registry.get(
                requirement
            )

        except KeyError:

            pass


        # -----------------------------------------------------
        # Artifact dependency
        #
        # Example:
        #
        # requires = ("scf_result",)
        #
        # Find the calculation that produces:
        #
        # produces = ("scf_result",)
        # -----------------------------------------------------

        for calculation in registry.all():

            if requirement in calculation.produces:

                return calculation


        # -----------------------------------------------------
        # Nothing can satisfy this requirement
        # -----------------------------------------------------

        raise RuntimeError(
            f"Unable to resolve dependency "
            f"'{requirement}'. "
            f"No calculation with this ID exists and "
            f"no registered calculation produces this "
            f"artifact."
        )
