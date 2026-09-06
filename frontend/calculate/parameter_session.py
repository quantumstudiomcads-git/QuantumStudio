"""Qt-free C8D parameter/preset view over the authoritative C3 resolver."""
from __future__ import annotations
import json
from backend.parameters.defaults import CALCULATION_DEFAULTS

PRESETS={"FAST":"low","INTERMEDIATE":"standard","PRECISE":"high","CUSTOM":"custom"}
UNITS={"hubbard_terms":"","hubbard_projector":"","tot_magnetization":"electrons","ecutwfc":"Ry","ecutrho":"Ry","degauss":"Ry","conv_thr":"","tr2_ph":"","nbnd":"","dense_kpoints":"mesh","qmesh":"mesh","energy_window":"eV","energy_min_eV":"eV","energy_max_eV":"eV","interband_broadening_eV":"eV","intraband_broadening_eV":"eV","optical_k_mesh":"mesh","optical_nbnd":"bands","number_of_points":"samples","delta_e":"eV","transport_k_mesh":"mesh"}
LABELS={"spin_treatment":"Spin treatment","starting_magnetization":"Initial magnetization by species (QE dimensionless)","tot_magnetization":"Constrained total magnetization","hubbard_terms":"Hubbard U terms","hubbard_projector":"Hubbard projector","ecutwfc":"Plane-wave cutoff","ecutrho":"Charge-density cutoff","conv_thr":"SCF convergence threshold","dense_kpoints":"Dense k mesh","qmesh":"Phonon q mesh","kpath":"Band path","nbnd":"Number of bands","spin":"Spin polarized","soc":"Spin-orbit coupling","delta_e":"DOS energy spacing","energy_min_eV":"Optical minimum photon energy","energy_max_eV":"Optical maximum photon energy","number_of_points":"Optical spectral points","interband_broadening_eV":"Interband broadening","intraband_broadening_eV":"Intraband broadening","optical_k_mesh":"Optical k mesh","optical_nbnd":"Optical bands","polarization_directions":"Tensor components","degauss":"DOS broadening"}
def preset_parameters(calculation_ids, mode, custom=None):
    mode=str(mode).upper(); values={}
    if mode not in PRESETS: raise ValueError("Unknown accuracy preset.")
    for item in calculation_ids:
        values.update(CALCULATION_DEFAULTS.get(item,{}))
    if mode!="CUSTOM": values["accuracy"]=PRESETS[mode]
    else: values.update(custom or {})
    return values
def descriptors(calculation_ids):
    keys=[]
    from backend.calculations import registry
    for item in calculation_ids:
        for key in registry.get(item).parameters:
            if key not in keys: keys.append(key)
    return tuple({"key":key,"label":LABELS.get(key,key.replace("_"," ").title()),"unit":UNITS.get(key,""),"default":next((CALCULATION_DEFAULTS.get(item,{}).get(key) for item in calculation_ids if key in CALCULATION_DEFAULTS.get(item,{})),None)} for key in keys)
def parse_value(value):
    try:return json.loads(value)
    except json.JSONDecodeError:return value
