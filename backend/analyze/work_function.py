"""Qt-free slab electrostatics and conservative work-function derivation."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from backend.results.models import ScientificResult,ResultStatus
from backend.results.parsers import RY_TO_EV

@dataclass(frozen=True)
class VacuumLevel:
 side:str; start_fractional:float; end_fractional:float; width_A:float; level_eV:float; std_eV:float; peak_to_peak_eV:float; slope_eV_per_A:float; valid:bool; selection_mode:str="AUTOMATIC"

def slab_axis(periodic, override=None):
 if override is not None:
  axis={"X":0,"Y":1,"Z":2}.get(str(override).upper())
  if axis is None: raise ValueError("Surface-normal override must be X, Y, or Z.")
  return axis
 p=[bool(x) for x in periodic]
 if len(p)!=3 or p.count(False)!=1: raise ValueError("Work function requires exactly one non-periodic slab direction or an explicit axis override.")
 return p.index(False)

def planar_potential(result, axis):
 from backend.results.volumetric import field_profile
 profile=field_profile(result,"XYZ"[axis]); raw=np.asarray(profile["values"],float); return {**profile,"potential_raw_Ry":raw,"potential_eV":raw*RY_TO_EV,"source_result_id":result.result_id}

def macroscopic_average(profile,window_A):
 values=np.asarray(profile["potential_eV"],float); distance=np.asarray(profile["distance_A"],float)
 if len(values)<3: return values.copy()
 step=float(np.mean(np.diff(distance)))
 if not np.isfinite(window_A) or window_A<=0: raise ValueError("Macroscopic window must be a positive physical length in Å.")
 count=max(1,int(round(float(window_A)/step))); count += 1-count%2
 if count>=len(values): raise ValueError("Macroscopic window is wider than the available profile.")
 pad=count//2; return np.convolve(np.pad(values,pad,mode="wrap"),np.full(count,1/count),mode="valid")

def _vacuum_mask(atoms,cell,axis,count,margin_A=1.2):
 length=float(np.linalg.norm(np.asarray(cell,float)[axis])); margin=float(margin_A)/length
 if not atoms: return np.ones(count,dtype=bool)
 coordinates=np.asarray([[float(a[k]) for k in ("x","y","z")] for a in atoms],float); fractional=np.matmul(coordinates,np.linalg.inv(np.asarray(cell,float))); centers=np.mod(fractional[:,axis],1.0); grid=np.arange(count)/count
 distance=np.min(np.abs(((grid[:,None]-centers[None,:]+.5)%1)-.5),axis=1); return distance>margin

def _longest_circular(mask):
 n=len(mask); doubled=np.concatenate([mask,mask]); best=(0,0); start=None
 for i,value in enumerate(doubled):
  if value and start is None: start=i
  if not value and start is not None:
   length=i-start
   if length<=n and length>best[1]: best=(start,length)
   start=None
 if start is not None:
  length=len(doubled)-start
  if length<=n and length>best[1]: best=(start,length)
 return best

def find_vacuum_level(profile,atoms,cell,axis,minimum_width_A=5.0,max_std_eV=.05,max_slope_eV_per_A=.02,manual_interval=None):
 values=np.asarray(profile["potential_eV"],float); n=len(values); length=float(np.linalg.norm(np.asarray(cell,float)[axis]))
 if manual_interval is not None:
  a,b=(float(x)%1 for x in manual_interval); indices=np.arange(n)[((np.arange(n)/n-a)%1)<((b-a)%1)] if a!=b else np.arange(n)
  mode="MANUAL"
 else:
  start,width=_longest_circular(_vacuum_mask(atoms,cell,axis,n));
  if width==0: return None,"No atom-free vacuum interval was found."
  # use the central 60 percent to avoid atom-boundary spillover
  trim=max(0,int(round(width*.2))); indices=(np.arange(start+trim,start+width-trim)%n); mode="AUTOMATIC"
 if len(indices)<3: return None,"Vacuum candidate has too few profile samples."
 width_A=len(indices)/n*length
 if width_A<minimum_width_A: return None,f"Vacuum region is too narrow ({width_A:.3g} Å < {minimum_width_A:.3g} Å)."
 sample=values[indices]; local=np.arange(len(indices))/n*length; slope=float(np.polyfit(local,sample,1)[0]); std=float(np.std(sample)); spread=float(np.ptp(sample)); valid=std<=max_std_eV and abs(slope)<=max_slope_eV_per_A
 start_fractional=float(indices[0]/n); end_fractional=float((indices[-1]+1)/n%1); level=VacuumLevel("shared",start_fractional,end_fractional,width_A,float(np.mean(sample)),std,spread,slope,valid,mode)
 if not valid: return level,"Vacuum potential is not sufficiently flat for a reliable work-function estimate."
 return level,""

def derive_work_function(potential,scf,atoms,*,axis_override=None,window_A=None,manual_interval=None,minimum_width_A=5.0,max_std_eV=.05,max_slope_eV_per_A=.02):
 if potential.result_type!="VolumetricResult" or potential.metadata.get("quantity_kind")!="ELECTROSTATIC_POTENTIAL": raise ValueError("Work function requires an electrostatic-potential VolumetricResult.")
 if scf.status is not ResultStatus.VALID: return {"status":ResultStatus.NOT_CONVERGED,"diagnostics":["Parent SCF is not scientifically valid."]}
 fermi=(scf.scalars.get("fermi_energy") or {}).get("value")
 if fermi is None: return {"status":ResultStatus.PARTIAL,"diagnostics":["Work function requires a Fermi/chemical-potential reference from the same electronic calculation."]}
 if potential.provenance.execution_id!=scf.provenance.execution_id or potential.provenance.request_id!=scf.provenance.request_id: raise ValueError("Potential and Fermi reference do not originate from the same electronic state.")
 a=potential.metadata.get("workflow_provenance",{}).get("structure_fingerprint",potential.provenance.structure_fingerprint); b=scf.metadata.get("workflow_provenance",{}).get("structure_fingerprint",scf.provenance.structure_fingerprint)
 if a and b and a!=b: raise ValueError("Potential and Fermi reference have different structure fingerprints.")
 method_p=potential.metadata.get("electronic_method",{}); method_s=scf.metadata.get("electronic_method",{});
 if method_p and method_s and method_p!=method_s: raise ValueError("Potential and Fermi reference have different electronic-method metadata.")
 if float(scf.metadata.get("tot_charge",0) or 0)!=0: return {"status":ResultStatus.PARTIAL,"diagnostics":["Automatic work function is blocked for a net-charged slab."]}
 axis=slab_axis(potential.metadata.get("periodic",[]),axis_override); profile=planar_potential(potential,axis); macro=None if window_A is None else macroscopic_average(profile,window_A); analysis_profile=dict(profile);
 if macro is not None: analysis_profile["potential_eV"]=macro
 level,diagnostic=find_vacuum_level(analysis_profile,atoms,potential.metadata["cell"],axis,minimum_width_A,max_std_eV,max_slope_eV_per_A,manual_interval)
 if level is None: return {"status":ResultStatus.PARTIAL,"profile":profile,"diagnostics":[diagnostic],"axis":"XYZ"[axis]}
 status=ResultStatus.VALID if level.valid else ResultStatus.PARTIAL; value=level.level_eV-float(fermi) if level.valid else None
 return {"status":status,"profile":profile,"macroscopic_eV":macro,"axis":"XYZ"[axis],"fermi_energy_eV":float(fermi),"vacuum_levels":[level],"work_functions_eV":[] if value is None else [value],"diagnostics":[] if level.valid else [diagnostic],"selection_mode":level.selection_mode}

