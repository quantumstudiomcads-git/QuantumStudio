"""Executable electronic calculation definitions."""

from backend.calculations.definition import CalculationDefinition
from backend.calculations.registry import registry


_SCF_PARAMETERS = (
    "accuracy", "functional", "pseudopotential", "ecutwfc", "ecutrho",
    "conv_thr", "kpoints", "spin", "soc", "spin_treatment", "starting_magnetization", "tot_magnetization", "hubbard_terms", "hubbard_projector", "occupations", "smearing", "degauss", "wf_collect", "disk_io",
)
_POST_SCF_PARAMETERS = (
    "accuracy", "functional", "pseudopotential", "ecutwfc", "ecutrho",
    "spin", "soc", "spin_treatment", "starting_magnetization", "tot_magnetization", "hubbard_terms", "hubbard_projector", "occupations", "smearing", "degauss", "wf_collect", "disk_io",
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
    id="band_decomposed_charge", name="Band-Decomposed Charge Density", category="Electronic Properties",
    description="Selected-state probability density |psi_nk(r)|² from QE pp.x.", requires=("scf",), workflow="electronic.band_decomposed_charge", engine="quantum_espresso", tags=("electronic","volumetric","band"), parameters=_POST_SCF_PARAMETERS + ("kpoint", "kband", "spin_component"),
))
registry.register(CalculationDefinition(
    id="fermi_surface", name="Fermi Surface", category="Electronic Properties",
    description="Dense reciprocal-space Fermi-surface sampling using QE fs.x.", requires=("scf",), workflow="electronic.fermi_surface", engine="quantum_espresso", tags=("electronic","fermi_surface","metal"), parameters=_POST_SCF_PARAMETERS + ("mesh", "deltaE", "spin_channel"),
))
registry.register(CalculationDefinition(
    id="bader_charge", name="Bader Charge Analysis", category="Electronic Properties",
    description="Topological partition of QE pseudo-valence charge density using Bader.", requires=("scf",),
    workflow="electronic.bader", engine="quantum_espresso", tags=("electronic", "bader", "charge"), parameters=_POST_SCF_PARAMETERS,
))
registry.register(CalculationDefinition(
    id="charge_transfer", name="Atomic Charge Transfer (Bader)", category="Electronic Properties",
    description="Atomic pseudo-valence charge transfer derived from a Bader result.", requires=("bader_charge",),
    workflow="electronic.charge_transfer", engine="quantum_espresso", tags=("electronic", "derived", "bader"), parameters=_POST_SCF_PARAMETERS,
))
registry.register(CalculationDefinition(
    id="mulliken_population", name="Löwdin Population Analysis", category="Electronic Properties",
    description="Atomic-orbital population analysis using QE projwfc.x Löwdin projections.", requires=("scf",),
    workflow="electronic.lowdin", engine="quantum_espresso", tags=("electronic", "projection", "lowdin"), parameters=_POST_SCF_PARAMETERS + ("projection",),
))
registry.register(CalculationDefinition(
    id="orbital_texture", name="Orbital Character / Orbital Texture", category="Electronic Properties",
    description="k- and band-resolved atomic-orbital projection character from QE projwfc.x.", requires=("scf",),
    workflow="electronic.orbital_texture", engine="quantum_espresso", tags=("electronic", "orbital", "projection"), parameters=_POST_SCF_PARAMETERS + ("kpath", "kpoint_density"),
))
registry.register(CalculationDefinition(
    id="magnetic_moment", name="Magnetic Moments", category="Electronic Properties",
    description="Cell and collinear Löwdin-projected local magnetic moments.", requires=("mulliken_population",),
    workflow="electronic.magnetic_moment", engine="quantum_espresso", tags=("electronic", "magnetism", "projection"), parameters=_POST_SCF_PARAMETERS,
))
registry.register(CalculationDefinition(
    id="band_gap", name="Band Gap Analysis", category="Electronic Properties",
    description="Sampled band-edge analysis derived from a compatible band structure.", requires=("bands",),
    workflow="electronic.band_gap", engine="quantum_espresso", tags=("electronic", "derived", "band_gap"),
    parameters=_POST_SCF_PARAMETERS + ("kpath", "kpoint_density"),
))
registry.register(CalculationDefinition(
    id="effective_mass", name="Effective Mass", category="Electronic Properties",
    description="Local carrier effective-mass fit derived from a compatible band structure.", requires=("bands",),
    workflow="electronic.effective_mass", engine="quantum_espresso", tags=("electronic", "derived", "effective_mass"),
    parameters=_POST_SCF_PARAMETERS + ("kpath", "kpoint_density", "carrier", "edge", "fit_points", "band_index"),
))
registry.register(CalculationDefinition(
    id="hybrid_electronic", name="Hybrid Functional Electronic Structure", category="Electronic Properties",
    description="HSE06 or B3LYP self-consistent electronic structure and band dispersion.", requires=("bands",), workflow="electronic.hybrid_bands", engine="quantum_espresso", tags=("electronic","hybrid","bands"), parameters=_POST_SCF_PARAMETERS + ("kpath", "kpoint_density", "exx_q_mesh"),
))
registry.register(CalculationDefinition(
    id="hubbard_u", name="Hubbard U Determination", category="Electronic Properties",
    description="Linear-response Hubbard parameters using QE hp.x.", requires=("scf",), workflow="electronic.hubbard_u", engine="quantum_espresso", tags=("electronic","hubbard","linear_response"), parameters=_POST_SCF_PARAMETERS + ("hubbard_species", "hubbard_manifold", "qmesh", "conv_thr"),
))
registry.register(CalculationDefinition(
    id="electrostatic_potential", name="Electrostatic Potential", category="Electronic Properties",
    description="Bare-ionic plus Hartree potential field.", requires=("scf",), workflow="electronic.potential",
    engine="quantum_espresso", tags=("electronic", "potential", "real_space"), parameters=_POST_SCF_PARAMETERS,
))
