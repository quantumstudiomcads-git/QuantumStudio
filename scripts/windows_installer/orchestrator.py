"""Deterministic installer orchestration; system mutation is injected and isolated."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol
from .contracts import ComponentAction, ComponentResult, HostAssessment, HostPrerequisite, InstallerPayload, InstallerProfile, MANAGED_RUNTIME_ID
from .state import InstallerPhase, InstallerState, InstallerStateStore

class InstallerBackend(Protocol):
    def assess_host(self)->HostAssessment: ...
    def enable_wsl_prerequisites(self)->HostPrerequisite: ...
    def register_resume(self, installation_id:str)->None: ...
    def remove_resume(self, installation_id:str)->None: ...
    def install_application(self,payload:InstallerPayload)->ComponentResult: ...
    def verify_application(self,payload:InstallerPayload)->ComponentResult: ...
    def ensure_managed_runtime(self,payload:InstallerPayload)->ComponentResult: ...
    def verify_managed_runtime(self)->ComponentResult: ...
    def ensure_engine_pack(self,payload:InstallerPayload)->ComponentResult: ...
    def verify_engine_pack(self)->ComponentResult: ...
    def create_shell_integration(self)->ComponentResult: ...
    def remove_application(self)->ComponentResult: ...
    def remove_shell_integration(self)->ComponentResult: ...
    def remove_managed_runtime_and_data(self)->ComponentResult: ...

@dataclass
class InstallerOrchestrator:
    payload: InstallerPayload
    profile: InstallerProfile
    backend: InstallerBackend
    store: InstallerStateStore
    installation_id: str

    def _save(self,state): self.store.save(state)
    def _enter(self,state,phase,detail="",rollback=""):
        state.transition(phase,detail=detail,rollback=rollback); self._save(state)
    def _complete(self,state,detail=""):
        state.finish_phase(detail=detail); self._save(state)
    def _component(self,state,result:ComponentResult,label:str)->bool:
        if result.action is ComponentAction.OWNERSHIP_CONFLICT:
            state.fail(f"{label}: existing QuantumStudioRuntime ownership is not recognized; destructive action is blocked.",repair=True); self._save(state); return False
        if not result.okay:
            state.fail(f"{label}: {result.detail or 'component operation failed.'}",repair=True); self._save(state); return False
        self._complete(state,result.detail); return True

    def plan(self)->tuple[str,...]:
        host=self.backend.assess_host()
        actions=["CHECK_HOST"]
        if host.supported and host.prerequisite is HostPrerequisite.NEEDS_ENABLEMENT: actions.extend(["ENABLE_WSL_PREREQUISITES","REBOOT_IF_REQUIRED"])
        actions.extend(["INSTALL_APPLICATION","VERIFY_APPLICATION"])
        if self.profile is not InstallerProfile.GUI_ONLY: actions.extend(["IMPORT_RUNTIME","VERIFY_RUNTIME"])
        if self.profile is InstallerProfile.FULL_SCIENTIFIC: actions.extend(["INSTALL_ENGINE_PACK","VERIFY_ENGINE_PACK"])
        actions.extend(["CREATE_SHELL_INTEGRATION","FINAL_VERIFY"]); return tuple(actions)

    def run(self, state:InstallerState|None=None)->InstallerState:
        state=state or self.store.load() or InstallerState(installation_id=self.installation_id)
        try:
            if state.phase is InstallerPhase.REBOOT_REQUIRED:
                self._enter(state,InstallerPhase.RESUME_AFTER_REBOOT,"Resuming installation after required restart.")
                self.backend.remove_resume(state.installation_id); state.resume_registered=False; self._complete(state)
                state.phase=InstallerPhase.CHECK_PREREQUISITES; self._save(state)
            if state.phase in {InstallerPhase.NOT_STARTED,InstallerPhase.CHECK_HOST}:
                self._enter(state,InstallerPhase.CHECK_HOST,"Checking supported Windows host.")
                host=self.backend.assess_host(); host.require_supported(); self._complete(state,host.detail)
                state.phase=InstallerPhase.CHECK_PREREQUISITES; self._save(state)
            if state.phase is InstallerPhase.CHECK_PREREQUISITES:
                self._enter(state,InstallerPhase.CHECK_PREREQUISITES,"Checking compute prerequisites.")
                prerequisite=self.backend.assess_host().prerequisite
                if prerequisite is HostPrerequisite.UNSUPPORTED: raise RuntimeError("Required Windows components are unsupported.")
                if prerequisite is HostPrerequisite.FAILED: raise RuntimeError("Windows prerequisite detection failed.")
                if prerequisite is HostPrerequisite.NEEDS_ENABLEMENT:
                    self._complete(state); state.phase=InstallerPhase.ENABLE_PREREQUISITES; self._save(state)
                elif prerequisite is HostPrerequisite.REBOOT_REQUIRED:
                    self._complete(state); return self._request_reboot(state)
                else: self._complete(state); state.phase=InstallerPhase.INSTALL_APPLICATION; self._save(state)
            if state.phase is InstallerPhase.ENABLE_PREREQUISITES:
                self._enter(state,InstallerPhase.ENABLE_PREREQUISITES,"Preparing required Windows compute components.")
                result=self.backend.enable_wsl_prerequisites()
                if result is HostPrerequisite.REBOOT_REQUIRED: self._complete(state); return self._request_reboot(state)
                if result is not HostPrerequisite.READY: raise RuntimeError("Windows prerequisite enablement failed.")
                self._complete(state); state.phase=InstallerPhase.INSTALL_APPLICATION; self._save(state)
            self.payload.validate(self.profile)
            if state.phase is InstallerPhase.INSTALL_APPLICATION:
                self._enter(state,InstallerPhase.INSTALL_APPLICATION,"Installing Quantum Studio application.","Preserve existing runtime data.")
                if not self._component(state,self.backend.install_application(self.payload),"Application installation"): return state
                state.phase=InstallerPhase.VERIFY_APPLICATION; self._save(state)
            if state.phase is InstallerPhase.VERIFY_APPLICATION:
                self._enter(state,InstallerPhase.VERIFY_APPLICATION,"Verifying Quantum Studio application.")
                if not self._component(state,self.backend.verify_application(self.payload),"Application verification"): return state
                state.phase=InstallerPhase.IMPORT_RUNTIME if self.profile is not InstallerProfile.GUI_ONLY else InstallerPhase.CREATE_SHELL_INTEGRATION; self._save(state)
            if state.phase is InstallerPhase.IMPORT_RUNTIME:
                self._enter(state,InstallerPhase.IMPORT_RUNTIME,"Preparing scientific runtime.","Never remove an unrecognized runtime.")
                if not self._component(state,self.backend.ensure_managed_runtime(self.payload),"Scientific runtime installation"): return state
                state.phase=InstallerPhase.VERIFY_RUNTIME; self._save(state)
            if state.phase is InstallerPhase.VERIFY_RUNTIME:
                self._enter(state,InstallerPhase.VERIFY_RUNTIME,"Verifying compute components.")
                if not self._component(state,self.backend.verify_managed_runtime(),"Scientific runtime verification"): return state
                state.phase=InstallerPhase.INSTALL_ENGINE_PACK if self.profile is InstallerProfile.FULL_SCIENTIFIC else InstallerPhase.CREATE_SHELL_INTEGRATION; self._save(state)
            if state.phase is InstallerPhase.INSTALL_ENGINE_PACK:
                self._enter(state,InstallerPhase.INSTALL_ENGINE_PACK,"Installing verified scientific components.","Preserve previous verified Engine Pack.")
                if not self._component(state,self.backend.ensure_engine_pack(self.payload),"Scientific component installation"): return state
                state.phase=InstallerPhase.VERIFY_ENGINE_PACK; self._save(state)
            if state.phase is InstallerPhase.VERIFY_ENGINE_PACK:
                self._enter(state,InstallerPhase.VERIFY_ENGINE_PACK,"Verifying scientific components.")
                if not self._component(state,self.backend.verify_engine_pack(),"Scientific component verification"): return state
                state.phase=InstallerPhase.CREATE_SHELL_INTEGRATION; self._save(state)
            if state.phase is InstallerPhase.CREATE_SHELL_INTEGRATION:
                self._enter(state,InstallerPhase.CREATE_SHELL_INTEGRATION,"Finalizing Quantum Studio installation.")
                if not self._component(state,self.backend.create_shell_integration(),"Shell integration"): return state
                state.phase=InstallerPhase.FINAL_VERIFY; self._save(state)
            if state.phase is InstallerPhase.FINAL_VERIFY:
                self._enter(state,InstallerPhase.FINAL_VERIFY,"Checking installation readiness.")
                self._complete(state,"Installation completed."); state.phase=InstallerPhase.COMPLETED; state.reboot_required=False; self._save(state); self.backend.remove_resume(state.installation_id); state.resume_registered=False; self._save(state)
            return state
        except Exception as error:
            state.fail(str(error),repair=state.phase not in {InstallerPhase.NOT_STARTED,InstallerPhase.CHECK_HOST}); self._save(state); return state

    def _request_reboot(self,state):
        self._enter(state,InstallerPhase.REBOOT_REQUIRED,"A restart is required to finish preparing Quantum Studio.")
        state.reboot_required=True; self.backend.register_resume(state.installation_id); state.resume_registered=True; self._complete(state); self._save(state); return state

    def uninstall(self, *, remove_runtime_data:bool=False, explicit_confirmation:bool=False)->InstallerState:
        state=InstallerState(installation_id=self.installation_id); self._enter(state,InstallerPhase.UNINSTALLING,"Removing Quantum Studio application; projects and runtime data are preserved by default.")
        if not self._component(state,self.backend.remove_shell_integration(),"Shell integration removal"): return state
        if not self._component(state,self.backend.remove_application(),"Application removal"): return state
        if remove_runtime_data:
            if not explicit_confirmation: state.fail("Full scientific runtime removal requires explicit confirmation.",repair=True); self._save(state); return state
            if not self._component(state,self.backend.remove_managed_runtime_and_data(),"Full scientific runtime removal"): return state
        state.phase=InstallerPhase.UNINSTALLED; self._complete(state,"Uninstall completed."); self._save(state); return state
