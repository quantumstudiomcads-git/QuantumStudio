"""Qt-free, validated DFT functional registry for QE input generation."""
from dataclasses import dataclass
@dataclass(frozen=True)
class XCFunctional:
 id:str; display_name:str; family:str; qe_input_dft:str; hybrid:bool=False; semilocal_parent:str=""; exx_fraction:float|None=None; screening:float|None=None
FUNCTIONALS={x.id:x for x in (
 XCFunctional("pz","Perdew-Zunger LDA","LDA","PZ"),XCFunctional("pbe","PBE","GGA","PBE"),XCFunctional("pw91","PW91","GGA","PW91"),XCFunctional("blyp","BLYP","GGA","BLYP"),XCFunctional("hse06","HSE06","Hybrid","HSE",True,"pbe",.25,.106),XCFunctional("b3lyp","B3LYP","Hybrid","B3LYP",True,"blyp",.20,None))}
def resolve(value):
 key={"hse":"hse06","lda":"pz"}.get(str(value or "pbe").lower(),str(value or "pbe").lower())
 if key not in FUNCTIONALS: raise ValueError("Select an explicit functional; GGA is a family, not a QE functional identifier.")
 return FUNCTIONALS[key]
def hybrid_capability(functional, calculation_ids):
 f=resolve(functional)
 if not f.hybrid:return "SUPPORTED"
 if set(calculation_ids)&{"phonons","phonon_dos","phonon_band_structure","electron_phonon"}: return "UNSUPPORTED_BY_QE_PHONON"
 if set(calculation_ids)&{"wannierization","dos","pdos","boltztrap_bands","electrical_conductivity","seebeck","thermal_conductivity_electronic","carrier_concentration"}: return "NOT_YET_IMPLEMENTED"
 return "SUPPORTED"
