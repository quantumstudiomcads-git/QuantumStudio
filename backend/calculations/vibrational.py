"""Executable vibrational calculation definitions."""

from backend.calculations.definition import CalculationDefinition
from backend.calculations.registry import registry


registry.register(CalculationDefinition(
    id="phonons", name="Phonon Dispersion", category="Vibrational Properties",
    description="Phonon frequencies and vibrational dispersion relations.", requires=("scf",),
    workflow="vibrational.phonons", engine="quantum_espresso", tags=("vibrational", "phonons"),
    parameters=("accuracy", "qmesh", "tr2_ph", "phonon_convergence", "lo_to_splitting"),
))
registry.register(CalculationDefinition(
    id="phonon_dos", name="Phonon Density of States", category="Vibrational Properties",
    description="Vibrational density of states.", requires=("phonons",),
    workflow="vibrational.phonon_dos", engine="quantum_espresso", tags=("vibrational", "phonons", "dos"),
    parameters=("accuracy", "qmesh", "phonon_convergence"),
))
