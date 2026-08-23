"""
Quantum Studio Request Compiler

The RequestCompiler converts a CalculationRequest into a fully
resolved ExecutionPlan.

It coordinates calculation dependency resolution and parameter
resolution.
"""

from backend.compiler.calculation_compiler import (
    CalculationCompiler,
)

from backend.compiler.parameter_resolver import (
    ParameterResolver,
)

from backend.core.calculation_request import (
    CalculationRequest,
)


class RequestCompiler:

    def __init__(
        self,
        request: CalculationRequest,
    ):

        self.request = request


    def compile(self):

        # -----------------------------------------------------
        # Resolve calculation dependencies
        #
        # CalculationCompiler operates directly on the complete
        # CalculationRequest.
        # -----------------------------------------------------

        calculation_compiler = CalculationCompiler(
            self.request
        )

        plan = calculation_compiler.compile()


        # -----------------------------------------------------
        # Resolve parameters for every calculation in the final
        # execution sequence.
        # -----------------------------------------------------

        parameter_resolver = ParameterResolver(
            self.request.parameters
        )

        resolved_parameters = (
            parameter_resolver.resolve(
                plan.resolved_calculations
            )
        )


        # -----------------------------------------------------
        # Attach resolved information to the execution plan.
        # -----------------------------------------------------

        plan.metadata["parameters"] = (
            resolved_parameters
        )

        plan.metadata["structure"] = (
            self.request.structure
        )

        plan.metadata["request_created_at"] = (
            self.request.created_at
        )

        plan.metadata["request_metadata"] = (
            self.request.metadata
        )


        return plan
