"""
Calculation API Routes

Provides the GUI with information about all calculations
registered in Quantum Studio.
"""

from fastapi import APIRouter, HTTPException

from backend.calculations.registry import registry


router = APIRouter()


@router.get("/")
def list_calculations():

    calculations = []

    for calculation in registry.all():

        calculations.append(
            {
                "id": calculation.id,
                "name": calculation.name,
                "category": calculation.category,
                "description": calculation.description,
                "requires": calculation.requires,
                "produces": calculation.produces,
                "workflow": calculation.workflow,
                "engine": calculation.engine,
                "parameters": calculation.parameters,
                "tags": calculation.tags,
            }
        )

    return {
        "calculations": calculations,
        "categories": registry.categories(),
    }


@router.get("/{calculation_id}")
def get_calculation(
    calculation_id: str,
):

    try:

        calculation = registry.get(
            calculation_id
        )

    except KeyError:

        raise HTTPException(
            status_code=404,
            detail=(
                f"Unknown calculation: "
                f"{calculation_id}"
            ),
        )

    return {
        "id": calculation.id,
        "name": calculation.name,
        "category": calculation.category,
        "description": calculation.description,
        "requires": calculation.requires,
        "produces": calculation.produces,
        "workflow": calculation.workflow,
        "engine": calculation.engine,
        "parameters": calculation.parameters,
        "tags": calculation.tags,
        "metadata": calculation.metadata,
    }
