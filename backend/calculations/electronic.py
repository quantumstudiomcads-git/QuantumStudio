"""Executable electronic calculation definitions."""

from backend.calculations.definition import CalculationDefinition
from backend.calculations.registry import registry


_SCF_PARAMETERS = (
    "accuracy", "functional", "pseudopotential", "ecutwfc", "ecutrho",
    "conv_thr", "kpoints", "spin", "soc", "spin_treatment", "starting_magnetization", "tot_magnetization", "hubbard_terms", "hubbard_projector", "occupations", "smearing", "degauss",
)
_POST_SCF_PARAMETERS = (
    "accuracy", "functional", "pseudopotential", "ecutwfc", "ecutrho",
    "spin", "soc", "spin_treatment", "starting_magnetization", "tot_magnetization", "hubbard_terms", "hubbard_projector", "occupations", "smearing", "degauss",
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
    description="Collinear real-space spin polarization.", requires=("scf",), workflow="electronic.spin_density",
    engine="quantum_espresso", tags=("electronic", "spin", "real_space"), parameters=_POST_SCF_PARAMETERS,
))
registry.register(CalculationDefinition(
    id="work_function", name="Work Function", category="Electronic Properties",
    description="Fermi-referenced slab vacuum work function.", requires=("scf",), workflow="electronic.work_function",
    engine="quantum_espresso", tags=("electronic", "surface", "work_function"), parameters=_POST_SCF_PARAMETERS + ("surface_normal", "macro_window_A"),
))
registry.register(CalculationDefinition(
    id="electron_localization", name="Electron Localization Function", category="Electronic Properties",
    description="Real-space electron localization function.", requires=("scf",), workflow="electronic.elf",
    engine="quantum_espresso", tags=("electronic", "elf", "real_space"), parameters=_POST_SCF_PARAMETERS,
))
registry.register(CalculationDefinition(
    id="electrostatic_potential", name="Electrostatic Potential", category="Electronic Properties",
    description="Bare-ionic plus Hartree potential field.", requires=("scf",), workflow="electronic.potential",
    engine="quantum_espresso", tags=("electronic", "potential", "real_space"), parameters=_POST_SCF_PARAMETERS,
))
