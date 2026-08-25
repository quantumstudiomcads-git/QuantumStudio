from dataclasses import dataclass
from typing import Mapping, Sequence
class InvalidEPWSettingsError(ValueError): pass
class EPWMeshMismatchError(InvalidEPWSettingsError): pass
@dataclass(frozen=True)
class EPWSettings:
 nk_coarse: tuple[int,int,int]; nq_coarse: tuple[int,int,int]; nk_fine: tuple[int,int,int]; nq_fine: tuple[int,int,int]
 @classmethod
 def from_parameters(cls,p:Mapping):
  keys=('nk_coarse','nq_coarse','nk_fine','nq_fine'); missing=[k for k in keys if k not in p]
  if missing: raise InvalidEPWSettingsError('electron_phonon requires '+', '.join(missing)+'.')
  def mesh(k):
   v=p[k]
   if not isinstance(v,Sequence) or len(v)!=3: raise InvalidEPWSettingsError(k+' must contain three positive integers.')
   v=tuple(int(x) for x in v)
   if any(x<1 for x in v): raise InvalidEPWSettingsError(k+' must be positive.')
   return v
  return cls(*(mesh(k) for k in keys))
