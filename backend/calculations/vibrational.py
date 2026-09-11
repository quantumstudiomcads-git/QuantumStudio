"""Executable vibrational calculation definitions."""

from backend.calculations.definition import CalculationDefinition
from backend.calculations.registry import registry


registry.register(CalculationDefinition(
    id="phonons", name="Γ-Point Phonons", category="Vibrational Properties",
    description="Γ-point DFPT phonon frequencies and eigenmodes for supported 3D scalar PBE systems.", requires=("scf",),
    workflow="vibrational.phonons", engine="quantum_espresso", tags=("vibrational", "phonons"),
    parameters=("accuracy", "q_point", "tr2_ph"),
))
registry.register(CalculationDefinition(
    id="phonon_dos", name="Phonon Density of States", category="Vibrational Properties",
    description="Vibrational density of states.", requires=("phonons",),
    workflow="vibrational.phonon_dos", engine="quantum_espresso", tags=("vibrational", "phonons", "dos"),
    parameters=("accuracy", "qmesh", "tr2_ph", "dos_mesh"),
))
registry.register(CalculationDefinition(
    id="phonon_band_structure", name="Phonon Band Structure", category="Vibrational Properties",
    description="Phonon dispersion interpolated along an explicit reciprocal-space q path.", requires=("phonons",),
    workflow="vibrational.phonon_band_structure", engine="quantum_espresso", tags=("vibrational", "phonons", "dispersion"),
    parameters=("accuracy", "qmesh", "tr2_ph", "phonon_path", "path_points_per_segment"),
))

registry.register(CalculationDefinition(
    id="born_charges", name="Born Effective Charges", category="Vibrational Properties",
    description="Born effective charge tensors and the electronic high-frequency dielectric tensor for supported insulating 3D scalar PBE systems.", requires=("scf",),
    workflow="vibrational.born_charges", engine="quantum_espresso", tags=("vibrational", "polar", "bec"),
    parameters=("accuracy", "tr2_ph"),
))

registry.register(CalculationDefinition(
    id="lo_to_splitting", name="LO-TO Splitting", category="Vibrational Properties",
    description="Directional non-analytic Γ-point polar phonon frequencies.", requires=("born_charges",),
    workflow="vibrational.lo_to_splitting", engine="quantum_espresso", tags=("vibrational", "polar", "lo-to"),
    parameters=("accuracy", "direction", "directions"),
))
registry.register(CalculationDefinition(
    id="raman", name="Raman Spectrum", category="Vibrational Properties",
    description="Gamma-point non-resonant Raman tensors for supported QE 7.6 LDA/PZ norm-conserving workflows.", requires=("scf",),
    workflow="vibrational.raman", engine="quantum_espresso", tags=("vibrational", "raman", "spectroscopy"),
    parameters=("accuracy", "tr2_ph", "raman_accuracy"),
    metadata={"supported_functionals": ("pz",), "required_pseudo_type": "NC", "gamma_only": True},
))

registry.register(CalculationDefinition(
    id="infrared", name="Infrared Spectrum", category="Vibrational Properties",
    description="Γ-point infrared-active phonon modes using QE dynmat native activities.", requires=("born_charges",),
    workflow="vibrational.infrared", engine="quantum_espresso", tags=("vibrational", "polar", "infrared"),
    parameters=("accuracy",),
))
registry.register(CalculationDefinition(
    id="dielectric_phonon", name="Phonon Dielectric Response", category="Vibrational Properties",
    description="Electronic plus ionic harmonic lattice dielectric response from analytic Γ modes.", requires=("born_charges",),
    workflow="vibrational.dielectric_phonon", engine="quantum_espresso", tags=("vibrational", "polar", "dielectric"),
    parameters=("accuracy", "tr2_ph"),
))
