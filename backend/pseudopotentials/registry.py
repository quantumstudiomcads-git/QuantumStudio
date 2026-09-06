import json
from dataclasses import dataclass, replace
from pathlib import Path
from .models import PseudoType, Relativity
from .upf import inspect_upf

PROVIDER_LIBRARY_IDS = ("sssp_efficiency", "sssp_precision", "pseudodojo", "pslibrary", "sg15", "gbrv", "qe_official", "local")

@dataclass(frozen=True)
class PseudoLibrary:
 library_id:str; display_name:str; root:str; version:str=""

class PseudoLibraryRegistry:
 def __init__(self): self._libraries={}; self._records={}
 def register(self,library):
  if library.library_id in self._libraries: raise ValueError("Duplicate pseudo library.")
  self._libraries[library.library_id]=library
 def unregister(self,library_id):
  self._records.pop(library_id,None); return self._libraries.pop(library_id,None)
 def libraries(self): return tuple(self._libraries[key] for key in sorted(self._libraries))
 def records(self,library_id=None):
  if library_id is not None: return self._records.get(library_id,())
  return tuple(record for key in sorted(self._records) for record in self._records[key])
 def index(self,library_id):
  lib=self._libraries[library_id]; root=Path(lib.root)
  if not root.is_dir(): raise ValueError("Pseudopotential library root is not a directory.")
  records=[]
  for path in sorted(root.rglob("*")):
   if path.is_file() and path.suffix.lower()==".upf":
    if len(records)>=10000: raise ValueError("Pseudopotential library exceeds the 10,000-file index limit.")
    records.append(inspect_upf(path,library_id,lib.version))
  self._records[library_id]=tuple(records); return tuple(records)
 def index_manifest(self,library_id,manifest_path):
  """Index an installed provider pack using its local JSON metadata."""
  lib=self._libraries[library_id]; root=Path(lib.root).resolve(); data=json.loads(Path(manifest_path).read_text(encoding="utf-8"))
  entries=data.get("pseudopotentials", data) if isinstance(data,dict) else data
  if not isinstance(entries,list): raise ValueError("Pseudopotential manifest must contain a list of records.")
  records=[]
  for entry in entries:
   if not isinstance(entry,dict) or not isinstance(entry.get("filename"),str): raise ValueError("Pseudopotential manifest entry requires filename.")
   path=(root/entry["filename"]).resolve()
   if root not in path.parents: raise ValueError("Pseudopotential manifest path escapes its library root.")
   record=inspect_upf(path,library_id,lib.version)
   expected=entry.get("sha256") or entry.get("checksum")
   if expected and str(expected).lower()!=record.sha256: raise ValueError(f"Checksum mismatch for {entry["filename"]}.")
   records.append(replace(record, recommended_ecutwfc_ry=float(entry.get("cutoff_wfc",entry.get("ecutwfc",record.recommended_ecutwfc_ry))) if entry.get("cutoff_wfc",entry.get("ecutwfc")) is not None else record.recommended_ecutwfc_ry, recommended_ecutrho_ry=float(entry.get("cutoff_rho",entry.get("ecutrho",record.recommended_ecutrho_ry))) if entry.get("cutoff_rho",entry.get("ecutrho")) is not None else record.recommended_ecutrho_ry))
  self._records[library_id]=tuple(records); return tuple(records)
 def find(self,element=None,xc=None,pseudo_type=None,relativity=None):
  pseudo_type=PseudoType(pseudo_type) if pseudo_type is not None else None
  relativity=Relativity(relativity) if relativity is not None else None
  return tuple(r for r in self.records() if (element is None or r.element==element) and (xc is None or r.xc_functional==xc) and (pseudo_type is None or r.pseudo_type is pseudo_type) and (relativity is None or r.relativity is relativity))
