from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import hashlib
@dataclass(frozen=True)
class PseudoIdentity:
 provider_id: str
 provider_version: str
 collection: str
 element: str
 filename: str
 sha256: str
class PseudoType(str,Enum): NC="NC"; USPP="USPP"; PAW="PAW"; UNKNOWN="UNKNOWN"
class Relativity(str,Enum): NONRELATIVISTIC="NONRELATIVISTIC"; SCALAR_RELATIVISTIC="SCALAR_RELATIVISTIC"; FULLY_RELATIVISTIC="FULLY_RELATIVISTIC"; UNKNOWN="UNKNOWN"
@dataclass(frozen=True)
class PseudoPotentialRecord:
 element:str; path:str; sha256:str; xc_functional:str="unknown"; pseudo_type:PseudoType=PseudoType.UNKNOWN; relativity:Relativity=Relativity.UNKNOWN; has_spin_orbit:bool=False; z_valence:float|None=None; recommended_ecutwfc_ry:float|None=None; recommended_ecutrho_ry:float|None=None; library_id:str="local"; library_version:str=""; upf_version:str=""; collection:str=""; original_source:str=""
 @property
 def filename(self): return Path(self.path).name
 @property
 def identity(self): return PseudoIdentity(self.library_id,self.library_version,self.collection or self.library_id,self.element,self.filename,self.sha256)
@dataclass(frozen=True)
class PseudoSet:
 records:dict[str,PseudoPotentialRecord]
 def required_missing(self,species): return tuple(sorted(set(species)-set(self.records)))
def sha256(path):
 h=hashlib.sha256()
 with Path(path).open("rb") as f:
  for b in iter(lambda:f.read(65536),b""): h.update(b)
 return h.hexdigest()
