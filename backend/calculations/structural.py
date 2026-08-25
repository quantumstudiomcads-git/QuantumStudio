"""Executable structural calculation definitions."""

from backend.calculations.definition import CalculationDefinition
from backend.calculations.registry import registry


_COMMON_ELECTRONIC_PARAMETERS = (
    "accuracy", "functional", "pseudopotential", "ecutwfc", "ecutrho",
    "conv_thr", "kpoints", "spin", "soc",
)

registry.register(CalculationDefinition(
    id="relax", name="Geometry Relaxation", category="Structural Properties",
    description="Relax atomic positions while keeping the simulation cell fixed.",
    workflow="structural.relax", engine="quantum_espresso", tags=("structural", "relaxation"),
    parameters=_COMMON_ELECTRONIC_PARAMETERS + ("force_threshold",),
))

registry.register(CalculationDefinition(
    id="vc_relax", name="Variable Cell Relaxation", category="Structural Properties",
    description="Relax atomic positions and lattice parameters simultaneously.",
    workflow="structural.vc_relax", engine="quantum_espresso", tags=("structural", "relaxation", "cell"),
    parameters=_COMMON_ELECTRONIC_PARAMETERS + ("force_threshold", "stress_threshold"),
))
