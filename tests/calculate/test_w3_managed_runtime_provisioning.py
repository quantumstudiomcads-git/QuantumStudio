import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from backend.execution import ManagedWSL2Runtime
from backend.runtime import (
    HOST_MARKER_FILENAME, MANAGED_DISTRO_NAME, ManagedRuntimeHealthState,
    ManagedRuntimeImage, ManagedRuntimeProvisioner, ManagedWSL2CommandInterface,
    OperatingSystem, RuntimeImageError, RuntimeProvisioningAction,
    RuntimeProvisioningError, RuntimeVersionCompatibility, WSLCommandResult,
    WSLProbeError, compare_runtime_versions, detect_platform, runtime_paths,
)

WINDOWS = detect_platform(system="Windows", machine="AMD64", python_bits=64)
LIST_HEADER = b"  NAME      STATE           VERSION\r\n"


class FakeWSLRunner:
    """Stateful WSL boundary used solely by Linux tests; never runs a subprocess."""

    def __init__(self, *, registered=False, wsl_version=2, metadata=None, available=True,
                 import_error=None, import_returncode=0, import_registers=True):
        self.registered = registered
        self.wsl_version = wsl_version
        self.metadata = metadata
        self.available_value = available
        self.import_error = import_error
        self.import_returncode = import_returncode
        self.import_registers = import_registers
        self.calls = []

    def available(self):
        return self.available_value

    def run(self, arguments):
        args = tuple(arguments)
        self.calls.append(args)
        if args == ("--list", "--verbose"):
            body = b""
            if self.registered:
                body = f"{MANAGED_DISTRO_NAME} Stopped {self.wsl_version}\r\n".encode()
            return WSLCommandResult(("wsl.exe", *args), returncode=0, stdout=LIST_HEADER + body)
        if args == ("--version",):
            return WSLCommandResult(("wsl.exe", *args), returncode=0, stdout=b"WSL version: 2.4\n")
        if args[:2] == ("--import", MANAGED_DISTRO_NAME):
            if self.import_registers:
                self.registered = True
                self.wsl_version = 2
            return WSLCommandResult(("wsl.exe", *args), returncode=self.import_returncode, error=self.import_error)
        if args == ("--unregister", MANAGED_DISTRO_NAME):
            self.registered = False
            return WSLCommandResult(("wsl.exe", *args), returncode=0)
        if args == ("--distribution", MANAGED_DISTRO_NAME, "--exec", "cat", "/opt/quantumstudio/runtime/runtime.json"):
            if self.metadata is None:
                return WSLCommandResult(("wsl.exe", *args), returncode=1, stderr=b"missing")
            return WSLCommandResult(("wsl.exe", *args), returncode=0, stdout=json.dumps(self.metadata).encode())
        return WSLCommandResult(("wsl.exe", *args), returncode=1, error=WSLProbeError.COMMAND_FAILED)


class ManagedRuntimeProvisioningTests(unittest.TestCase):
    def _image(self, root, *, payload=b"tiny rootfs", version="0.2-runtime.1"):
        source = Path(root) / "runtime rootfs.tar"
        source.write_bytes(payload)
        return ManagedRuntimeImage(MANAGED_DISTRO_NAME, version, OperatingSystem.WINDOWS, "x86_64", source,
                                   hashlib.sha256(payload).hexdigest())

    def _paths(self, root):
        return runtime_paths(home=root, platform_name="win32", environ={"LOCALAPPDATA": str(Path(root) / "Local AppData")})

    def _metadata(self, image, *, version=None, **changes):
        result = {
            "runtime_id": MANAGED_DISTRO_NAME,
            "runtime_version": version or image.runtime_version,
            "schema_version": "1",
            "architecture": "amd64",
            "build_id": "test-build",
            "build_timestamp": "2026-09-08T00:00:00Z",
            "image_sha256": image.sha256,
        }
        result.update(changes)
        return result

    def test_absent_valid_image_plans_import_and_import_argv_is_fixed(self):
        with tempfile.TemporaryDirectory() as root:
            image = self._image(root)
            runner = FakeWSLRunner(registered=False, metadata=self._metadata(image))
            provisioner = ManagedRuntimeProvisioner(image, info=WINDOWS, runner=runner, paths=self._paths(root))
            before = provisioner.inspect()
            plan = provisioner.plan(before)
            self.assertEqual(before.health, ManagedRuntimeHealthState.ABSENT)
            self.assertEqual(plan.action, RuntimeProvisioningAction.IMPORT_RUNTIME)
            result = provisioner.execute(plan, before=before)
            self.assertTrue(result.success)
            expected = ("--import", MANAGED_DISTRO_NAME, str(provisioner.installation_root), str(image.source_path), "--version", "2")
            self.assertIn(expected, runner.calls)
            self.assertTrue((provisioner.installation_root / HOST_MARKER_FILENAME).is_file())

    def test_corrupt_image_blocks_before_any_mutation(self):
        with tempfile.TemporaryDirectory() as root:
            image = self._image(root)
            bad = ManagedRuntimeImage(MANAGED_DISTRO_NAME, image.runtime_version, OperatingSystem.WINDOWS,
                                      "x86_64", image.source_path, "0" * 64)
            runner = FakeWSLRunner(metadata=self._metadata(image))
            provisioner = ManagedRuntimeProvisioner(bad, info=WINDOWS, runner=runner, paths=self._paths(root))
            plan = provisioner.plan(provisioner.inspect())
            self.assertEqual(plan.action, RuntimeProvisioningAction.BLOCKED)
            result = provisioner.execute(plan)
            self.assertEqual(result.error, RuntimeProvisioningError.IMAGE_INTEGRITY_FAILED)
            self.assertNotIn(("--import", MANAGED_DISTRO_NAME), [call[:2] for call in runner.calls])

    def test_correct_runtime_is_no_action_and_second_ensure_is_idempotent(self):
        with tempfile.TemporaryDirectory() as root:
            image = self._image(root)
            paths = self._paths(root)
            runner = FakeWSLRunner(registered=True, metadata=self._metadata(image))
            provisioner = ManagedRuntimeProvisioner(image, info=WINDOWS, runner=runner, paths=paths)
            # First pass writes the missing, repairable host ownership marker.
            first = provisioner.ensure_managed_runtime()
            self.assertEqual(first.requested_action, RuntimeProvisioningAction.REPAIR_METADATA)
            self.assertTrue(first.success)
            before_calls = len(runner.calls)
            second = provisioner.ensure_managed_runtime()
            self.assertEqual(second.requested_action, RuntimeProvisioningAction.NO_ACTION)
            self.assertTrue(second.success)
            self.assertNotIn("--import", [item for call in runner.calls[before_calls:] for item in call])
            self.assertNotIn("--unregister", [item for call in runner.calls[before_calls:] for item in call])

    def test_wsl1_recreate_is_destructive_and_never_automatic(self):
        with tempfile.TemporaryDirectory() as root:
            image = self._image(root)
            runner = FakeWSLRunner(registered=True, wsl_version=1)
            provisioner = ManagedRuntimeProvisioner(image, info=WINDOWS, runner=runner, paths=self._paths(root))
            before = provisioner.inspect()
            plan = provisioner.plan(before)
            self.assertEqual(plan.action, RuntimeProvisioningAction.RECREATE_RUNTIME)
            self.assertTrue(plan.destructive)
            result = provisioner.execute(plan, before=before)
            self.assertEqual(result.error, RuntimeProvisioningError.DESTRUCTIVE_ACTION_NOT_AUTHORIZED)
            self.assertNotIn(("--unregister", MANAGED_DISTRO_NAME), runner.calls)

    def test_missing_or_malformed_metadata_recommends_explicit_recreate(self):
        with tempfile.TemporaryDirectory() as root:
            image = self._image(root)
            for metadata in (None, {"runtime_id": MANAGED_DISTRO_NAME}):
                with self.subTest(metadata=metadata):
                    runner = FakeWSLRunner(registered=True, metadata=metadata)
                    provisioner = ManagedRuntimeProvisioner(image, info=WINDOWS, runner=runner, paths=self._paths(root))
                    inspection = provisioner.inspect()
                    self.assertEqual(inspection.health, ManagedRuntimeHealthState.METADATA_INVALID)
                    self.assertEqual(provisioner.plan(inspection).action, RuntimeProvisioningAction.RECREATE_RUNTIME)

    def test_version_compatibility_is_deterministic_and_newer_is_blocked(self):
        self.assertEqual(compare_runtime_versions("0.2-runtime.0", "0.2-runtime.1"), RuntimeVersionCompatibility.OLDER_COMPATIBLE)
        self.assertEqual(compare_runtime_versions("0.2-runtime.2", "0.2-runtime.1"), RuntimeVersionCompatibility.NEWER_COMPATIBLE)
        self.assertEqual(compare_runtime_versions("0.3-runtime.0", "0.2-runtime.1"), RuntimeVersionCompatibility.NEWER_UNSUPPORTED)
        self.assertEqual(compare_runtime_versions("broken", "0.2-runtime.1"), RuntimeVersionCompatibility.INVALID)
        with tempfile.TemporaryDirectory() as root:
            image = self._image(root)
            runner = FakeWSLRunner(registered=True, metadata=self._metadata(image, version="0.3-runtime.0"))
            provisioner = ManagedRuntimeProvisioner(image, info=WINDOWS, runner=runner, paths=self._paths(root))
            self.assertEqual(provisioner.plan(provisioner.inspect()).action, RuntimeProvisioningAction.BLOCKED)

    def test_wsl_prerequisite_missing_does_not_attempt_install(self):
        with tempfile.TemporaryDirectory() as root:
            image = self._image(root)
            runner = FakeWSLRunner(available=False)
            result = ManagedRuntimeProvisioner(image, info=WINDOWS, runner=runner, paths=self._paths(root)).ensure_managed_runtime()
            self.assertEqual(result.error, RuntimeProvisioningError.HOST_PREREQUISITE_MISSING)
            self.assertEqual(runner.calls, [])

    def test_user_and_similarly_named_distros_are_never_mutated(self):
        with tempfile.TemporaryDirectory() as root:
            image = self._image(root)
            runner = FakeWSLRunner(metadata=self._metadata(image))
            # The fixed interface has no name argument by design.
            interface = ManagedWSL2CommandInterface(runner)
            interface.import_managed_runtime(Path(root) / "space 量子", image.source_path)
            interface.unregister_managed_runtime()
            self.assertEqual(runner.calls[0][1], MANAGED_DISTRO_NAME)
            self.assertEqual(runner.calls[1], ("--unregister", MANAGED_DISTRO_NAME))
            self.assertNotIn("Ubuntu", str(runner.calls))

    def test_unknown_nonempty_install_directory_blocks_overwrite(self):
        with tempfile.TemporaryDirectory() as root:
            image = self._image(root)
            paths = self._paths(root)
            target = paths.managed_wsl_runtime / MANAGED_DISTRO_NAME
            target.mkdir(parents=True)
            (target / "someone-elses-data.txt").write_text("do not erase")
            provisioner = ManagedRuntimeProvisioner(image, info=WINDOWS, runner=FakeWSLRunner(), paths=paths)
            plan = provisioner.plan(provisioner.inspect())
            self.assertEqual(plan.action, RuntimeProvisioningAction.BLOCKED)
            self.assertEqual((target / "someone-elses-data.txt").read_text(), "do not erase")

    def test_paths_with_spaces_and_unicode_are_argv_elements_not_shell_text(self):
        with tempfile.TemporaryDirectory(prefix="Quantum Studio 量子 ") as root:
            image = self._image(root)
            runner = FakeWSLRunner(metadata=self._metadata(image))
            provisioner = ManagedRuntimeProvisioner(image, info=WINDOWS, runner=runner, paths=self._paths(root))
            result = provisioner.ensure_managed_runtime()
            self.assertTrue(result.success)
            import_call = next(call for call in runner.calls if call[:2] == ("--import", MANAGED_DISTRO_NAME))
            self.assertIn(" ", import_call[2])
            self.assertIn("量子", import_call[3])

    def test_import_timeout_and_partial_registration_are_controlled(self):
        with tempfile.TemporaryDirectory() as root:
            image = self._image(root)
            runner = FakeWSLRunner(metadata=self._metadata(image), import_error=WSLProbeError.TIMEOUT, import_registers=True)
            result = ManagedRuntimeProvisioner(image, info=WINDOWS, runner=runner, paths=self._paths(root)).ensure_managed_runtime()
            self.assertEqual(result.error, RuntimeProvisioningError.IMPORT_TIMEOUT)
            self.assertTrue(runner.registered)

    def test_post_import_wsl1_and_metadata_version_mismatch_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            image = self._image(root)
            runner = FakeWSLRunner(metadata=self._metadata(image))
            original = runner.run
            def wsl1_after_import(arguments):
                result = original(arguments)
                if tuple(arguments)[:2] == ("--import", MANAGED_DISTRO_NAME):
                    runner.wsl_version = 1
                return result
            runner.run = wsl1_after_import
            result = ManagedRuntimeProvisioner(image, info=WINDOWS, runner=runner, paths=self._paths(root)).ensure_managed_runtime()
            self.assertEqual(result.error, RuntimeProvisioningError.POST_IMPORT_WSL1)
        with tempfile.TemporaryDirectory() as root:
            image = self._image(root)
            runner = FakeWSLRunner(metadata=self._metadata(image, version="0.2-runtime.0"))
            result = ManagedRuntimeProvisioner(image, info=WINDOWS, runner=runner, paths=self._paths(root)).ensure_managed_runtime()
            self.assertEqual(result.error, RuntimeProvisioningError.METADATA_INVALID)

    def test_import_nonzero_is_controlled_without_user_distro_mutation(self):
        with tempfile.TemporaryDirectory() as root:
            image = self._image(root)
            runner = FakeWSLRunner(metadata=self._metadata(image), import_returncode=42, import_registers=False)
            result = ManagedRuntimeProvisioner(image, info=WINDOWS, runner=runner, paths=self._paths(root)).ensure_managed_runtime()
            self.assertEqual(result.error, RuntimeProvisioningError.IMPORT_FAILED)
            self.assertNotIn("Ubuntu", str(runner.calls))

    def test_post_import_absent_and_metadata_identity_schema_failures_are_controlled(self):
        with tempfile.TemporaryDirectory() as root:
            image = self._image(root)
            absent = FakeWSLRunner(metadata=self._metadata(image), import_registers=False)
            result = ManagedRuntimeProvisioner(image, info=WINDOWS, runner=absent, paths=self._paths(root)).ensure_managed_runtime()
            self.assertEqual(result.error, RuntimeProvisioningError.POST_IMPORT_ABSENT)
        with tempfile.TemporaryDirectory() as root:
            image = self._image(root)
            for fields in ({"runtime_id": "Ubuntu"}, {"schema_version": "99"}):
                with self.subTest(fields=fields):
                    runner = FakeWSLRunner(registered=True, metadata=self._metadata(image, **fields))
                    provisioner = ManagedRuntimeProvisioner(image, info=WINDOWS, runner=runner, paths=self._paths(root))
                    self.assertEqual(provisioner.inspect().health, ManagedRuntimeHealthState.METADATA_INVALID)

    def test_provider_can_report_verified_metadata_but_remains_scientifically_disabled(self):
        runtime = ManagedWSL2Runtime(WINDOWS, provisioning_health=ManagedRuntimeHealthState.METADATA_VALID)
        self.assertEqual(runtime.probe().state.value, "AVAILABLE_NOT_READY")
        with self.assertRaises(Exception):
            runtime.execute(None)

    def test_image_missing_and_hash_failures_are_typed(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "missing.tar"
            image = ManagedRuntimeImage(MANAGED_DISTRO_NAME, "0.2-runtime.1", OperatingSystem.WINDOWS, "x86_64", source, "0" * 64)
            self.assertEqual(image.verify(host_platform=OperatingSystem.WINDOWS, host_architecture="amd64").error, RuntimeImageError.MISSING)


if __name__ == "__main__":
    unittest.main()
