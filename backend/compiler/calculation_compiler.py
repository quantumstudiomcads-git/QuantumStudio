"""
Quantum Studio Calculation Compiler

Resolves the complete calculation dependency sequence.
"""

from backend.compiler.dependency_resolver import (
    DependencyResolver,
)

from backend.compiler.execution_plan import (
    ExecutionPlan,
)


class CalculationCompiler:

    def __init__(
        self,
        request,
    ):

        self.request = request


    def compile(self) -> ExecutionPlan:

        resolver = DependencyResolver(
            self.request.selected_calculations
        )

        resolved_calculations = (
            resolver.resolve()
        )

        return ExecutionPlan(
            calculation_id=self.request.id,

            selected_calculations=
                self.request.selected_calculations,

            resolved_calculations=
                resolved_calculations,

            execution_target=
                self.request.execution_target,
        )
