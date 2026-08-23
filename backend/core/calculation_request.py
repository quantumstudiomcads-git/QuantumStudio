"""
Quantum Studio Calculation Request

A CalculationRequest represents everything the user has requested
from Quantum Studio.

This is the primary interface between the GUI and the backend.

The GUI describes WHAT the user wants.

The backend determines HOW it must be executed.

Example:

    CalculationRequest(
        structure=diamond,
        selected_calculations=[
            "bands",
            "dos",
            "phonons",
        ],
        parameters={
            "accuracy": "high",
            "functional": "HSE",
            "soc": True,
        },
        execution_target="local",
    )
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


@dataclass
class CalculationRequest:

    # ---------------------------------------------------------
    # Structure
    # ---------------------------------------------------------

    structure: dict[str, Any]


    # ---------------------------------------------------------
    # User-selected calculations
    #
    # Example:
    #
    # ["bands", "dos", "phonons"]
    # ---------------------------------------------------------

    selected_calculations: list[str]


    # ---------------------------------------------------------
    # Global calculation parameters
    #
    # These may include:
    #
    # accuracy
    # functional
    # pseudopotential
    # spin
    # soc
    #
    # Engine-specific parameters may also be added later.
    # ---------------------------------------------------------

    parameters: dict[str, Any] = field(
        default_factory=dict
    )


    # ---------------------------------------------------------
    # Execution
    #
    # Examples:
    #
    # local
    # ssh
    # hpc
    # ---------------------------------------------------------

    execution_target: str = "local"


    # ---------------------------------------------------------
    # Identity
    # ---------------------------------------------------------

    id: str = field(
        default_factory=lambda: str(uuid4())
    )


    created_at: str = field(
        default_factory=lambda:
        datetime.now(
            timezone.utc
        ).isoformat()
    )


    # ---------------------------------------------------------
    # Future extensions
    #
    # Reserved for:
    #
    # project metadata
    # GUI state
    # notes
    # execution preferences
    # provenance
    # ---------------------------------------------------------

    metadata: dict[str, Any] = field(
        default_factory=dict
    )


    def to_dict(self) -> dict[str, Any]:

        return {

            "calculation_request": {

                "id": self.id,

                "created_at":
                    self.created_at,

                "structure":
                    self.structure,

                "selected_calculations":
                    self.selected_calculations,

                "parameters":
                    self.parameters,

                "execution_target":
                    self.execution_target,

                "metadata":
                    self.metadata,
            }
        }
