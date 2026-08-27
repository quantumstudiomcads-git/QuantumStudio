"""Executable electronic calculation definitions."""

from backend.calculations.definition import CalculationDefinition
from backend.calculations.registry import registry


_SCF_PARAMETERS = (
    "accuracy", "functional", "pseudopotential", "ecutwfc", "ecutrho",
    "conv_thr", "kpoints", "spin", "soc",
)
_POST_SCF_PARAMETERS = (
    "accuracy", "functional", "pseudopotential", "ecutwfc", "ecutrho",
    "spin", "soc",
)

registry.register(CalculationDefinition(
    id="scf", name="Self-Consistent Field", category="Electronic Properties",
    description="Self-consistent electronic structure calculation.", workflow="electronic.scf",
    engine="quantum_espresso", tags=("electronic", "ground_state", "scf"), parameters=_SCF_PARAMETERS,
))
registry.register(CalculationDefinition(
    id="bands", name="Band Structure", category="Electronic Properties",
    description="Electronic band dispersion along high-symmetry k-point paths.", requires=("scf",),
    workflow="electronic.bands", engine="quantum_espresso", tags=("electronic", "bands", "band_structure"),
    parameters=_POST_SCF_PARAMETERS + ("kpath", "kpoint_density"),
))
registry.register(CalculationDefinition(
    id="dos", name="Density of States", category="Electronic Properties",
    description="Electronic density of states.", requires=("scf",), workflow="electronic.dos",
    engine="quantum_espresso", tags=("electronic", "dos"),
    parameters=_POST_SCF_PARAMETERS + ("dense_kpoints", "energy_window", "delta_e"),
))
registry.register(CalculationDefinition(
    id="pdos", name="Projected Density of States", category="Electronic Properties",
    description="Atom- and orbital-resolved electronic density of states.", requires=("scf",),
    workflow="electronic.pdos", engine="quantum_espresso", tags=("electronic", "dos", "projected"),
    parameters=_POST_SCF_PARAMETERS + ("dense_kpoints", "energy_window", "delta_e", "projection"),
))
registry.register(CalculationDefinition(
    id="charge_density", name="Charge Density", category="Electronic Properties",
    description="Real-space electronic charge density.", requires=("scf",),
    workflow="electronic.charge_density", engine="quantum_espresso", tags=("electronic", "charge", "real_space"),
    parameters=_POST_SCF_PARAMETERS,
))
registry.register(CalculationDefinition(
    id="spin_density", name="Spin Density", category="Electronic Properties",
    description="Real-space spin density.", requires=("scf",), workflow="electronic.spin_density",
    engine="quantum_espresso", tags=("electronic", "spin", "real_space"), parameters=_POST_SCF_PARAMETERS,
))
