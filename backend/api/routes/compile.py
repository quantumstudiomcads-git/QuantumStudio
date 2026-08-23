"""
Compilation API Routes

Receives a calculation request from the GUI and converts it
into a fully resolved ExecutionPlan.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.application.compilation_service import (
    CompilationService,
)


router = APIRouter()
compilation_service = CompilationService()


class CompileRequest(BaseModel):

    selected_calculations: list[str] = Field(
        min_length=1,
    )

    structure: dict

    parameters: dict = Field(
        default_factory=dict,
    )

    execution_target: str = "local"


@router.post("/")
def compile_calculation(
    request: CompileRequest,
):

    try:

        execution_plan = compilation_service.compile(
            selected_calculations=request.selected_calculations,
            structure=request.structure,
            parameters=request.parameters,
            execution_target=request.execution_target,
        )

        return execution_plan.to_dict()

    except Exception as error:

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )
