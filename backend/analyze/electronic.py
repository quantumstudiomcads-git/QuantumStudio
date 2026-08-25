"""Conservative derived electronic analysis over structured BandStructureResult data."""
from __future__ import annotations
from dataclasses import dataclass, field
import math
import numpy as np

TOLERANCE=1e-6
@dataclass(frozen=True)
class BandEdge:
    energy: float; band_index: int; path_sample_index: int; path_coordinate: float|None=None
    kpoint: tuple[float,...]|None=None; spin: str|None=None; label: str|None=None
@dataclass(frozen=True)
class BandGapAnalysis:
    status: str; gap_scope: str="sampled_path"; gap: float|None=None; classification: str="UNRESOLVED"
    vbm: BandEdge|None=None; cbm: BandEdge|None=None; degenerate_vbm: tuple[BandEdge,...]=(); degenerate_cbm: tuple[BandEdge,...]=()
    warnings: tuple[str,...]=()
@dataclass(frozen=True)
class EffectiveMassFit:
    status: str; edge: str; mass_me: float|None=None; curvature: float|None=None; coefficients: tuple[float,...]=()
    r_squared: float|None=None; sample_count: int=0; k_range: tuple[float,float]|None=None; direction: str=""; warnings: tuple[str,...]=()
@dataclass(frozen=True)
class ElectronicAnalysisResult:
    gap: BandGapAnalysis; fits: tuple[EffectiveMassFit,...]=(); result_id: str=""

def _scalar(result,key):
    value=result.metadata.get(key)
    if value is None:value=result.scalars.get(key)
    if isinstance(value,dict):value=value.get("value")
    return value

def _bands(result):
    values=result.arrays.get("energies", result.arrays.get("energy"))
    if values is None:return None
    a=np.asarray(values,dtype=float); return a[:,None] if a.ndim==1 else a

def _kpoints(result,n):
    value=result.arrays.get("kpoints", result.metadata.get("kpoints"))
    if value is None:return [None]*n
    a=np.asarray(value,dtype=float); return [tuple(row.tolist()) for row in a[:n]]

def _occupied_mask(result, shape):
    occ=result.metadata.get("occupations", result.arrays.get("occupations"))
    if occ is not None:
        a=np.asarray(occ); return a>0.5, None
    count=result.metadata.get("occupied_band_count", result.metadata.get("n_occupied"))
    if count is not None:
        c=int(count); mask=np.zeros(shape,bool); mask[:,:min(c,shape[1])]=True; return mask,None
    if result.metadata.get("metallic") is True:return None,"METALLIC"
    return None,"UNRESOLVED_OCCUPANCY"

def analyze_band_edges(result, *, tolerance=TOLERANCE):
    bands=_bands(result)
    if bands is None:return BandGapAnalysis("UNRESOLVED_OCCUPANCY",warnings=("Band energies are unavailable.",))
    mask,reason=_occupied_mask(result,bands.shape)
    if reason:return BandGapAnalysis(reason,warnings=("Occupied and unoccupied bands cannot be identified from stored metadata.",))
    if np.any(mask & ~mask): return BandGapAnalysis("UNRESOLVED_OCCUPANCY")
    if not np.any(mask) or not np.any(~mask):return BandGapAnalysis("UNRESOLVED_OCCUPANCY")
    if np.any((bands>0)&(bands<1e-12)): pass
    occupied=np.where(mask,bands,np.nan); unoccupied=np.where(~mask,bands,np.nan)
    vmax=float(np.nanmax(occupied)); cmin=float(np.nanmin(unoccupied));
    kpoints=_kpoints(result,bands.shape[0]); path=result.arrays.get("path_coordinate",np.arange(bands.shape[0])); labels=result.metadata.get("path_labels",{})
    def edge(value, band_index, sample):
        label=labels.get(str(sample),labels.get(sample)) if isinstance(labels,dict) else None
        return BandEdge(value,band_index,sample,float(path[sample]) if sample<len(path) else None,kpoints[sample],None,label)
    vi=np.argwhere(np.isclose(occupied,vmax,atol=tolerance)); ci=np.argwhere(np.isclose(unoccupied,cmin,atol=tolerance))
    v=edge(vmax,int(vi[0,1]),int(vi[0,0])); c=edge(cmin,int(ci[0,1]),int(ci[0,0]))
    dv=tuple(edge(float(bands[i,j]),int(j),int(i)) for i,j in vi); dc=tuple(edge(float(bands[i,j]),int(j),int(i)) for i,j in ci)
    gap=cmin-vmax
    if gap < -tolerance:return BandGapAnalysis("METALLIC",gap_scope="sampled_path",gap=None,vbm=v,cbm=c,degenerate_vbm=dv,degenerate_cbm=dc,warnings=("Occupied and unoccupied states overlap on the sampled path.",))
    if abs(gap)<=tolerance: cls="ZERO_GAP"
    else:
        direct=False
        if v.kpoint is not None and c.kpoint is not None: direct=bool(np.allclose(np.asarray(v.kpoint)-np.asarray(c.kpoint),np.round(np.asarray(v.kpoint)-np.asarray(c.kpoint)),atol=tolerance))
        else: direct=v.path_sample_index==c.path_sample_index
        cls="DIRECT_SAMPLED_PATH" if direct else "INDIRECT_SAMPLED_PATH"
    return BandGapAnalysis("VALID",str(result.metadata.get("gap_scope","sampled_path")),float(max(0,gap)),cls,v,c,dv,dc)

def fit_effective_mass(result, edge: BandEdge, *, points_each_side=5, cell=None, tolerance=TOLERANCE):
    bands=_bands(result)
    if bands is None:return EffectiveMassFit("UNAVAILABLE", "CBM", warnings=("Band energies unavailable.",))
    cell=cell or result.metadata.get("cell") or result.provenance.__dict__.get("cell")
    if cell is None:return EffectiveMassFit("UNAVAILABLE","CBM",warnings=("A valid real-space cell is required for reciprocal-distance fitting.",))
    try: reciprocal=2*np.pi*np.linalg.inv(np.asarray(cell,dtype=float)).T
    except Exception:return EffectiveMassFit("UNAVAILABLE","CBM",warnings=("Cell metadata is invalid.",))
    k=_kpoints(result,bands.shape[0]);
    if any(point is None for point in k):return EffectiveMassFit("UNAVAILABLE","CBM",warnings=("Cartesian reciprocal k-points are unavailable.",))
    i=edge.path_sample_index; lo=max(0,i-points_each_side); hi=min(len(k),i+points_each_side+1); indices=[j for j in range(lo,hi) if j!=i]
    if len(indices)<3:return EffectiveMassFit("INSUFFICIENT_POINTS", "CBM",warnings=("At least three neighboring samples are required.",))
    center=np.asarray(k[i]); distances=np.array([np.linalg.norm((np.asarray(k[j])-center)@reciprocal) for j in indices]); energies=np.array([bands[j,edge.band_index] for j in indices]);
    if np.any(distances<=tolerance):return EffectiveMassFit("UNAVAILABLE","CBM",warnings=("Reciprocal-distance samples are degenerate.",))
    coeff=np.polyfit(distances,energies,2); predicted=np.polyval(coeff,distances); ssr=float(np.sum((energies-predicted)**2)); sst=float(np.sum((energies-np.mean(energies))**2)); r2=1-ssr/sst if sst>0 else 1.0; hbar=1.054571817e-34; electron=9.1093837015e-31; ev=1.602176634e-19; curvature=2*coeff[0]; mass=hbar*hbar/(curvature*ev*1e-20) / electron if curvature else None
    if edge.energy <= float(np.min(energies))+tolerance: mass=abs(mass) if mass is not None else None
    warning=("Poor parabolic fit.",) if r2<0.98 else ()
    return EffectiveMassFit("VALID", "CBM", mass,curvature,tuple(float(x) for x in coeff),r2,len(indices),(float(distances.min()),float(distances.max())),"local reciprocal direction",warning)
