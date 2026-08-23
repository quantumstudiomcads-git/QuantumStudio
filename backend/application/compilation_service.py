from backend.compiler.request_compiler import RequestCompiler
from backend.core.calculation_request import CalculationRequest


class CompilationService:

    def compile(
        self,
        *,
        selected_calculations,
        structure,
        parameters=None,
        execution_target="local",
    ):
        request = CalculationRequest(
            selected_calculations=selected_calculations,
            structure=structure,
            parameters=parameters or {},
            execution_target=execution_target,
        )

        return RequestCompiler(request).compile()
