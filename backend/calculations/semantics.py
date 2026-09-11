"""Authoritative C5E scientific taxonomy for every public catalog intent."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from frontend.calculations.catalog import CALCULATIONS

class CalculationKind(str,Enum): PRIMITIVE="PRIMITIVE"; WORKFLOW="WORKFLOW"; DERIVED="DERIVED"; MULTI_SYSTEM="MULTI_SYSTEM"; META="META"
class InputCardinality(str,Enum): SINGLE_STRUCTURE="SINGLE_STRUCTURE"; MULTI_STRUCTURE="MULTI_STRUCTURE"; DEVICE_TRANSPORT="DEVICE_TRANSPORT"; TRAJECTORY="TRAJECTORY"; RESULT_ONLY="RESULT_ONLY"; META_CHILD_WORKFLOW="META_CHILD_WORKFLOW"
@dataclass(frozen=True)
class CalculationSemantics:
 calculation_id:str; kind:CalculationKind; prerequisites:tuple[str,...]; workflow_family:str; input_cardinality:InputCardinality; required_capabilities:tuple[str,...]=(); notes:str=""

_MULTI={"formation_energy","surface_energy","cleavage_energy","vacancy_formation","substitutional_defect","ferroelectric","phase_stability","defect_charge_transition","adsorption_energy","reaction_energy","chemical_potential","surface_phase_diagram","charge_state_analysis","charge_density_difference","band_alignment","heterostructure_analysis"}
_META={"convergence_ecut","convergence_kpoints","convergence_supercell","transport_temperature","transport_doping","bias_sweep","gate_voltage","strain_engineering","parameter_sweep","device_builder"}
_TRAJECTORY={"radial_distribution","mean_square_displacement","velocity_autocorrelation","diffusion_coefficient","thermal_expansion","melting_point","trajectory_analysis"}
_DERIVED={"band_gap","effective_mass","work_function","electron_localization","bader_charge","mulliken_population","charge_transfer","band_decomposed_charge","spin_texture","orbital_texture","magnetic_moment","exchange_parameters","phonon_modes","raman","infrared","lo_to_splitting","born_charges","refractive_index","joint_dos","power_factor","zt","mobility","wannier_bands","berry_phase","berry_curvature","chern_number","z2_invariant","wilson_loop","surface_states","fermi_arcs","anomalous_hall","spin_hall","orbital_hall","polarization","orbital_magnetization","local_dos","local_current","contact_resistance","spin_transport","thermoelectric_transport","tunneling","resonant_transport","spectral_function","planar_average","macroscopic_average","charge_density_line","electronic_localization"}
_NEGF={"device_builder","electrode_scf","device_scf","transmission","iv_curve","bias_sweep","gate_voltage","local_dos","local_current","contact_resistance","spin_transport","thermoelectric_transport","tunneling","resonant_transport","transistor"}
_MD={"md_nve","md_nvt","md_npt","ab_initio_md","geometry_optimization_md"}
_BASE={"bands":("scf",),"dos":("scf",),"pdos":("scf",),"phonons":("scf",),"phonon_dos":("phonons",),"phonon_band_structure":("phonons",),"electron_phonon":("scf",),"wannierization":("scf",),"boltztrap_bands":("scf",),"electrical_conductivity":("boltztrap_bands",),"seebeck":("boltztrap_bands",),"thermal_conductivity_electronic":("boltztrap_bands",),"power_factor":("seebeck","electrical_conductivity"),"zt":("power_factor","thermal_conductivity_electronic","lattice_thermal_conductivity"),"carrier_concentration":("boltztrap_bands",),"transmission":("electrode_scf","device_scf"),"local_dos":("transmission",),"iv_curve":("transmission",),"tunneling":("transmission",),"resonant_transport":("transmission",)}
def _family(cid):
 if cid=="electron_phonon":return "electron_phonon"
 if cid in _NEGF:return "negf_transport"
 if cid in _MD or cid in _TRAJECTORY:return "molecular_dynamics"
 if cid.startswith("phonon") or cid in {"raman","infrared","lattice_thermal_conductivity","anharmonic_phonons","quasi_harmonic","electron_phonon"}:return "phonon_harmonic"
 if cid in {"wannierization","wannier_bands","berry_phase","berry_curvature","chern_number","z2_invariant","wilson_loop"}:return "wannier"
 if cid in {"boltztrap_bands","electrical_conductivity","seebeck","thermal_conductivity_electronic","power_factor","zt","carrier_concentration","mobility","transport_temperature","transport_doping"}:return "boltzmann_transport"
 if cid in _MULTI:return "multi_system_energy"
 if cid in _META:return "parameter_sweep"
 if cid in {"bands","band_gap","effective_mass","fermi_surface"}:return "electronic_bands"
 if cid in {"dos","pdos","joint_dos"}:return "electronic_dos"
 if cid in {"relax","vc_relax"}:return "relaxation"
 return "ground_state"
def _kind(cid): return CalculationKind.MULTI_SYSTEM if cid in _MULTI else CalculationKind.META if cid in _META else CalculationKind.DERIVED if cid in _DERIVED or cid in _TRAJECTORY else CalculationKind.WORKFLOW if cid in _BASE or cid in _MD else CalculationKind.PRIMITIVE
def _input(cid,kind): return InputCardinality.DEVICE_TRANSPORT if cid in _NEGF else InputCardinality.MULTI_STRUCTURE if kind is CalculationKind.MULTI_SYSTEM else InputCardinality.META_CHILD_WORKFLOW if kind is CalculationKind.META else InputCardinality.TRAJECTORY if cid in _TRAJECTORY else InputCardinality.RESULT_ONLY if kind is CalculationKind.DERIVED else InputCardinality.SINGLE_STRUCTURE
SEMANTICS={c.id:CalculationSemantics(c.id,_kind(c.id),_BASE.get(c.id,()),_family(c.id),_input(c.id,_kind(c.id)),notes=("Requires a future multi-system request model." if c.id in _MULTI else "Requires TransportInput; public Calculate routing is deferred." if c.id in _NEGF else "")) for c in CALCULATIONS}
