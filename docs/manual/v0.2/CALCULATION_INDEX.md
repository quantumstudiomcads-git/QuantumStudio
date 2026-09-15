# Public Calculation Index

This index reconciles all **148** public Quantum Studio 0.2.0 calculation intents. It excludes the backend-only definition `extinction_coefficient`. **Availability** is implementation availability; entitlement and scientific validation remain separate decisions.

| Display Name | Intent ID | Category | Implementation | Validation | Availability | Manual Link |
| --- | --- | --- | --- | --- | --- | --- |
| Self-Consistent Field | `scf` | Structural & Ground State | READY | UNKNOWN | Subject to validation, engine availability, and entitlement | [Reference](calculations/structural_and_ground_state/scf.md) |
| Geometry Relaxation | `relax` | Structural & Ground State | PARTIAL | UNKNOWN | Limited; see page | [Reference](calculations/structural_and_ground_state/relax.md) |
| Variable Cell Relaxation | `vc_relax` | Structural & Ground State | READY | UNKNOWN | Subject to validation, engine availability, and entitlement | [Reference](calculations/structural_and_ground_state/vc_relax.md) |
| Non-Self-Consistent Field | `nscf` | Structural & Ground State | PARTIAL | UNKNOWN | Limited; see page | [Reference](calculations/structural_and_ground_state/nscf.md) |
| Plane-Wave Cutoff Convergence | `convergence_ecut` | Structural & Ground State | PLANNED | UNKNOWN | Not executable | [Reference](calculations/structural_and_ground_state/planned_reference.md#convergence_ecut) |
| K-Point Convergence | `convergence_kpoints` | Structural & Ground State | PLANNED | UNKNOWN | Not executable | [Reference](calculations/structural_and_ground_state/planned_reference.md#convergence_kpoints) |
| Supercell Convergence | `convergence_supercell` | Structural & Ground State | PLANNED | UNKNOWN | Not executable | [Reference](calculations/structural_and_ground_state/planned_reference.md#convergence_supercell) |
| Equation of State | `equation_of_state` | Structural & Ground State | PLANNED | UNKNOWN | Not executable | [Reference](calculations/structural_and_ground_state/planned_reference.md#equation_of_state) |
| Elastic Constants | `elastic_constants` | Structural & Ground State | PLANNED | UNKNOWN | Not executable | [Reference](calculations/structural_and_ground_state/planned_reference.md#elastic_constants) |
| Stress-Strain Calculation | `stress_strain` | Structural & Ground State | PLANNED | UNKNOWN | Not executable | [Reference](calculations/structural_and_ground_state/planned_reference.md#stress_strain) |
| Formation Energy | `formation_energy` | Structural & Ground State | PLANNED | UNKNOWN | Not executable | [Reference](calculations/structural_and_ground_state/planned_reference.md#formation_energy) |
| Surface Energy | `surface_energy` | Structural & Ground State | PLANNED | UNKNOWN | Not executable | [Reference](calculations/structural_and_ground_state/planned_reference.md#surface_energy) |
| Cleavage Energy | `cleavage_energy` | Structural & Ground State | PLANNED | UNKNOWN | Not executable | [Reference](calculations/structural_and_ground_state/planned_reference.md#cleavage_energy) |
| Vacancy Formation Energy | `vacancy_formation` | Structural & Ground State | PLANNED | UNKNOWN | Not executable | [Reference](calculations/structural_and_ground_state/planned_reference.md#vacancy_formation) |
| Substitutional Defect | `substitutional_defect` | Structural & Ground State | PLANNED | UNKNOWN | Not executable | [Reference](calculations/structural_and_ground_state/planned_reference.md#substitutional_defect) |
| Band Structure | `bands` | Electronic Properties | READY | UNKNOWN | Subject to validation, engine availability, and entitlement | [Reference](calculations/electronic_properties/bands.md) |
| Density of States | `dos` | Electronic Properties | READY | UNKNOWN | Subject to validation, engine availability, and entitlement | [Reference](calculations/electronic_properties/dos.md) |
| Projected Density of States | `pdos` | Electronic Properties | READY | UNKNOWN | Subject to validation, engine availability, and entitlement | [Reference](calculations/electronic_properties/pdos.md) |
| Charge Density | `charge_density` | Electronic Properties | READY | UNKNOWN | Subject to validation, engine availability, and entitlement | [Reference](calculations/electronic_properties/charge_density.md) |
| Spin Density | `spin_density` | Electronic Properties | READY | UNKNOWN | Subject to validation, engine availability, and entitlement | [Reference](calculations/electronic_properties/spin_density.md) |
| Fermi Surface | `fermi_surface` | Electronic Properties | PARTIAL | UNKNOWN | Limited; see page | [Reference](calculations/electronic_properties/fermi_surface.md) |
| Band Gap Analysis | `band_gap` | Electronic Properties | READY | UNKNOWN | Subject to validation, engine availability, and entitlement | [Reference](calculations/electronic_properties/band_gap.md) |
| Effective Mass | `effective_mass` | Electronic Properties | READY | UNKNOWN | Subject to validation, engine availability, and entitlement | [Reference](calculations/electronic_properties/effective_mass.md) |
| Work Function | `work_function` | Electronic Properties | READY | UNKNOWN | Subject to validation, engine availability, and entitlement | [Reference](calculations/electronic_properties/work_function.md) |
| Electron Localization Function | `electron_localization` | Electronic Properties | READY | UNKNOWN | Subject to validation, engine availability, and entitlement | [Reference](calculations/electronic_properties/electron_localization.md) |
| Bader Charge Analysis | `bader_charge` | Electronic Properties | READY | UNKNOWN | Subject to validation, engine availability, and entitlement | [Reference](calculations/electronic_properties/bader_charge.md) |
| Löwdin Population Analysis | `mulliken_population` | Electronic Properties | READY | UNKNOWN | Subject to validation, engine availability, and entitlement | [Reference](calculations/electronic_properties/mulliken_population.md) |
| Atomic Charge Transfer (Bader) | `charge_transfer` | Electronic Properties | READY | UNKNOWN | Subject to validation, engine availability, and entitlement | [Reference](calculations/electronic_properties/charge_transfer.md) |
| Band-Decomposed Charge Density | `band_decomposed_charge` | Electronic Properties | PARTIAL | UNKNOWN | Limited; see page | [Reference](calculations/electronic_properties/band_decomposed_charge.md) |
| Spin Texture | `spin_texture` | Electronic Properties | PARTIAL | UNKNOWN | Limited; see page | [Reference](calculations/electronic_properties/spin_texture.md) |
| Orbital Texture | `orbital_texture` | Electronic Properties | PARTIAL | UNKNOWN | Limited; see page | [Reference](calculations/electronic_properties/orbital_texture.md) |
| Magnetic Moments | `magnetic_moment` | Electronic Properties | READY | UNKNOWN | Subject to validation, engine availability, and entitlement | [Reference](calculations/electronic_properties/magnetic_moment.md) |
| Exchange Parameters | `exchange_parameters` | Electronic Properties | EXTERNAL BACKEND REQUIRED | UNKNOWN | External backend required | [Reference](calculations/electronic_properties/exchange_parameters.md) |
| Hubbard U Determination | `hubbard_u` | Electronic Properties | PARTIAL | UNKNOWN | Limited; see page | [Reference](calculations/electronic_properties/hubbard_u.md) |
| Hybrid Functional Electronic Structure | `hybrid_electronic` | Electronic Properties | PARTIAL | UNKNOWN | Limited; see page | [Reference](calculations/electronic_properties/hybrid_electronic.md) |
| Γ-Point Phonons | `phonons` | Vibrational Properties | READY | UNKNOWN | Subject to validation, engine availability, and entitlement | [Reference](calculations/vibrational_properties/phonons.md) |
| Phonon Density of States | `phonon_dos` | Vibrational Properties | READY | UNKNOWN | Subject to validation, engine availability, and entitlement | [Reference](calculations/vibrational_properties/phonon_dos.md) |
| Phonon Band Structure | `phonon_band_structure` | Vibrational Properties | READY | UNKNOWN | Subject to validation, engine availability, and entitlement | [Reference](calculations/vibrational_properties/phonon_band_structure.md) |
| Phonon Eigenmodes | `phonon_modes` | Vibrational Properties | PLANNED | UNKNOWN | Not executable | [Reference](calculations/vibrational_properties/planned_reference.md#phonon_modes) |
| Raman Spectrum | `raman` | Vibrational Properties | READY | UNKNOWN | Subject to validation, engine availability, and entitlement | [Reference](calculations/vibrational_properties/raman.md) |
| Infrared Spectrum | `infrared` | Vibrational Properties | READY | UNKNOWN | Subject to validation, engine availability, and entitlement | [Reference](calculations/vibrational_properties/infrared.md) |
| LO-TO Splitting | `lo_to_splitting` | Vibrational Properties | READY | UNKNOWN | Subject to validation, engine availability, and entitlement | [Reference](calculations/vibrational_properties/lo_to_splitting.md) |
| Born Effective Charges | `born_charges` | Vibrational Properties | READY | UNKNOWN | Subject to validation, engine availability, and entitlement | [Reference](calculations/vibrational_properties/born_charges.md) |
| Phonon Dielectric Response | `dielectric_phonon` | Vibrational Properties | READY | UNKNOWN | Subject to validation, engine availability, and entitlement | [Reference](calculations/vibrational_properties/dielectric_phonon.md) |
| Electron-Phonon Coupling | `electron_phonon` | Vibrational Properties | PARTIAL | UNKNOWN | Limited; see page | [Reference](calculations/vibrational_properties/electron_phonon.md) |
| Eliashberg Function | `eliashberg` | Vibrational Properties | PLANNED | UNKNOWN | Not executable | [Reference](calculations/vibrational_properties/planned_reference.md#eliashberg) |
| Superconducting Critical Temperature | `superconducting_tc` | Vibrational Properties | PLANNED | UNKNOWN | Not executable | [Reference](calculations/vibrational_properties/planned_reference.md#superconducting_tc) |
| Phonon Lifetime | `phonon_lifetime` | Vibrational Properties | PLANNED | UNKNOWN | Not executable | [Reference](calculations/vibrational_properties/planned_reference.md#phonon_lifetime) |
| Lattice Thermal Conductivity | `lattice_thermal_conductivity` | Vibrational Properties | PLANNED | UNKNOWN | Not executable | [Reference](calculations/vibrational_properties/planned_reference.md#lattice_thermal_conductivity) |
| Anharmonic Phonons | `anharmonic_phonons` | Vibrational Properties | PLANNED | UNKNOWN | Not executable | [Reference](calculations/vibrational_properties/planned_reference.md#anharmonic_phonons) |
| Quasi-Harmonic Approximation | `quasi_harmonic` | Vibrational Properties | PLANNED | UNKNOWN | Not executable | [Reference](calculations/vibrational_properties/planned_reference.md#quasi_harmonic) |
| Complex Dielectric Function | `dielectric` | Optical Properties | PARTIAL | UNKNOWN | Limited; see page | [Reference](calculations/optical_properties/dielectric.md) |
| Optical Absorption | `absorption` | Optical Properties | PARTIAL | UNKNOWN | Limited; see page | [Reference](calculations/optical_properties/absorption.md) |
| Reflectivity | `reflectivity` | Optical Properties | PARTIAL | UNKNOWN | Limited; see page | [Reference](calculations/optical_properties/reflectivity.md) |
| Refractive Index | `refractive_index` | Optical Properties | PARTIAL | UNKNOWN | Limited; see page | [Reference](calculations/optical_properties/refractive_index.md) |
| Optical Conductivity | `optical_conductivity` | Optical Properties | PARTIAL | UNKNOWN | Limited; see page | [Reference](calculations/optical_properties/optical_conductivity.md) |
| Energy Loss Function | `energy_loss` | Optical Properties | PARTIAL | UNKNOWN | Limited; see page | [Reference](calculations/optical_properties/energy_loss.md) |
| Joint Density of States | `joint_dos` | Optical Properties | PLANNED | UNKNOWN | Not executable | [Reference](calculations/optical_properties/planned_reference.md#joint_dos) |
| Photoluminescence | `photoluminescence` | Optical Properties | PLANNED | UNKNOWN | Not executable | [Reference](calculations/optical_properties/planned_reference.md#photoluminescence) |
| Excitonic Properties | `excitonic` | Optical Properties | PLANNED | UNKNOWN | Not executable | [Reference](calculations/optical_properties/planned_reference.md#excitonic) |
| GW Quasiparticle Calculation | `gw_quasiparticle` | Optical Properties | PLANNED | UNKNOWN | Not executable | [Reference](calculations/optical_properties/planned_reference.md#gw_quasiparticle) |
| Bethe-Salpeter Equation | `bethe_salpeter` | Optical Properties | PLANNED | UNKNOWN | Not executable | [Reference](calculations/optical_properties/planned_reference.md#bethe_salpeter) |
| Nonlinear Optical Response | `nonlinear_optics` | Optical Properties | PLANNED | UNKNOWN | Not executable | [Reference](calculations/optical_properties/planned_reference.md#nonlinear_optics) |
| Second Harmonic Generation | `second_harmonic` | Optical Properties | PLANNED | UNKNOWN | Not executable | [Reference](calculations/optical_properties/planned_reference.md#second_harmonic) |
| Circular Dichroism | `circular_dichroism` | Optical Properties | PLANNED | UNKNOWN | Not executable | [Reference](calculations/optical_properties/planned_reference.md#circular_dichroism) |
| 2D Optical Absorption | `absorption_2d` | Optical Properties | PLANNED | UNKNOWN | Not executable | [Reference](calculations/optical_properties/planned_reference.md#absorption_2d) |
| Wannierization | `wannierization` | Wannier & Berry Properties | READY | UNKNOWN | Subject to validation, engine availability, and entitlement | [Reference](calculations/wannier_and_berry_properties/wannierization.md) |
| Wannier Interpolated Bands | `wannier_bands` | Wannier & Berry Properties | PLANNED | UNKNOWN | Not executable | [Reference](calculations/wannier_and_berry_properties/planned_reference.md#wannier_bands) |
| Berry Phase | `berry_phase` | Wannier & Berry Properties | PLANNED | UNKNOWN | Not executable | [Reference](calculations/wannier_and_berry_properties/planned_reference.md#berry_phase) |
| Berry Curvature | `berry_curvature` | Wannier & Berry Properties | PLANNED | UNKNOWN | Not executable | [Reference](calculations/wannier_and_berry_properties/planned_reference.md#berry_curvature) |
| Chern Number | `chern_number` | Wannier & Berry Properties | PLANNED | UNKNOWN | Not executable | [Reference](calculations/wannier_and_berry_properties/planned_reference.md#chern_number) |
| Z2 Topological Invariant | `z2_invariant` | Wannier & Berry Properties | PLANNED | UNKNOWN | Not executable | [Reference](calculations/wannier_and_berry_properties/planned_reference.md#z2_invariant) |
| Wilson Loop | `wilson_loop` | Wannier & Berry Properties | PLANNED | UNKNOWN | Not executable | [Reference](calculations/wannier_and_berry_properties/planned_reference.md#wilson_loop) |
| Topological Surface States | `surface_states` | Wannier & Berry Properties | PLANNED | UNKNOWN | Not executable | [Reference](calculations/wannier_and_berry_properties/planned_reference.md#surface_states) |
| Fermi Arcs | `fermi_arcs` | Wannier & Berry Properties | PLANNED | UNKNOWN | Not executable | [Reference](calculations/wannier_and_berry_properties/planned_reference.md#fermi_arcs) |
| Anomalous Hall Conductivity | `anomalous_hall` | Wannier & Berry Properties | PLANNED | UNKNOWN | Not executable | [Reference](calculations/wannier_and_berry_properties/planned_reference.md#anomalous_hall) |
| Spin Hall Conductivity | `spin_hall` | Wannier & Berry Properties | PLANNED | UNKNOWN | Not executable | [Reference](calculations/wannier_and_berry_properties/planned_reference.md#spin_hall) |
| Orbital Hall Conductivity | `orbital_hall` | Wannier & Berry Properties | PLANNED | UNKNOWN | Not executable | [Reference](calculations/wannier_and_berry_properties/planned_reference.md#orbital_hall) |
| Electric Polarization | `polarization` | Wannier & Berry Properties | PLANNED | UNKNOWN | Not executable | [Reference](calculations/wannier_and_berry_properties/planned_reference.md#polarization) |
| Ferroelectric Polarization | `ferroelectric` | Wannier & Berry Properties | PLANNED | UNKNOWN | Not executable | [Reference](calculations/wannier_and_berry_properties/planned_reference.md#ferroelectric) |
| Orbital Magnetization | `orbital_magnetization` | Wannier & Berry Properties | PLANNED | UNKNOWN | Not executable | [Reference](calculations/wannier_and_berry_properties/planned_reference.md#orbital_magnetization) |
| Boltzmann Band Interpolation | `boltztrap_bands` | Boltzmann Transport | PARTIAL | UNKNOWN | Limited; see page | [Reference](calculations/boltzmann_transport/boltztrap_bands.md) |
| Electrical Conductivity / Relaxation Time (σ/τ) | `electrical_conductivity` | Boltzmann Transport | READY | UNKNOWN | Subject to validation, engine availability, and entitlement | [Reference](calculations/boltzmann_transport/electrical_conductivity.md) |
| Seebeck Coefficient | `seebeck` | Boltzmann Transport | READY | UNKNOWN | Subject to validation, engine availability, and entitlement | [Reference](calculations/boltzmann_transport/seebeck.md) |
| Electronic Thermal Conductivity / Relaxation Time (κe/τ) | `thermal_conductivity_electronic` | Boltzmann Transport | READY | UNKNOWN | Subject to validation, engine availability, and entitlement | [Reference](calculations/boltzmann_transport/thermal_conductivity_electronic.md) |
| Thermoelectric Power Factor | `power_factor` | Boltzmann Transport | PARTIAL | UNKNOWN | Limited; see page | [Reference](calculations/boltzmann_transport/power_factor.md) |
| Thermoelectric Figure of Merit | `zt` | Boltzmann Transport | PLANNED | UNKNOWN | Not executable | [Reference](calculations/boltzmann_transport/planned_reference.md#zt) |
| Carrier Concentration | `carrier_concentration` | Boltzmann Transport | READY | UNKNOWN | Subject to validation, engine availability, and entitlement | [Reference](calculations/boltzmann_transport/carrier_concentration.md) |
| Carrier Mobility | `mobility` | Boltzmann Transport | PLANNED | UNKNOWN | Not executable | [Reference](calculations/boltzmann_transport/planned_reference.md#mobility) |
| Temperature-Dependent Transport | `transport_temperature` | Boltzmann Transport | PLANNED | UNKNOWN | Not executable | [Reference](calculations/boltzmann_transport/planned_reference.md#transport_temperature) |
| Doping-Dependent Transport | `transport_doping` | Boltzmann Transport | PLANNED | UNKNOWN | Not executable | [Reference](calculations/boltzmann_transport/planned_reference.md#transport_doping) |
| Device Construction | `device_builder` | NEGF & Device Transport | PLANNED | UNKNOWN | Not executable | [Reference](calculations/negf_and_device_transport/planned_reference.md#device_builder) |
| Electrode SCF | `electrode_scf` | NEGF & Device Transport | PLANNED | UNKNOWN | Not executable | [Reference](calculations/negf_and_device_transport/planned_reference.md#electrode_scf) |
| Device SCF | `device_scf` | NEGF & Device Transport | PLANNED | UNKNOWN | Not executable | [Reference](calculations/negf_and_device_transport/planned_reference.md#device_scf) |
| Transmission Spectrum | `transmission` | NEGF & Device Transport | PLANNED | UNKNOWN | Not executable | [Reference](calculations/negf_and_device_transport/planned_reference.md#transmission) |
| Current-Voltage Curve | `iv_curve` | NEGF & Device Transport | PLANNED | UNKNOWN | Not executable | [Reference](calculations/negf_and_device_transport/planned_reference.md#iv_curve) |
| Bias Sweep | `bias_sweep` | NEGF & Device Transport | PLANNED | UNKNOWN | Not executable | [Reference](calculations/negf_and_device_transport/planned_reference.md#bias_sweep) |
| Gate Voltage Sweep | `gate_voltage` | NEGF & Device Transport | PLANNED | UNKNOWN | Not executable | [Reference](calculations/negf_and_device_transport/planned_reference.md#gate_voltage) |
| Local Density of States | `local_dos` | NEGF & Device Transport | PLANNED | UNKNOWN | Not executable | [Reference](calculations/negf_and_device_transport/planned_reference.md#local_dos) |
| Local Current | `local_current` | NEGF & Device Transport | PLANNED | UNKNOWN | Not executable | [Reference](calculations/negf_and_device_transport/planned_reference.md#local_current) |
| Contact Resistance | `contact_resistance` | NEGF & Device Transport | PLANNED | UNKNOWN | Not executable | [Reference](calculations/negf_and_device_transport/planned_reference.md#contact_resistance) |
| Spin Transport | `spin_transport` | NEGF & Device Transport | PLANNED | UNKNOWN | Not executable | [Reference](calculations/negf_and_device_transport/planned_reference.md#spin_transport) |
| Thermoelectric Device Transport | `thermoelectric_transport` | NEGF & Device Transport | PLANNED | UNKNOWN | Not executable | [Reference](calculations/negf_and_device_transport/planned_reference.md#thermoelectric_transport) |
| Quantum Tunneling | `tunneling` | NEGF & Device Transport | PLANNED | UNKNOWN | Not executable | [Reference](calculations/negf_and_device_transport/planned_reference.md#tunneling) |
| Resonant Transport | `resonant_transport` | NEGF & Device Transport | PLANNED | UNKNOWN | Not executable | [Reference](calculations/negf_and_device_transport/planned_reference.md#resonant_transport) |
| Field-Effect Transistor Simulation | `transistor` | NEGF & Device Transport | PLANNED | UNKNOWN | Not executable | [Reference](calculations/negf_and_device_transport/planned_reference.md#transistor) |
| NVE Molecular Dynamics | `md_nve` | Molecular Dynamics | PLANNED | UNKNOWN | Not executable | [Reference](calculations/molecular_dynamics/planned_reference.md#md_nve) |
| NVT Molecular Dynamics | `md_nvt` | Molecular Dynamics | PLANNED | UNKNOWN | Not executable | [Reference](calculations/molecular_dynamics/planned_reference.md#md_nvt) |
| NPT Molecular Dynamics | `md_npt` | Molecular Dynamics | PLANNED | UNKNOWN | Not executable | [Reference](calculations/molecular_dynamics/planned_reference.md#md_npt) |
| Ab Initio Molecular Dynamics | `ab_initio_md` | Molecular Dynamics | PLANNED | UNKNOWN | Not executable | [Reference](calculations/molecular_dynamics/planned_reference.md#ab_initio_md) |
| MD Geometry Optimization | `geometry_optimization_md` | Molecular Dynamics | PLANNED | UNKNOWN | Not executable | [Reference](calculations/molecular_dynamics/planned_reference.md#geometry_optimization_md) |
| Radial Distribution Function | `radial_distribution` | Molecular Dynamics | PLANNED | UNKNOWN | Not executable | [Reference](calculations/molecular_dynamics/planned_reference.md#radial_distribution) |
| Mean Square Displacement | `mean_square_displacement` | Molecular Dynamics | PLANNED | UNKNOWN | Not executable | [Reference](calculations/molecular_dynamics/planned_reference.md#mean_square_displacement) |
| Velocity Autocorrelation | `velocity_autocorrelation` | Molecular Dynamics | PLANNED | UNKNOWN | Not executable | [Reference](calculations/molecular_dynamics/planned_reference.md#velocity_autocorrelation) |
| Diffusion Coefficient | `diffusion_coefficient` | Molecular Dynamics | PLANNED | UNKNOWN | Not executable | [Reference](calculations/molecular_dynamics/planned_reference.md#diffusion_coefficient) |
| Thermal Expansion | `thermal_expansion` | Molecular Dynamics | PLANNED | UNKNOWN | Not executable | [Reference](calculations/molecular_dynamics/planned_reference.md#thermal_expansion) |
| Melting Point Estimation | `melting_point` | Molecular Dynamics | PLANNED | UNKNOWN | Not executable | [Reference](calculations/molecular_dynamics/planned_reference.md#melting_point) |
| Trajectory Analysis | `trajectory_analysis` | Molecular Dynamics | PLANNED | UNKNOWN | Not executable | [Reference](calculations/molecular_dynamics/planned_reference.md#trajectory_analysis) |
| Free Energy | `free_energy` | Thermodynamic & Advanced | PLANNED | UNKNOWN | Not executable | [Reference](calculations/thermodynamic_and_advanced/planned_reference.md#free_energy) |
| Entropy | `entropy` | Thermodynamic & Advanced | PLANNED | UNKNOWN | Not executable | [Reference](calculations/thermodynamic_and_advanced/planned_reference.md#entropy) |
| Heat Capacity | `heat_capacity` | Thermodynamic & Advanced | PLANNED | UNKNOWN | Not executable | [Reference](calculations/thermodynamic_and_advanced/planned_reference.md#heat_capacity) |
| Phase Stability | `phase_stability` | Thermodynamic & Advanced | PLANNED | UNKNOWN | Not executable | [Reference](calculations/thermodynamic_and_advanced/planned_reference.md#phase_stability) |
| Defect Charge Transition Levels | `defect_charge_transition` | Thermodynamic & Advanced | PLANNED | UNKNOWN | Not executable | [Reference](calculations/thermodynamic_and_advanced/planned_reference.md#defect_charge_transition) |
| Nudged Elastic Band | `nudged_elastic_band` | Thermodynamic & Advanced | PLANNED | UNKNOWN | Not executable | [Reference](calculations/thermodynamic_and_advanced/planned_reference.md#nudged_elastic_band) |
| Transition State Search | `transition_state` | Thermodynamic & Advanced | PLANNED | UNKNOWN | Not executable | [Reference](calculations/thermodynamic_and_advanced/planned_reference.md#transition_state) |
| Adsorption Energy | `adsorption_energy` | Thermodynamic & Advanced | PLANNED | UNKNOWN | Not executable | [Reference](calculations/thermodynamic_and_advanced/planned_reference.md#adsorption_energy) |
| Reaction Energy | `reaction_energy` | Thermodynamic & Advanced | PLANNED | UNKNOWN | Not executable | [Reference](calculations/thermodynamic_and_advanced/planned_reference.md#reaction_energy) |
| Chemical Potential | `chemical_potential` | Thermodynamic & Advanced | PLANNED | UNKNOWN | Not executable | [Reference](calculations/thermodynamic_and_advanced/planned_reference.md#chemical_potential) |
| Grand Canonical Thermodynamics | `grand_canonical` | Thermodynamic & Advanced | PLANNED | UNKNOWN | Not executable | [Reference](calculations/thermodynamic_and_advanced/planned_reference.md#grand_canonical) |
| Surface Phase Diagram | `surface_phase_diagram` | Thermodynamic & Advanced | PLANNED | UNKNOWN | Not executable | [Reference](calculations/thermodynamic_and_advanced/planned_reference.md#surface_phase_diagram) |
| Charge State Analysis | `charge_state_analysis` | Thermodynamic & Advanced | PLANNED | UNKNOWN | Not executable | [Reference](calculations/thermodynamic_and_advanced/planned_reference.md#charge_state_analysis) |
| Finite Temperature Properties | `finite_temperature` | Thermodynamic & Advanced | PLANNED | UNKNOWN | Not executable | [Reference](calculations/thermodynamic_and_advanced/planned_reference.md#finite_temperature) |
| Thermal Stability | `thermal_stability` | Thermodynamic & Advanced | PLANNED | UNKNOWN | Not executable | [Reference](calculations/thermodynamic_and_advanced/planned_reference.md#thermal_stability) |
| X-Ray Diffraction Pattern | `xrd` | Specialized & Post-processing | PLANNED | UNKNOWN | Not executable | [Reference](calculations/specialized_and_post_processing/planned_reference.md#xrd) |
| Simulated STEM Image | `stem_image` | Specialized & Post-processing | PLANNED | UNKNOWN | Not executable | [Reference](calculations/specialized_and_post_processing/planned_reference.md#stem_image) |
| Simulated TEM Image | `tem_image` | Specialized & Post-processing | PLANNED | UNKNOWN | Not executable | [Reference](calculations/specialized_and_post_processing/planned_reference.md#tem_image) |
| Simulated STM Image | `stm_image` | Specialized & Post-processing | PLANNED | UNKNOWN | Not executable | [Reference](calculations/specialized_and_post_processing/planned_reference.md#stm_image) |
| Spectral Function | `spectral_function` | Specialized & Post-processing | PLANNED | UNKNOWN | Not executable | [Reference](calculations/specialized_and_post_processing/planned_reference.md#spectral_function) |
| Charge Density Difference | `charge_density_difference` | Specialized & Post-processing | PLANNED | UNKNOWN | Not executable | [Reference](calculations/specialized_and_post_processing/planned_reference.md#charge_density_difference) |
| Electrostatic Potential | `electrostatic_potential` | Specialized & Post-processing | READY | UNKNOWN | Subject to validation, engine availability, and entitlement | [Reference](calculations/specialized_and_post_processing/electrostatic_potential.md) |
| Planar Averaged Potential | `planar_average` | Specialized & Post-processing | PLANNED | UNKNOWN | Not executable | [Reference](calculations/specialized_and_post_processing/planned_reference.md#planar_average) |
| Macroscopic Average | `macroscopic_average` | Specialized & Post-processing | PLANNED | UNKNOWN | Not executable | [Reference](calculations/specialized_and_post_processing/planned_reference.md#macroscopic_average) |
| Charge Density Line Profile | `charge_density_line` | Specialized & Post-processing | PLANNED | UNKNOWN | Not executable | [Reference](calculations/specialized_and_post_processing/planned_reference.md#charge_density_line) |
| Electronic Localization Analysis | `electronic_localization` | Specialized & Post-processing | PLANNED | UNKNOWN | Not executable | [Reference](calculations/specialized_and_post_processing/planned_reference.md#electronic_localization) |
| Band Alignment | `band_alignment` | Specialized & Post-processing | PLANNED | UNKNOWN | Not executable | [Reference](calculations/specialized_and_post_processing/planned_reference.md#band_alignment) |
| Heterostructure Analysis | `heterostructure_analysis` | Specialized & Post-processing | PLANNED | UNKNOWN | Not executable | [Reference](calculations/specialized_and_post_processing/planned_reference.md#heterostructure_analysis) |
| Strain Engineering Sweep | `strain_engineering` | Specialized & Post-processing | PLANNED | UNKNOWN | Not executable | [Reference](calculations/specialized_and_post_processing/planned_reference.md#strain_engineering) |
| Parameter Sweep | `parameter_sweep` | Specialized & Post-processing | PLANNED | UNKNOWN | Not executable | [Reference](calculations/specialized_and_post_processing/planned_reference.md#parameter_sweep) |
