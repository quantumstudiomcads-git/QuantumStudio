import re
from pathlib import Path
from .models import PseudoPotentialRecord,PseudoType,Relativity,sha256
class UPFMetadataError(ValueError): pass
def inspect_upf(path,library_id="local",library_version=""):
 p=Path(path)
 try: text=p.read_text(errors="replace")[:65536]
 except OSError as e: raise UPFMetadataError(str(e))
 def attr(*names):
  for n in names:
   quoted=re.search(rf"{n}\s*=\s*['\"]\s*([^'\"]*?)\s*['\"]",text,re.I)
   if quoted:return quoted.group(1).strip()
   m=re.search(rf"{n}\s*=\s*([^\s>]+)",text,re.I)
   if m:return m.group(1)
  return None
 element=attr("element","pseudo_element")
 if not element:
  legacy=re.search(r"<PP_HEADER>\s*(.*?)</PP_HEADER>",text,re.I|re.S)
  legacy_text=legacy.group(1) if legacy else ""
  match=re.search(r"^\s*([A-Z][a-z]?)\s+Element",legacy_text,re.I|re.M)
  if match: element=match.group(1).title()
 if not element: raise UPFMetadataError("UPF element metadata is missing.")
 xc_value=attr("functional","dft","functional_type")
 if not xc_value and legacy:
  functional_line=next((line for line in legacy_text.splitlines() if "functional" in line.lower()),"")
  xc_value=next((name for name in ("PBE","PW91","BLYP","PZ","LDA") if name in functional_line.upper()),None)
 xc=(xc_value or "unknown").lower().replace("_","-")
 aliases={"lda":"pz","perdew-zunger":"pz","perdew-zunger-lda":"pz","perdew-burke-ernzerhof":"pbe","pbe":"pbe","pw91":"pw91","perdew-wang-91":"pw91","blyp":"blyp","becke-lee-yang-parr":"blyp"}; xc=aliases.get(xc,xc)
 kind=(attr("pseudo_type","pp_type","is-ultrasoft") or "UNKNOWN").upper()
 if kind == "UNKNOWN" and legacy:
  kind = "USPP" if "ultrasoft pseudopotential" in legacy_text.lower() else "NC" if "norm-conserving" in legacy_text.lower() else "PAW" if "paw pseudopotential" in legacy_text.lower() else "UNKNOWN"
 kind={"US":"USPP","USPP":"USPP","PAW":"PAW","NC":"NC"}.get(kind,PseudoType.UNKNOWN.value)
 rel=(attr("relativistic","relativity") or "unknown").lower()
 if rel == "unknown" and legacy:
  rel = "scalar" if "scalar-relativistic" in text.lower() else "non" if "non-relativistic" in text.lower() else "unknown"
 relativity=Relativity.FULLY_RELATIVISTIC if "full" in rel else Relativity.SCALAR_RELATIVISTIC if "scalar" in rel else Relativity.NONRELATIVISTIC if "non" in rel else Relativity.UNKNOWN
 def number(*names):
  value=attr(*names)
  try:return float(value) if value is not None else None
  except ValueError:return None
 so=(attr("has_so","has_spin_orbit") or "false").lower() in {"t","true",".true.","1"}
 return PseudoPotentialRecord(element,p.resolve().as_posix(),sha256(p),xc,PseudoType(kind),relativity,so,number("z_valence"),number("ecutwfc","cutoff_wfc"),number("ecutrho","cutoff_rho"),library_id,library_version,attr("version") or "")
