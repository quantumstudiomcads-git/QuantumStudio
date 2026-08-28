"""Qt-free derived electronic Result contracts."""
from __future__ import annotations
import numpy as np
from backend.analyze.electronic import analyze_band_edges, available_fit_directions, fit_effective_mass
from .models import ResultStatus, ScientificResult

def _edge(edge):
    if edge is None: return None
    return {"energy_eV":edge.energy,"band_index":edge.band_index,"path_sample_index":edge.path_sample_index,"path_coordinate":edge.path_coordinate,"kpoint":None if edge.kpoint is None else list(edge.kpoint),"label":edge.label}

def derive_band_gap(source):
    analysis=analyze_band_edges(source)
    metadata={"source_band_result_id":source.result_id,"sampling_caveat":"Gap classification is limited to the calculated reciprocal-space samples.","gap_scope":analysis.gap_scope,"classification":analysis.classification,"vbm":_edge(analysis.vbm),"cbm":_edge(analysis.cbm),"minimum_sampled_direct_gap_eV":analysis.minimum_direct_gap}
    scalars={}
    if analysis.vbm: scalars["vbm"]={"value":analysis.vbm.energy,"unit":"eV"}
    if analysis.cbm: scalars["cbm"]={"value":analysis.cbm.energy,"unit":"eV"}
    if analysis.gap is not None: scalars["sampled_gap"]={"value":analysis.gap,"unit":"eV"}
    if analysis.minimum_direct_gap is not None: scalars["minimum_sampled_direct_gap"]={"value":analysis.minimum_direct_gap,"unit":"eV"}
    status=ResultStatus.VALID if analysis.status=="VALID" else ResultStatus.PARTIAL
    return ScientificResult("BandGapResult",status,source.provenance,scalars=scalars,arrays={key:np.asarray(value) for key,value in source.arrays.items() if key in {"path_coordinate","energies"}},metadata=metadata,warnings=list(analysis.warnings))

def derive_effective_mass(source, *, carrier="electron", edge_name=None, fit_points=5, band_index=None):
    analysis=analyze_band_edges(source); requested=str(edge_name or carrier).upper(); use_cbm=requested in {"CBM","ELECTRON","ELECTRONS"}
    edge=analysis.cbm if use_cbm else analysis.vbm
    if band_index is not None and edge is not None: edge=type(edge)(edge.energy,int(band_index),edge.path_sample_index,edge.path_coordinate,edge.kpoint,edge.spin,edge.label)
    if edge is None:
        return ScientificResult("EffectiveMassResult",ResultStatus.PARTIAL,source.provenance,metadata={"source_band_result_id":source.result_id,"diagnostic":"A defensible sampled band edge is unavailable."},warnings=list(analysis.warnings))
    directions=available_fit_directions(source,edge); direction=directions[0] if directions else None
    fit=fit_effective_mass(source,edge,carrier="CBM" if use_cbm else "VBM",points_each_side=int(fit_points),direction=direction)
    metadata={"source_band_result_id":source.result_id,"carrier":"electron" if use_cbm else "hole","edge":_edge(edge),"fit_status":fit.status,"fit_range_Ainv":fit.k_range,"fit_residual":None if fit.r_squared is None else 1.0-fit.r_squared,"direction":fit.direction,"sample_count":fit.sample_count,"diagnostic":"; ".join(fit.warnings)}
    scalars={} if fit.mass_me is None else {"effective_mass": {"value":fit.mass_me,"unit":"m_e"},"curvature":{"value":fit.curvature,"unit":"eV A^2"},"r_squared":{"value":fit.r_squared,"unit":""}}
    arrays={"k_distance_Ainv":np.asarray(fit.sample_distances),"energy_eV":np.asarray(fit.sample_energies),"fit_energy_eV":np.asarray(fit.fitted_energies)}
    return ScientificResult("EffectiveMassResult",ResultStatus.VALID if fit.status=="VALID" else ResultStatus.PARTIAL,source.provenance,scalars=scalars,arrays=arrays,metadata=metadata,warnings=list(fit.warnings))

def derive_charge_transfer(source):
    q=np.asarray(source.arrays.get("net_charge",()),dtype=float)
    species=list(source.metadata.get("species",()))
    if not len(q) or not np.all(np.isfinite(q)): raise ValueError("Bader Result has no finite net atomic charges.")
    totals={name:float(q[[i for i,item in enumerate(species) if item==name]].sum()) for name in sorted(set(species))}
    return ScientificResult("ChargeTransferResult",ResultStatus.VALID,source.provenance,arrays={"atom_index":np.asarray(source.arrays.get("atom_index",np.arange(1,len(q)+1))),"charge_transfer":q,"transfer":q},metadata={"source_bader_result_id":source.result_id,"species":species,"species_transfer":totals,"sign_convention":"positive = electron deficiency; negative = electron accumulation","total_transfer":float(q.sum())})


def derive_magnetic_moments(lowdin, ground_state=None):
    population=np.asarray(lowdin.arrays.get("population",()),dtype=float)
    moments=np.asarray(lowdin.arrays.get("spin_difference",()),dtype=float)
    atom_indices=np.asarray(lowdin.arrays.get("atom_index",np.arange(1,len(population)+1)))
    unique=[]; local=[]
    for atom in atom_indices:
        if atom in unique: continue
        unique.append(atom); vals=moments[atom_indices==atom] if len(moments)==len(atom_indices) else np.asarray(())
        local.append(float(np.nansum(vals)) if len(vals) and np.any(np.isfinite(vals)) else np.nan)
    scalars={}
    if ground_state is not None:
        for key in ("total_magnetization","absolute_magnetization"):
            if key in ground_state.scalars: scalars[key]=dict(ground_state.scalars[key])
    has_spin=bool(local) and np.all(np.isfinite(local))
    warnings=[] if has_spin else ["QE projwfc output did not provide complete spin-resolved Lowdin populations; projected local moments are unavailable."]
    return ScientificResult("MagneticMomentResult",ResultStatus.VALID if has_spin else ResultStatus.PARTIAL,lowdin.provenance,scalars=scalars,arrays={"atom_index":np.asarray(unique,dtype=int),"projected_local_moment":np.asarray(local,dtype=float)},metadata={"source_lowdin_result_id":lowdin.result_id,"source_ground_state_result_id":None if ground_state is None else ground_state.result_id,"species":[lowdin.metadata.get("species",[])[list(atom_indices).index(atom)] if atom in atom_indices else "" for atom in unique],"projection_basis":"QE projwfc.x Lowdin projections","spin_treatment":(lowdin.metadata.get("electronic_method") or {}).get("spin_treatment","SCALAR_NONSPIN"),"moment_definition":"N_up - N_down (projected local magnetic moment; electron-spin convention)","population_reference":population.tolist()},warnings=warnings)
