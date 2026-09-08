"""Atomic, resumable installer state and journal contracts."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json, os
from pathlib import Path
from typing import Mapping

class InstallerPhase(str, Enum):
    NOT_STARTED="NOT_STARTED"; CHECK_HOST="CHECK_HOST"; CHECK_PREREQUISITES="CHECK_PREREQUISITES"; ENABLE_PREREQUISITES="ENABLE_PREREQUISITES"; REBOOT_REQUIRED="REBOOT_REQUIRED"; RESUME_AFTER_REBOOT="RESUME_AFTER_REBOOT"; INSTALL_APPLICATION="INSTALL_APPLICATION"; VERIFY_APPLICATION="VERIFY_APPLICATION"; IMPORT_RUNTIME="IMPORT_RUNTIME"; VERIFY_RUNTIME="VERIFY_RUNTIME"; INSTALL_ENGINE_PACK="INSTALL_ENGINE_PACK"; VERIFY_ENGINE_PACK="VERIFY_ENGINE_PACK"; CREATE_SHELL_INTEGRATION="CREATE_SHELL_INTEGRATION"; FINAL_VERIFY="FINAL_VERIFY"; COMPLETED="COMPLETED"; FAILED="FAILED"; REPAIR_REQUIRED="REPAIR_REQUIRED"; UNINSTALLING="UNINSTALLING"; UNINSTALLED="UNINSTALLED"

TERMINAL_PHASES=frozenset({InstallerPhase.COMPLETED,InstallerPhase.FAILED,InstallerPhase.REPAIR_REQUIRED,InstallerPhase.UNINSTALLED})
def now() -> str: return datetime.now(timezone.utc).isoformat()

@dataclass
class InstallerState:
    schema_version: int=1; installation_id: str=""; phase: InstallerPhase=InstallerPhase.NOT_STARTED; app_version: str=""; runtime_version: str=""; engine_pack_version: str=""; reboot_required: bool=False; resume_registered: bool=False; repair_required: bool=False; diagnostics: list[str]=field(default_factory=list); journal: list[dict]=field(default_factory=list); updated_at: str=""
    def transition(self, phase: InstallerPhase, *, detail: str="", rollback: str="") -> None:
        self.phase=InstallerPhase(phase); self.updated_at=now()
        entry={"phase":self.phase.value,"timestamp":self.updated_at,"result":"ENTERED","diagnostic":detail,"rollback":rollback}
        self.journal.append(entry)
        if detail: self.diagnostics.append(detail)
    def finish_phase(self, *, detail: str="") -> None:
        if self.journal: self.journal[-1].update({"result":"COMPLETED","finished_at":now(),"diagnostic":detail or self.journal[-1].get("diagnostic","")})
    def fail(self, detail: str, *, repair: bool=False) -> None:
        self.repair_required=repair; self.transition(InstallerPhase.REPAIR_REQUIRED if repair else InstallerPhase.FAILED,detail=detail); self.finish_phase(detail=detail)
    def to_dict(self):
        value=asdict(self); value["phase"]=self.phase.value; return value
    @classmethod
    def from_dict(cls,value):
        if not isinstance(value,dict) or value.get("schema_version") != 1: raise ValueError("Installer state schema is unsupported.")
        value=dict(value)
        allowed=set(cls.__dataclass_fields__)
        if set(value) - allowed: raise ValueError("Installer state contains unknown fields.")
        value["phase"]=InstallerPhase(value.get("phase",InstallerPhase.NOT_STARTED.value))
        defaults=cls()
        return cls(**{key:value.get(key,getattr(defaults,key)) for key in allowed})


def installer_state_root(*, environ: Mapping[str, str] | None = None,
                         fallback: str | Path | None = None) -> Path:
    """Return ProgramData-owned continuation state, never CWD or temporary state."""
    values=dict(os.environ if environ is None else environ)
    if values.get("PROGRAMDATA"): return Path(values["PROGRAMDATA"]) / "QuantumStudio" / "installer"
    if fallback is not None: return Path(fallback) / "QuantumStudio" / "installer"
    return Path("C:/ProgramData") / "QuantumStudio" / "installer"

class InstallerStateStore:
    """ProgramData-owned atomic continuation state; never CWD or temp state."""
    filename="installer-state.json"
    def __init__(self,root: str|Path): self.root=Path(root); self.path=self.root/self.filename
    def load(self) -> InstallerState|None:
        try: return InstallerState.from_dict(json.loads(self.path.read_text(encoding="utf-8")))
        except FileNotFoundError: return None
        except (OSError,json.JSONDecodeError,ValueError) as error: raise ValueError("Installer continuation state is corrupt; manual repair is required.") from error
    def save(self,state: InstallerState) -> None:
        self.root.mkdir(parents=True,exist_ok=True); temporary=self.path.with_name(self.path.name+".tmp")
        with temporary.open("w",encoding="utf-8") as stream: json.dump(state.to_dict(),stream,sort_keys=True,indent=2); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary,self.path)
    def clear(self) -> None:
        try:self.path.unlink()
        except FileNotFoundError:pass
