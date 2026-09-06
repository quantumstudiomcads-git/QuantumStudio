from dataclasses import dataclass, fields
from typing import Mapping, Sequence
import hashlib
import json
class InvalidEPWSettingsError(ValueError): pass
class EPWMeshMismatchError(InvalidEPWSettingsError): pass
class EPWCapabilityError(InvalidEPWSettingsError): pass
@dataclass(frozen=True)
class EPWSettings:
 nk_coarse: tuple[int,int,int]; nq_coarse: tuple[int,int,int]; nk_fine: tuple[int,int,int]; nq_fine: tuple[int,int,int]
 nbndsub: int = 4; fsthick_ev: float = 6.0; degaussw_ev: float = 0.05; degaussq_mev: float = 0.05
 a2f: bool = True; eliashberg: bool = False; tc_linear: bool = False; mu_star: float = 0.10
 tc_linear_solver: str = "power"
 auto_projections: bool = False; scdm_proj: bool = False; scdm_entanglement: str = ""; scdm_mu_eV: float | None = None; scdm_sigma_eV: float | None = None
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
  solver=str(p.get("tc_linear_solver","power")).lower()
  if solver not in {"power","lapack"}: raise InvalidEPWSettingsError("tc_linear_solver must be power or lapack.")
  nbndsub=int(p.get("nbndsub",p.get("num_wann",4)))
  if nbndsub < 1: raise InvalidEPWSettingsError("nbndsub must be positive.")
  mu=float(p.get("mu_star",0.10))
  if not 0 <= mu < 1: raise InvalidEPWSettingsError("mu_star must be in [0,1).")
  return cls(*(mesh(k) for k in keys), nbndsub, float(p.get("fsthick",6.0)), float(p.get("degaussw",0.05)), float(p.get("degaussq",0.05)), bool(p.get("a2f",True)), bool(p.get("eliashberg",False)), bool(p.get("tc_linear",False)) , mu, solver, bool(p.get("auto_projections",False)), bool(p.get("scdm_proj",False)), str(p.get("scdm_entanglement","")).lower(), p.get("scdm_mu"), p.get("scdm_sigma"))


@dataclass(frozen=True)
class EPWCoarseState:
    """Compatibility identity for expensive SCF/DFPT/NSCF/Wannier EPW state."""
    structure_fingerprint: str
    pseudo_sha256: tuple[str, ...]
    functional: str
    cutoffs: tuple[float, float]
    scf_mesh: tuple[int, int, int]
    coarse_k_mesh: tuple[int, int, int]
    coarse_q_mesh: tuple[int, int, int]
    nbnd: int
    nbndsub: int
    projections: tuple[str, ...]
    windows: tuple[float | None, ...] = ()
    collector_identity: str = ""
    ifc_identity: str = ""
    ukk_identity: str = ""
    engine_family: str = ""
    epw_version: str = "6.1"
    wannier_version: str = ""
    electronic_grid_mode: str = "SYMMETRY_REDUCED"
    explicit_kpoint_count: int | None = None
    electronic_smearing: tuple[str, float] = ("", 0.0)
    wannier_subspace_method: str = "ENERGY_DISENTANGLEMENT"
    projector_source: str = ""
    projector_normalization: str = ""
    projectability_threshold_mode: str = ""
    projectability_thresholds: tuple[float | None, float | None] = (None, None)
    scdm_fit_identity: str = ""
    scdm_fit_quality: tuple[float, ...] = ()
    scdm_mu_eV: float | None = None
    scdm_sigma_eV: float | None = None
    dis_num_iter: int = 0
    auto_projections: bool = False
    scdm_proj: bool = False
    scdm_entanglement: str = ""
    use_ws_distance: bool = False

    def to_dict(self) -> dict[str, object]:
        result = {}
        for item in fields(self):
            value = getattr(self, item.name)
            result[item.name] = list(value) if isinstance(value, tuple) else value
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "EPWCoarseState":
        if not isinstance(value, Mapping):
            raise ValueError("EPW coarse state must be a mapping.")
        names = {item.name for item in fields(cls)}
        data = {name: value[name] for name in names if name in value}
        for name in ("pseudo_sha256", "scf_mesh", "coarse_k_mesh", "coarse_q_mesh", "projections", "windows", "projectability_thresholds", "scdm_fit_quality", "electronic_smearing"):
            if name in data and isinstance(data[name], list):
                data[name] = tuple(data[name])
        return cls(**data)

    @property
    def identity(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def compatible_for(self, candidate: "EPWCoarseState") -> bool:
        """Fine-grid/runtime changes are intentionally outside this identity."""
        return self == candidate
