"""
Quantum Studio Calculation Catalog

This is the frontend-facing catalog of calculations available in
Quantum Studio.

The catalog describes WHAT the user can request.

Execution is handled separately by the backend.

Status values:

    ready    - backend execution exists
    partial  - partially implemented
    planned  - visible in GUI, backend pending
"""

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class CalculationInfo:

    id: str
    name: str
    category: str
    engine: str
    description: str

    tags: tuple[str, ...] = ()

    status: str = "planned"
    executable_while_partial: bool = False


CALCULATIONS: list[CalculationInfo] = []


def register(
    id: str,
    name: str,
    category: str,
    engine: str,
    description: str,
    tags: Iterable[str] = (),
    status: str = "planned",
    executable_while_partial: bool = False,
) -> None:

    CALCULATIONS.append(
        CalculationInfo(
            id=id,
            name=name,
            category=category,
            engine=engine,
            description=description,
            tags=tuple(tags),
            status=status,
            executable_while_partial=bool(executable_while_partial),
        )
    )


# ============================================================
# STRUCTURAL AND GROUND STATE
# ============================================================

register(
    "scf",
    "Self-Consistent Field",
    "Structural & Ground State",
    "Quantum ESPRESSO",
    "Calculate the electronic ground state.",
    ["ground_state", "electronic", "qe"],
    "ready",
)

register(
    "relax",
    "Geometry Relaxation",
    "Structural & Ground State",
    "Quantum ESPRESSO",
    "Optimize atomic positions.",
    ["structure", "optimization", "qe"],
    "partial",
)

register(
    "vc_relax",
    "Variable Cell Relaxation",
    "Structural & Ground State",
    "Quantum ESPRESSO",
    "Optimize atomic positions and lattice vectors.",
    ["structure", "optimization", "cell", "qe"],
    "ready",
)

register(
    "nscf",
    "Non-Self-Consistent Field",
    "Structural & Ground State",
    "Quantum ESPRESSO",
    "Calculate electronic states using a fixed charge density.",
    ["electronic", "qe"],
    "partial",
)

register(
    "convergence_ecut",
    "Plane-Wave Cutoff Convergence",
    "Structural & Ground State",
    "Quantum ESPRESSO",
    "Converge total energy with respect to plane-wave cutoff.",
    ["convergence", "qe"],
)

register(
    "convergence_kpoints",
    "K-Point Convergence",
    "Structural & Ground State",
    "Quantum ESPRESSO",
    "Converge the calculation with respect to k-point sampling.",
    ["convergence", "kpoints", "qe"],
)

register(
    "convergence_supercell",
    "Supercell Convergence",
    "Structural & Ground State",
    "Quantum ESPRESSO",
    "Study convergence with supercell size.",
    ["convergence", "supercell"],
)

register(
    "equation_of_state",
    "Equation of State",
    "Structural & Ground State",
    "Quantum ESPRESSO",
    "Calculate energy as a function of volume.",
    ["eos", "structure"],
)

register(
    "elastic_constants",
    "Elastic Constants",
    "Structural & Ground State",
    "Quantum ESPRESSO",
    "Calculate elastic stiffness constants.",
    ["mechanical", "elastic"],
)

register(
    "stress_strain",
    "Stress-Strain Calculation",
    "Structural & Ground State",
    "Quantum ESPRESSO",
    "Calculate stress response under applied strain.",
    ["mechanical", "strain"],
)

register(
    "formation_energy",
    "Formation Energy",
    "Structural & Ground State",
    "Quantum ESPRESSO",
    "Calculate defect or compound formation energies.",
    ["thermodynamics", "defects"],
)

register(
    "surface_energy",
    "Surface Energy",
    "Structural & Ground State",
    "Quantum ESPRESSO",
    "Calculate the energy associated with a crystal surface.",
    ["surface"],
)

register(
    "cleavage_energy",
    "Cleavage Energy",
    "Structural & Ground State",
    "Quantum ESPRESSO",
    "Calculate energy required to separate layered materials.",
    ["surface", "2d"],
)

register(
    "vacancy_formation",
    "Vacancy Formation Energy",
    "Structural & Ground State",
    "Quantum ESPRESSO",
    "Calculate formation energy of atomic vacancies.",
    ["defects"],
)

register(
    "substitutional_defect",
    "Substitutional Defect",
    "Structural & Ground State",
    "Quantum ESPRESSO",
    "Calculate energetics of substitutional defects.",
    ["defects"],
)


# ============================================================
# ELECTRONIC PROPERTIES
# ============================================================

register(
    "bands",
    "Band Structure",
    "Electronic Properties",
    "Quantum ESPRESSO",
    "Calculate electronic band dispersion.",
    ["bands", "electronic", "qe"],
    "ready",
)

register(
    "dos",
    "Density of States",
    "Electronic Properties",
    "Quantum ESPRESSO",
    "Calculate the electronic density of states.",
    ["dos", "electronic", "qe"],
    "ready",
)

register(
    "pdos",
    "Projected Density of States",
    "Electronic Properties",
    "Quantum ESPRESSO",
    "Resolve density of states into atomic or orbital contributions.",
    ["dos", "projected"],
    "ready",
)

register(
    "charge_density",
    "Charge Density",
    "Electronic Properties",
    "Quantum ESPRESSO",
    "Calculate and visualize electronic charge density.",
    ["charge", "electronic"],
    "ready",
)

register(
    "spin_density",
    "Spin Density",
    "Electronic Properties",
    "Quantum ESPRESSO",
    "Calculate spatial spin density.",
    ["spin", "magnetism"],
    "ready",
)

register(
    "fermi_surface",
    "Fermi Surface",
    "Electronic Properties",
    "Quantum ESPRESSO",
    "Generate a dense reciprocal-space Fermi surface for metallic systems using QE fs.x.",
    ["fermi", "electronic"],
    "partial",
)

register(
    "band_gap",
    "Band Gap Analysis",
    "Electronic Properties",
    "Post-processing",
    "Extract sampled fundamental and direct band gaps from an automatic Bands prerequisite.",
    ["band_gap"],
    "ready",
)

register(
    "effective_mass",
    "Effective Mass",
    "Electronic Properties",
    "Post-processing",
    "Calculate carrier effective masses from an automatic Bands prerequisite.",
    ["effective_mass", "transport"],
    "ready",
)

register(
    "work_function",
    "Work Function",
    "Electronic Properties",
    "Quantum ESPRESSO",
    "Calculate the work function of a material or surface.",
    ["surface", "electronic"],
    "ready",
)

register(
    "electron_localization",
    "Electron Localization Function",
    "Electronic Properties",
    "Quantum ESPRESSO",
    "Calculate electron localization function.",
    ["elf", "charge"],
    "ready",
)

register(
    "bader_charge",
    "Bader Charge Analysis",
    "Electronic Properties",
    "Bader",
    "Partition electron density into atomic charges.",
    ["charge", "bader"],
    "ready",
)

register(
    "mulliken_population",
    "Löwdin Population Analysis",
    "Electronic Properties",
    "Post-processing",
    "Atomic-orbital population analysis using QE projwfc.x Löwdin projections.",
    ["population"],
    "ready",
)

register(
    "charge_transfer",
    "Atomic Charge Transfer (Bader)",
    "Electronic Properties",
    "Post-processing",
    "Atomic net charge transfer derived from Bader pseudo-valence populations.",
    ["charge", "interface"],
    "ready",
)

register(
    "band_decomposed_charge",
    "Band-Decomposed Charge Density",
    "Electronic Properties",
    "Quantum ESPRESSO",
    "Calculate charge density associated with selected states.",
    ["bands", "charge"],
    "partial",
)

register(
    "spin_texture",
    "Spin Texture",
    "Electronic Properties",
    "Quantum ESPRESSO",
    "k- and band-resolved spin expectation values for SOC/noncollinear states.",
    ["spin", "soc"],
    "partial",
)

register(
    "orbital_texture",
    "Orbital Texture",
    "Electronic Properties",
    "Post-processing",
    "k- and band-resolved atomic-orbital projection character; not orbital angular momentum.",
    ["orbital"],
    "partial",
)

register(
    "magnetic_moment",
    "Magnetic Moments",
    "Electronic Properties",
    "Quantum ESPRESSO",
    "Total QE magnetization and projected local moments where collinear projections are available.",
    ["magnetism"],
    "ready",
)

register(
    "exchange_parameters",
    "Exchange Parameters",
    "Electronic Properties",
    "Quantum ESPRESSO",
    "Heisenberg exchange parameters; requires an external exchange backend such as TB2J.",
    ["magnetism", "exchange"],
    "external_backend_required",
)

register(
    "hubbard_u",
    "Hubbard U Determination",
    "Electronic Properties",
    "Quantum ESPRESSO",
    "First-principles linear-response Hubbard parameters using QE hp.x.",
    ["dft_u", "correlation"],
    "partial",
)

register(
    "hybrid_electronic",
    "Hybrid Functional Electronic Structure",
    "Electronic Properties",
    "Quantum ESPRESSO",
    "Electronic structure using hybrid exchange-correlation.",
    ["hybrid", "hse", "pbe0"],
    "partial",
)


# ============================================================
# VIBRATIONAL PROPERTIES
# ============================================================

register(
    "phonons",
    "Γ-Point Phonons",
    "Vibrational Properties",
    "Quantum ESPRESSO",
    "Calculate Γ-point DFPT phonon frequencies and eigenmodes.",
    ["phonons", "vibrational", "qe", "gamma"],
    "ready",
)

register(
    "phonon_dos",
    "Phonon Density of States",
    "Vibrational Properties",
    "Quantum ESPRESSO",
    "Calculate vibrational density of states.",
    ["phonons", "dos"],
    "ready",
)

register(
    "phonon_modes",
    "Phonon Eigenmodes",
    "Vibrational Properties",
    "Quantum ESPRESSO",
    "Analyze vibrational eigenvectors.",
    ["phonons", "modes"],
)

register(
    "raman",
    "Raman Spectrum",
    "Vibrational Properties",
    "Quantum ESPRESSO",
    "Calculate Raman-active vibrational modes.",
    ["raman", "spectroscopy"],
    "ready",
)

register(
    "infrared",
    "Infrared Spectrum",
    "Vibrational Properties",
    "Quantum ESPRESSO",
    "Calculate infrared-active vibrational modes.",
    ["infrared", "spectroscopy"],
    "ready",
)

register(
    "lo_to_splitting",
    "LO-TO Splitting",
    "Vibrational Properties",
    "Quantum ESPRESSO",
    "Calculate longitudinal-transverse optical phonon splitting.",
    ["phonons", "polar"],
    "ready",
)

register(
    "born_charges",
    "Born Effective Charges",
    "Vibrational Properties",
    "Quantum ESPRESSO",
    "Calculate Born effective charge tensors.",
    ["bec", "dielectric"],
    "ready",
)

register(
    "dielectric_phonon",
    "Phonon Dielectric Response",
    "Vibrational Properties",
    "Quantum ESPRESSO",
    "Calculate dielectric response from lattice vibrations.",
    ["phonons", "dielectric"],
    "ready",
)

register(
    "electron_phonon",
    "Electron-Phonon Coupling",
    "Vibrational Properties",
    "EPW",
    "Calculate coupling between electrons and phonons.",
    ["electron_phonon", "epw"],
    "partial",
)

register(
    "eliashberg",
    "Eliashberg Function",
    "Vibrational Properties",
    "EPW",
    "Calculate the Eliashberg spectral function.",
    ["superconductivity", "electron_phonon"],
)

register(
    "superconducting_tc",
    "Superconducting Critical Temperature",
    "Vibrational Properties",
    "EPW",
    "Estimate superconducting critical temperature.",
    ["superconductivity"],
)

register(
    "phonon_lifetime",
    "Phonon Lifetime",
    "Vibrational Properties",
    "Phono3py",
    "Calculate phonon scattering lifetimes.",
    ["phonons", "thermal"],
)

register(
    "lattice_thermal_conductivity",
    "Lattice Thermal Conductivity",
    "Vibrational Properties",
    "Phono3py",
    "Calculate phonon-mediated thermal conductivity.",
    ["thermal", "phonons"],
)

register(
    "anharmonic_phonons",
    "Anharmonic Phonons",
    "Vibrational Properties",
    "Phono3py",
    "Calculate anharmonic vibrational properties.",
    ["anharmonic"],
)

register(
    "quasi_harmonic",
    "Quasi-Harmonic Approximation",
    "Vibrational Properties",
    "Phonopy",
    "Calculate temperature-dependent thermodynamic properties.",
    ["thermodynamics", "phonons"],
)


# ============================================================
# OPTICAL PROPERTIES
# ============================================================

register(
    "dielectric",
    "Complex Dielectric Function",
    "Optical Properties",
    "Quantum ESPRESSO",
    "Calculate frequency-dependent dielectric response.",
    ["optical", "dielectric"],
    "partial",
    True,
)

register(
    "absorption",
    "Optical Absorption",
    "Optical Properties",
    "Quantum ESPRESSO",
    "Calculate optical absorption spectrum.",
    ["optical", "absorption"],
    "partial",
    True,
)

register(
    "reflectivity",
    "Reflectivity",
    "Optical Properties",
    "Quantum ESPRESSO",
    "Calculate optical reflectivity.",
    ["optical"],
    "partial",
    True,
)

register(
    "refractive_index",
    "Refractive Index",
    "Optical Properties",
    "Post-processing",
    "Calculate refractive index and extinction coefficient.",
    ["optical"],
    "partial",
    True,
)

register(
    "optical_conductivity",
    "Optical Conductivity",
    "Optical Properties",
    "Quantum ESPRESSO",
    "Calculate frequency-dependent optical conductivity.",
    ["optical", "conductivity"],
    "partial",
    True,
)

register(
    "energy_loss",
    "Energy Loss Function",
    "Optical Properties",
    "Quantum ESPRESSO",
    "Calculate electron energy loss spectrum.",
    ["eels", "optical"],
    "partial",
    True,
)

register(
    "joint_dos",
    "Joint Density of States",
    "Optical Properties",
    "Post-processing",
    "Calculate joint density of states.",
    ["optical", "dos"],
)

register(
    "photoluminescence",
    "Photoluminescence",
    "Optical Properties",
    "Post-processing",
    "Estimate photoluminescence spectrum.",
    ["pl", "optical"],
)

register(
    "excitonic",
    "Excitonic Properties",
    "Optical Properties",
    "Yambo",
    "Calculate excitonic optical response.",
    ["exciton", "bse"],
)

register(
    "gw_quasiparticle",
    "GW Quasiparticle Calculation",
    "Optical Properties",
    "Yambo",
    "Calculate quasiparticle corrections.",
    ["gw"],
)

register(
    "bethe_salpeter",
    "Bethe-Salpeter Equation",
    "Optical Properties",
    "Yambo",
    "Calculate many-body optical spectra.",
    ["bse", "exciton"],
)

register(
    "nonlinear_optics",
    "Nonlinear Optical Response",
    "Optical Properties",
    "Quantum ESPRESSO",
    "Calculate nonlinear optical coefficients.",
    ["nonlinear", "shg"],
)

register(
    "second_harmonic",
    "Second Harmonic Generation",
    "Optical Properties",
    "Post-processing",
    "Calculate second-order nonlinear response.",
    ["shg"],
)

register(
    "circular_dichroism",
    "Circular Dichroism",
    "Optical Properties",
    "Post-processing",
    "Calculate differential optical absorption.",
    ["chiral", "optical"],
)

register(
    "absorption_2d",
    "2D Optical Absorption",
    "Optical Properties",
    "Post-processing",
    "Calculate absorption for low-dimensional materials.",
    ["2d", "optical"],
)


# ============================================================
# WANNIER AND BERRY PROPERTIES
# ============================================================

register(
    "wannierization",
    "Wannierization",
    "Wannier & Berry Properties",
    "Wannier90",
    "Construct maximally localized Wannier functions.",
    ["wannier"],
    "ready",
)

register(
    "wannier_bands",
    "Wannier Interpolated Bands",
    "Wannier & Berry Properties",
    "Wannier90",
    "Interpolate electronic bands using Wannier functions.",
    ["wannier", "bands"],
)

register(
    "berry_phase",
    "Berry Phase",
    "Wannier & Berry Properties",
    "Wannier90",
    "Calculate Berry phases.",
    ["berry", "topology"],
)

register(
    "berry_curvature",
    "Berry Curvature",
    "Wannier & Berry Properties",
    "Wannier90",
    "Calculate momentum-space Berry curvature.",
    ["berry", "topology"],
)

register(
    "chern_number",
    "Chern Number",
    "Wannier & Berry Properties",
    "Wannier90",
    "Calculate topological Chern number.",
    ["topology"],
)

register(
    "z2_invariant",
    "Z2 Topological Invariant",
    "Wannier & Berry Properties",
    "Wannier90",
    "Calculate Z2 topological invariant.",
    ["topology"],
)

register(
    "wilson_loop",
    "Wilson Loop",
    "Wannier & Berry Properties",
    "WannierTools",
    "Calculate Wilson loops and Wannier charge centers.",
    ["topology"],
)

register(
    "surface_states",
    "Topological Surface States",
    "Wannier & Berry Properties",
    "WannierTools",
    "Calculate surface electronic states.",
    ["surface", "topology"],
)

register(
    "fermi_arcs",
    "Fermi Arcs",
    "Wannier & Berry Properties",
    "WannierTools",
    "Calculate topological Fermi arc states.",
    ["topology", "weyl"],
)

register(
    "anomalous_hall",
    "Anomalous Hall Conductivity",
    "Wannier & Berry Properties",
    "Wannier90",
    "Calculate anomalous Hall response.",
    ["hall", "berry"],
)

register(
    "spin_hall",
    "Spin Hall Conductivity",
    "Wannier & Berry Properties",
    "Wannier90",
    "Calculate intrinsic spin Hall conductivity.",
    ["spin", "hall"],
)

register(
    "orbital_hall",
    "Orbital Hall Conductivity",
    "Wannier & Berry Properties",
    "Wannier90",
    "Calculate orbital Hall response.",
    ["orbital", "hall"],
)

register(
    "polarization",
    "Electric Polarization",
    "Wannier & Berry Properties",
    "Quantum ESPRESSO",
    "Calculate spontaneous electric polarization.",
    ["polarization", "berry"],
)

register(
    "ferroelectric",
    "Ferroelectric Polarization",
    "Wannier & Berry Properties",
    "Quantum ESPRESSO",
    "Calculate polarization switching properties.",
    ["ferroelectric"],
)

register(
    "orbital_magnetization",
    "Orbital Magnetization",
    "Wannier & Berry Properties",
    "Wannier90",
    "Calculate orbital contribution to magnetization.",
    ["magnetism", "orbital"],
)


# ============================================================
# BOLTZMANN TRANSPORT
# ============================================================

register(
    "boltztrap_bands",
    "Boltzmann Band Interpolation",
    "Boltzmann Transport",
    "BoltzTraP2",
    "Interpolate electronic bands for transport calculations.",
    ["boltztrap", "bands"],
    "partial",
)

register(
    "electrical_conductivity",
    "Electrical Conductivity / Relaxation Time (σ/τ)",
    "Boltzmann Transport",
    "BoltzTraP2",
    "Calculate electrical conductivity divided by relaxation time (σ/τ) for validated 3D scalar BoltzTraP2 transport.",
    ["transport", "boltztrap"],
    "ready",
)

register(
    "seebeck",
    "Seebeck Coefficient",
    "Boltzmann Transport",
    "BoltzTraP2",
    "Calculate thermoelectric Seebeck coefficient for validated 3D scalar BoltzTraP2 transport.",
    ["thermoelectric"],
    "ready",
)

register(
    "thermal_conductivity_electronic",
    "Electronic Thermal Conductivity / Relaxation Time (κe/τ)",
    "Boltzmann Transport",
    "BoltzTraP2",
    "Calculate electronic thermal conductivity divided by relaxation time (κe/τ) for validated 3D scalar BoltzTraP2 transport.",
    ["thermal", "transport"],
    "ready",
)

register(
    "power_factor",
    "Thermoelectric Power Factor",
    "Boltzmann Transport",
    "BoltzTraP2",
    "Calculate thermoelectric power factor.",
    ["thermoelectric"],
    "partial",
)

register(
    "zt",
    "Thermoelectric Figure of Merit",
    "Boltzmann Transport",
    "BoltzTraP2",
    "Calculate ZT using electronic and lattice contributions.",
    ["thermoelectric"],
)

register(
    "carrier_concentration",
    "Carrier Concentration",
    "Boltzmann Transport",
    "BoltzTraP2",
    "Calculate signed carrier concentration versus chemical potential for validated 3D scalar BoltzTraP2 transport.",
    ["transport"],
    "ready",
)

register(
    "mobility",
    "Carrier Mobility",
    "Boltzmann Transport",
    "BoltzTraP2",
    "Calculate carrier mobility.",
    ["mobility", "transport"],
)

register(
    "transport_temperature",
    "Temperature-Dependent Transport",
    "Boltzmann Transport",
    "BoltzTraP2",
    "Calculate transport coefficients over temperature.",
    ["temperature", "transport"],
)

register(
    "transport_doping",
    "Doping-Dependent Transport",
    "Boltzmann Transport",
    "BoltzTraP2",
    "Calculate transport coefficients versus carrier doping.",
    ["doping", "transport"],
)


# ============================================================
# NEGF AND DEVICE TRANSPORT
# ============================================================

register(
    "device_builder",
    "Device Construction",
    "NEGF & Device Transport",
    "NEGF",
    "Construct left electrode, scattering region, and right electrode.",
    ["device", "negf"],
)

register(
    "electrode_scf",
    "Electrode SCF",
    "NEGF & Device Transport",
    "NEGF",
    "Calculate self-consistent electrode electronic structure.",
    ["device", "electrode"],
)

register(
    "device_scf",
    "Device SCF",
    "NEGF & Device Transport",
    "NEGF",
    "Calculate the self-consistent device electronic state.",
    ["device", "negf"],
)

register(
    "transmission",
    "Transmission Spectrum",
    "NEGF & Device Transport",
    "NEGF",
    "Calculate transmission as a function of energy.",
    ["negf", "transport"],
)

register(
    "iv_curve",
    "Current-Voltage Curve",
    "NEGF & Device Transport",
    "NEGF",
    "Calculate current as a function of applied bias.",
    ["iv", "device"],
)

register(
    "bias_sweep",
    "Bias Sweep",
    "NEGF & Device Transport",
    "NEGF",
    "Perform transport calculations over multiple bias voltages.",
    ["bias", "device"],
)

register(
    "gate_voltage",
    "Gate Voltage Sweep",
    "NEGF & Device Transport",
    "NEGF",
    "Study transport response to gate voltage.",
    ["gate", "device"],
)

register(
    "local_dos",
    "Local Density of States",
    "NEGF & Device Transport",
    "NEGF",
    "Calculate spatially resolved density of states.",
    ["ldos", "device"],
)

register(
    "local_current",
    "Local Current",
    "NEGF & Device Transport",
    "NEGF",
    "Calculate local current pathways.",
    ["current", "device"],
)

register(
    "contact_resistance",
    "Contact Resistance",
    "NEGF & Device Transport",
    "NEGF",
    "Analyze resistance at device contacts.",
    ["contacts", "device"],
)

register(
    "spin_transport",
    "Spin Transport",
    "NEGF & Device Transport",
    "NEGF",
    "Calculate spin-dependent transport.",
    ["spintronics", "device"],
)

register(
    "thermoelectric_transport",
    "Thermoelectric Device Transport",
    "NEGF & Device Transport",
    "NEGF",
    "Calculate thermoelectric transport through a device.",
    ["thermoelectric", "device"],
)

register(
    "tunneling",
    "Quantum Tunneling",
    "NEGF & Device Transport",
    "NEGF",
    "Calculate tunneling transmission.",
    ["tunneling", "device"],
)

register(
    "resonant_transport",
    "Resonant Transport",
    "NEGF & Device Transport",
    "NEGF",
    "Identify resonant transport channels.",
    ["resonance", "device"],
)

register(
    "transistor",
    "Field-Effect Transistor Simulation",
    "NEGF & Device Transport",
    "NEGF",
    "Simulate gate-controlled device transport.",
    ["fet", "device"],
)


# ============================================================
# MOLECULAR DYNAMICS
# ============================================================

register(
    "md_nve",
    "NVE Molecular Dynamics",
    "Molecular Dynamics",
    "Quantum ESPRESSO",
    "Perform constant-energy molecular dynamics.",
    ["md", "nve"],
)

register(
    "md_nvt",
    "NVT Molecular Dynamics",
    "Molecular Dynamics",
    "Quantum ESPRESSO",
    "Perform constant-temperature molecular dynamics.",
    ["md", "nvt"],
)

register(
    "md_npt",
    "NPT Molecular Dynamics",
    "Molecular Dynamics",
    "Quantum ESPRESSO",
    "Perform constant-pressure and temperature dynamics.",
    ["md", "npt"],
)

register(
    "ab_initio_md",
    "Ab Initio Molecular Dynamics",
    "Molecular Dynamics",
    "Quantum ESPRESSO",
    "Perform first-principles molecular dynamics.",
    ["aimd", "md"],
)

register(
    "geometry_optimization_md",
    "MD Geometry Optimization",
    "Molecular Dynamics",
    "Quantum ESPRESSO",
    "Optimize structures through dynamical simulation.",
    ["md", "optimization"],
)

register(
    "radial_distribution",
    "Radial Distribution Function",
    "Molecular Dynamics",
    "Post-processing",
    "Calculate pair distribution functions.",
    ["rdf", "md"],
)

register(
    "mean_square_displacement",
    "Mean Square Displacement",
    "Molecular Dynamics",
    "Post-processing",
    "Calculate atomic diffusion from trajectories.",
    ["msd", "diffusion"],
)

register(
    "velocity_autocorrelation",
    "Velocity Autocorrelation",
    "Molecular Dynamics",
    "Post-processing",
    "Calculate velocity autocorrelation functions.",
    ["vacf", "md"],
)

register(
    "diffusion_coefficient",
    "Diffusion Coefficient",
    "Molecular Dynamics",
    "Post-processing",
    "Calculate diffusion coefficients.",
    ["diffusion"],
)

register(
    "thermal_expansion",
    "Thermal Expansion",
    "Molecular Dynamics",
    "Post-processing",
    "Calculate temperature-dependent lattice expansion.",
    ["thermal"],
)

register(
    "melting_point",
    "Melting Point Estimation",
    "Molecular Dynamics",
    "Post-processing",
    "Estimate melting behavior from simulations.",
    ["phase_transition"],
)

register(
    "trajectory_analysis",
    "Trajectory Analysis",
    "Molecular Dynamics",
    "Post-processing",
    "Analyze structural evolution during molecular dynamics.",
    ["trajectory"],
)


# ============================================================
# THERMODYNAMIC AND ADVANCED
# ============================================================

register(
    "free_energy",
    "Free Energy",
    "Thermodynamic & Advanced",
    "Phonopy",
    "Calculate vibrational free energy.",
    ["thermodynamics"],
)

register(
    "entropy",
    "Entropy",
    "Thermodynamic & Advanced",
    "Phonopy",
    "Calculate vibrational entropy.",
    ["thermodynamics"],
)

register(
    "heat_capacity",
    "Heat Capacity",
    "Thermodynamic & Advanced",
    "Phonopy",
    "Calculate constant-volume heat capacity.",
    ["thermodynamics"],
)

register(
    "phase_stability",
    "Phase Stability",
    "Thermodynamic & Advanced",
    "Post-processing",
    "Compare thermodynamic stability of phases.",
    ["phase"],
)

register(
    "defect_charge_transition",
    "Defect Charge Transition Levels",
    "Thermodynamic & Advanced",
    "Quantum ESPRESSO",
    "Calculate defect charge transition levels.",
    ["defects"],
)

register(
    "nudged_elastic_band",
    "Nudged Elastic Band",
    "Thermodynamic & Advanced",
    "Quantum ESPRESSO",
    "Calculate minimum-energy reaction pathways.",
    ["neb", "reaction"],
)

register(
    "transition_state",
    "Transition State Search",
    "Thermodynamic & Advanced",
    "Quantum ESPRESSO",
    "Locate transition-state configurations.",
    ["reaction"],
)

register(
    "adsorption_energy",
    "Adsorption Energy",
    "Thermodynamic & Advanced",
    "Quantum ESPRESSO",
    "Calculate adsorption energies.",
    ["surface", "adsorption"],
)

register(
    "reaction_energy",
    "Reaction Energy",
    "Thermodynamic & Advanced",
    "Quantum ESPRESSO",
    "Calculate reaction energetics.",
    ["reaction"],
)

register(
    "chemical_potential",
    "Chemical Potential",
    "Thermodynamic & Advanced",
    "Post-processing",
    "Analyze chemical potentials and stability.",
    ["thermodynamics"],
)

register(
    "grand_canonical",
    "Grand Canonical Thermodynamics",
    "Thermodynamic & Advanced",
    "Post-processing",
    "Analyze systems under varying chemical potential.",
    ["thermodynamics"],
)

register(
    "surface_phase_diagram",
    "Surface Phase Diagram",
    "Thermodynamic & Advanced",
    "Post-processing",
    "Construct surface stability phase diagrams.",
    ["surface", "phase"],
)

register(
    "charge_state_analysis",
    "Charge State Analysis",
    "Thermodynamic & Advanced",
    "Quantum ESPRESSO",
    "Analyze energetics of multiple defect charge states.",
    ["defects", "charge"],
)

register(
    "finite_temperature",
    "Finite Temperature Properties",
    "Thermodynamic & Advanced",
    "Phonopy",
    "Calculate temperature-dependent material properties.",
    ["temperature"],
)

register(
    "thermal_stability",
    "Thermal Stability",
    "Thermodynamic & Advanced",
    "Molecular Dynamics",
    "Analyze structural stability at elevated temperature.",
    ["thermal"],
)


# ============================================================
# SPECIALIZED AND POST-PROCESSING
# ============================================================

register(
    "xrd",
    "X-Ray Diffraction Pattern",
    "Specialized & Post-processing",
    "Post-processing",
    "Simulate powder X-ray diffraction.",
    ["xrd"],
)

register(
    "stem_image",
    "Simulated STEM Image",
    "Specialized & Post-processing",
    "Post-processing",
    "Simulate scanning transmission electron microscopy contrast.",
    ["stem"],
)

register(
    "tem_image",
    "Simulated TEM Image",
    "Specialized & Post-processing",
    "Post-processing",
    "Simulate transmission electron microscopy images.",
    ["tem"],
)

register(
    "stm_image",
    "Simulated STM Image",
    "Specialized & Post-processing",
    "Quantum ESPRESSO",
    "Simulate scanning tunneling microscopy images.",
    ["stm"],
)

register(
    "spectral_function",
    "Spectral Function",
    "Specialized & Post-processing",
    "Post-processing",
    "Calculate spectral density and quasiparticle features.",
    ["spectral"],
)

register(
    "charge_density_difference",
    "Charge Density Difference",
    "Specialized & Post-processing",
    "Post-processing",
    "Calculate charge redistribution between systems.",
    ["charge"],
)

register(
    "electrostatic_potential",
    "Electrostatic Potential",
    "Specialized & Post-processing",
    "Quantum ESPRESSO",
    "Calculate electrostatic potential.",
    ["potential"],
    "ready",
)

register(
    "planar_average",
    "Planar Averaged Potential",
    "Specialized & Post-processing",
    "Post-processing",
    "Calculate planar averages of charge or potential.",
    ["potential"],
)

register(
    "macroscopic_average",
    "Macroscopic Average",
    "Specialized & Post-processing",
    "Post-processing",
    "Calculate macroscopic averages for interfaces.",
    ["interface"],
)

register(
    "charge_density_line",
    "Charge Density Line Profile",
    "Specialized & Post-processing",
    "Post-processing",
    "Extract one-dimensional charge density profiles.",
    ["charge"],
)

register(
    "electronic_localization",
    "Electronic Localization Analysis",
    "Specialized & Post-processing",
    "Post-processing",
    "Analyze localization of electronic states.",
    ["localization"],
)

register(
    "band_alignment",
    "Band Alignment",
    "Specialized & Post-processing",
    "Post-processing",
    "Calculate band offsets between materials.",
    ["interface", "bands"],
)

register(
    "heterostructure_analysis",
    "Heterostructure Analysis",
    "Specialized & Post-processing",
    "Post-processing",
    "Analyze interface electronic and structural properties.",
    ["interface"],
)

register(
    "strain_engineering",
    "Strain Engineering Sweep",
    "Specialized & Post-processing",
    "Quantum ESPRESSO",
    "Automate calculations over applied strain.",
    ["strain", "automation"],
)

register(
    "parameter_sweep",
    "Parameter Sweep",
    "Specialized & Post-processing",
    "Workflow",
    "Run a calculation over a systematic parameter range.",
    ["automation", "sweep"],
)


# ============================================================
# CATALOG ACCESS
# ============================================================

def all_calculations() -> list[CalculationInfo]:

    return list(CALCULATIONS)


def public_catalogue_snapshot() -> tuple[dict[str, str], ...]:
    """Return the deterministic public Calculate contract for parity diagnostics."""
    return tuple(
        {
            "id": calculation.id,
            "name": calculation.name,
            "category": calculation.category,
            "engine": calculation.engine,
            "status": calculation.status,
        }
        for calculation in CALCULATIONS
    )


def categories() -> list[str]:

    return sorted(
        {
            calculation.category
            for calculation in CALCULATIONS
        }
    )


def by_category(
    category: str,
) -> list[CalculationInfo]:

    return [
        calculation
        for calculation in CALCULATIONS
        if calculation.category == category
    ]


def get(
    calculation_id: str,
) -> CalculationInfo:

    for calculation in CALCULATIONS:

        if calculation.id == calculation_id:
            return calculation

    raise KeyError(
        f"Unknown calculation: {calculation_id}"
    )


def search(
    query: str,
) -> list[CalculationInfo]:

    query = query.lower().strip()

    if not query:
        return all_calculations()

    results = []

    for calculation in CALCULATIONS:

        searchable = " ".join(
            [
                calculation.id,
                calculation.name,
                calculation.category,
                calculation.engine,
                calculation.description,
                *calculation.tags,
            ]
        ).lower()

        if query in searchable:

            results.append(calculation)

    return results


def by_status(
    status: str,
) -> list[CalculationInfo]:

    return [
        calculation
        for calculation in CALCULATIONS
        if calculation.status == status
    ]
