from dataclasses import dataclass
from enum import Enum
from .models import Relativity
from backend.dft.functionals import resolve
class CompatibilityState(str,Enum): COMPATIBLE="COMPATIBLE"; COMPATIBLE_SEMILOCAL_PARENT="COMPATIBLE_SEMILOCAL_PARENT"; WARNING_XC_MISMATCH="WARNING_XC_MISMATCH"; WARNING_RELATIVITY="WARNING_RELATIVITY"; MISSING="MISSING"
@dataclass(frozen=True)
class PseudoCompatibility: state:CompatibilityState; reason:str
def compatibility(functional,record,soc=False):
 f=resolve(functional); xc=record.xc_functional
 if f.hybrid and xc==f.semilocal_parent: base=PseudoCompatibility(CompatibilityState.COMPATIBLE_SEMILOCAL_PARENT,f"{f.display_name} uses {xc.upper()} semilocal-parent pseudopotentials.")
 elif xc==f.id or (f.id=="pz" and xc in {"pz","lda"}): base=PseudoCompatibility(CompatibilityState.COMPATIBLE,"XC compatible.")
 else: base=PseudoCompatibility(CompatibilityState.WARNING_XC_MISMATCH,"Pseudopotential XC differs from selected functional.")
 if soc and record.relativity is not Relativity.FULLY_RELATIVISTIC: return PseudoCompatibility(CompatibilityState.WARNING_RELATIVITY,"SOC requested but this species is not fully relativistic.")
 return base
def validate_pseudo_set(functional,soc,species,pseudo_set):
 missing=pseudo_set.required_missing(species); findings={e:compatibility(functional,r,soc) for e,r in pseudo_set.records.items() if e in species}; return missing,findings
def recommended_cutoffs(records):
 w=[r.recommended_ecutwfc_ry for r in records if r.recommended_ecutwfc_ry is not None]; rho=[r.recommended_ecutrho_ry for r in records if r.recommended_ecutrho_ry is not None]; return {"ecutwfc":max(w) if w else None,"ecutrho":max(rho) if rho else None,"complete":len(w)==len(records) and len(rho)==len(records)}
