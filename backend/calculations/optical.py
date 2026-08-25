"""Executable optical calculation definitions."""

from backend.calculations.definition import CalculationDefinition
from backend.calculations.registry import registry


registry.register(CalculationDefinition(
    id="dielectric", name="Dielectric Function", category="Optical Properties",
    description="Frequency-dependent dielectric response.", requires=("scf",),
    workflow="optical.dielectric", engine="quantum_espresso", tags=("optical", "dielectric"),
    parameters=("accuracy", "functional", "spin", "soc", "energy_window"),
))
registry.register(CalculationDefinition(
    id="absorption", name="Optical Absorption", category="Optical Properties",
    description="Optical absorption spectrum.", requires=("dielectric",),
    workflow="optical.absorption", engine="quantum_espresso", tags=("optical", "absorption"),
    parameters=("accuracy", "energy_window"),
))
