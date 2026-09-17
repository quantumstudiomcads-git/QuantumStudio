import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from backend.runtime.platform import OperatingSystem
from backend.runtime.runtime_image import ManagedRuntimeImage
from scripts.windows_installer.contracts import (
    ComponentAction, ComponentResult, HostAssessment, HostPrerequisite,
    InstallerContractError, InstallerPayload, InstallerProfile, MANAGED_RUNTIME_ID,
)
from scripts.windows_installer.orchestrator import InstallerOrchestrator
from scripts.windows_installer.state import InstallerPhase, InstallerState, InstallerStateStore, installer_state_root
from scripts.windows_installer.system import FEATURES, is_windows_11, prerequisite_argv
from scripts.windows_installer.payload_audit import audit_installer_payload
from scripts.windows_installer.runtime_adapter import ManagedRuntimeInstallerAdapter
from scripts.build_windows_installer import installer_script

REPO = Path(__file__).resolve().parents[2]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FakeInstallerBackend:
    def __init__(self, *, prerequisite=HostPrerequisite.READY, enable=HostPrerequisite.READY,
                 runtime=ComponentAction.INSTALL, engine=ComponentAction.INSTALL):
        self.prerequisite, self.enable_result = prerequisite, enable
        self.runtime_action, self.engine_action = runtime, engine
        self.calls = []
        self.resume = []

    def assess_host(self):
        self.calls.append("assess")
        return HostAssessment(True, "x86_64", 11, self.prerequisite, "Synthetic Windows 11 x64 host.")

    def enable_wsl_prerequisites(self): self.calls.append("enable"); return self.enable_result
    def register_resume(self, installation_id): self.resume.append(("register", installation_id))
    def remove_resume(self, installation_id): self.resume.append(("remove", installation_id))
    def _result(self, name, action=ComponentAction.INSTALL): self.calls.append(name); return ComponentResult(action, name)
    def install_application(self, payload): return self._result("install_app")
    def verify_application(self, payload): return self._result("verify_app", ComponentAction.NO_ACTION)
    def ensure_managed_runtime(self, payload): return self._result("runtime", self.runtime_action)
    def verify_managed_runtime(self): return self._result("verify_runtime", ComponentAction.NO_ACTION)
    def ensure_engine_pack(self, payload): return self._result("engine", self.engine_action)
    def verify_engine_pack(self): return self._result("verify_engine", ComponentAction.NO_ACTION)
    def create_shell_integration(self): return self._result("shell")
    def remove_application(self): return self._result("remove_app")
    def remove_shell_integration(self): return self._result("remove_shell")
    def remove_managed_runtime_and_data(self): return self._result("remove_runtime")


class WindowsInstallerTests(unittest.TestCase):
    def test_generated_inno_script_has_stable_identity_and_pe_version_metadata(self):
        script = installer_script(
            app_bundle=Path("C:/validated/main.dist"),
            output=Path("C:/installer-output"),
            version="0.2.0",
        )

        for directive in (
            "AppId={{C90FC580-47D1-4A00-9C12-8A4502DEB601}",
            "VersionInfoVersion=0.2.0",
            "VersionInfoProductVersion=0.2.0",
            "VersionInfoProductName=Quantum Studio",
            "VersionInfoDescription=Quantum Studio Installer",
        ):
            self.assertIn(directive, script)

    def make_payload(self, root: Path, *, full=True):
        bundle=root / "Bundle Ω"; bundle.mkdir()
        (bundle / "QuantumStudio.exe").write_bytes(b"native bundle")
        manifest=bundle / "quantumstudio-build.json"
        manifest.write_text(json.dumps({"platform": "windows", "architecture": "x86_64"}))
        image=root / "runtime.tar"; image.write_bytes(b"synthetic rootfs")
        runtime=ManagedRuntimeImage("QuantumStudioRuntime", "0.2", OperatingSystem.WINDOWS, "x86_64", image, digest(image))
        pack=root / "engine pack"; (pack / "bin").mkdir(parents=True)
        tool=pack / "bin" / "fake-tool"; tool.write_bytes(b"fake executable")
        pack_manifest=pack / "engine-pack.json"
        pack_manifest.write_text(json.dumps({"schema_version": "1", "engine_pack_version": "0.2", "platform": "linux", "architecture": "x86_64", "engines": [{"tool_id": "fake-tool", "executable": "fake-tool", "relative_path": "bin/fake-tool", "sha256": digest(tool)}]}))
        return InstallerPayload(bundle, manifest, digest(manifest), runtime, pack if full else None, digest(pack_manifest) if full else "")

    def orchestrator(self, root, backend, *, full=True):
        return InstallerOrchestrator(self.make_payload(root, full=full), InstallerProfile.FULL_SCIENTIFIC if full else InstallerProfile.GUI_PLUS_RUNTIME, backend, InstallerStateStore(root / "ProgramData" / "QuantumStudio" / "installer"), "install-01")

    def test_full_mocked_install_validates_payload_and_completes(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend=FakeInstallerBackend(); state=self.orchestrator(Path(tmp), backend).run()
            self.assertEqual(state.phase, InstallerPhase.COMPLETED)
            self.assertEqual(backend.calls, ["assess", "assess", "install_app", "verify_app", "runtime", "verify_runtime", "engine", "verify_engine", "shell"])
            self.assertIn(("remove", "install-01"), backend.resume)

    def test_unsupported_host_refuses_before_component_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend=FakeInstallerBackend()
            backend.assess_host=lambda: HostAssessment(False, "arm64", 0, HostPrerequisite.UNSUPPORTED, "Windows 11 x86_64 is required.")
            state=self.orchestrator(Path(tmp), backend).run()
            self.assertEqual(state.phase, InstallerPhase.FAILED)
            self.assertEqual(backend.calls, [])

    def test_reboot_persists_and_resumes_without_repeating_completed_components(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); backend=FakeInstallerBackend(prerequisite=HostPrerequisite.NEEDS_ENABLEMENT, enable=HostPrerequisite.REBOOT_REQUIRED)
            installer=self.orchestrator(root, backend)
            paused=installer.run(); self.assertEqual(paused.phase, InstallerPhase.REBOOT_REQUIRED); self.assertTrue(paused.resume_registered)
            self.assertEqual(InstallerStateStore(root / "ProgramData" / "QuantumStudio" / "installer").load().phase, InstallerPhase.REBOOT_REQUIRED)
            backend.prerequisite=HostPrerequisite.READY
            resumed=installer.run(); self.assertEqual(resumed.phase, InstallerPhase.COMPLETED)
            self.assertEqual(backend.calls.count("install_app"), 1)
            self.assertIn(("register", "install-01"), backend.resume); self.assertGreaterEqual(backend.resume.count(("remove", "install-01")), 1)

    def test_ownership_conflict_blocks_without_destructive_runtime_removal(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend=FakeInstallerBackend(runtime=ComponentAction.OWNERSHIP_CONFLICT)
            state=self.orchestrator(Path(tmp), backend).run()
            self.assertEqual(state.phase, InstallerPhase.REPAIR_REQUIRED)
            self.assertIn("runtime", backend.calls); self.assertNotIn("remove_runtime", backend.calls)
            self.assertNotIn("engine", backend.calls)

    def test_installer_hard_binds_only_the_exact_managed_runtime_identity(self):
        self.assertEqual(MANAGED_RUNTIME_ID, "QuantumStudioRuntime")
        # The installer backend has no caller-supplied distro field: a W7
        # operation receives only a verified payload and reaches W3's fixed API.
        self.assertNotIn("distro", InstallerOrchestrator.__dataclass_fields__)
        ignored={"Ubuntu", "Debian", "Kali-Linux", "docker-desktop", "QuantumStudioRuntime-Test"}
        self.assertNotIn(MANAGED_RUNTIME_ID, ignored)

    def test_payload_hash_and_verified_engine_pack_are_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); payload=self.make_payload(root)
            payload.validate(InstallerProfile.FULL_SCIENTIFIC)
            (root / "engine pack" / "bin" / "fake-tool").write_bytes(b"corrupt")
            with self.assertRaises(InstallerContractError): payload.validate(InstallerProfile.FULL_SCIENTIFIC)

    def test_second_run_is_no_action_idempotent_at_component_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); backend=FakeInstallerBackend(runtime=ComponentAction.NO_ACTION, engine=ComponentAction.NO_ACTION)
            installer=self.orchestrator(root, backend); self.assertEqual(installer.run().phase, InstallerPhase.COMPLETED)
            # A completed journal is stable on a second invocation; it does not import again.
            self.assertEqual(installer.run().phase, InstallerPhase.COMPLETED)
            self.assertEqual(backend.calls.count("runtime"), 1); self.assertEqual(backend.calls.count("engine"), 1)

    def test_engine_failure_preserves_app_and_runtime_for_repair(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend=FakeInstallerBackend(engine=ComponentAction.FAILED)
            state=self.orchestrator(Path(tmp), backend).run()
            self.assertEqual(state.phase, InstallerPhase.REPAIR_REQUIRED)
            self.assertIn("runtime", backend.calls); self.assertNotIn("verify_engine", backend.calls)
            self.assertNotIn("remove_runtime", backend.calls)

    def test_normal_uninstall_preserves_runtime_and_full_cleanup_requires_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); backend=FakeInstallerBackend(); installer=self.orchestrator(root, backend)
            normal=installer.uninstall(); self.assertEqual(normal.phase, InstallerPhase.UNINSTALLED); self.assertNotIn("remove_runtime", backend.calls)
            blocked=installer.uninstall(remove_runtime_data=True); self.assertEqual(blocked.phase, InstallerPhase.REPAIR_REQUIRED); self.assertNotIn("remove_runtime", backend.calls)
            full=installer.uninstall(remove_runtime_data=True, explicit_confirmation=True); self.assertEqual(full.phase, InstallerPhase.UNINSTALLED); self.assertEqual(backend.calls.count("remove_runtime"), 1)

    def test_state_is_atomic_programdata_policy_and_corruption_is_controlled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); self.assertEqual(installer_state_root(environ={"PROGRAMDATA": str(root / "Program Data Ω")}), root / "Program Data Ω" / "QuantumStudio" / "installer")
            store=InstallerStateStore(root / "ProgramData" / "QuantumStudio" / "installer")
            store.save(InstallerState(installation_id="safe-id")); self.assertEqual(store.load().installation_id, "safe-id")
            store.path.write_text("not json")
            with self.assertRaisesRegex(ValueError, "continuation state is corrupt"): store.load()

    def test_fixed_dism_argv_and_windows_11_build_rule_have_no_shell(self):
        self.assertTrue(is_windows_11(release="10", build=22631)); self.assertFalse(is_windows_11(release="10", build=19045))
        for feature in FEATURES:
            argv=prerequisite_argv(feature); self.assertEqual(argv[0], "dism.exe"); self.assertIn("/norestart", argv); self.assertNotIn("cmd.exe", argv); self.assertNotIn("PowerShell", argv)
        with self.assertRaises(ValueError): prerequisite_argv("arbitrary-feature")

    def test_payload_audit_allows_declared_rootfs_but_rejects_unexpected_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); declared=root / "declared-rootfs.tar"; declared.write_bytes(b"rootfs")
            self.assertTrue(audit_installer_payload(root, declared=(declared,))["valid"])
            (root / "unexpected-rootfs.tar").write_bytes(b"rootfs")
            (root / "pw.x").write_bytes(b"untracked engine")
            audit=audit_installer_payload(root, declared=(declared,)); self.assertFalse(audit["valid"]); self.assertIn("unexpected-rootfs.tar", audit["forbidden"]); self.assertIn("pw.x", audit["forbidden"])

    def test_w3_adapter_maps_unowned_runtime_to_ownership_conflict_without_recreation(self):
        class Result:
            success=False; performed_action=None; error=None; diagnostics=("unknown root",)
        class Provisioner:
            def __init__(self, image): self.image=image
            def ensure_managed_runtime(self, *, allow_destructive):
                self.allow_destructive=allow_destructive
                from backend.runtime.provisioning import RuntimeProvisioningError
                Result.error=RuntimeProvisioningError.UNKNOWN_INSTALLATION_DIRECTORY
                return Result()
        with tempfile.TemporaryDirectory() as tmp:
            payload=self.make_payload(Path(tmp), full=False)
            result=ManagedRuntimeInstallerAdapter(provisioner_factory=Provisioner).ensure_runtime(payload)
            self.assertEqual(result.action, ComponentAction.OWNERSHIP_CONFLICT)

    def test_installer_builder_is_plan_only_on_linux(self):
        plan=subprocess.run([sys.executable, "scripts/build_windows_installer.py", "--plan", "--profile", "GUI_ONLY"], cwd=REPO, capture_output=True, text=True, check=False)
        self.assertEqual(plan.returncode, 0); self.assertIn('"status": "PLAN_ONLY"', plan.stdout)
        actual=subprocess.run([sys.executable, "scripts/build_windows_installer.py"], cwd=REPO, capture_output=True, text=True, check=False)
        if sys.platform.startswith("win"):
            self.assertEqual(actual.returncode, 2); self.assertIn("INSTALLER_INPUT_MISSING", actual.stderr)
        else:
            self.assertEqual(actual.returncode, 2); self.assertIn("WINDOWS_INSTALLER_BUILD_HOST_REQUIRED", actual.stderr)
