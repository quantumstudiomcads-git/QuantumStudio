import tempfile
import unittest
from pathlib import Path

from backend.execution import (
    LocalLinuxRuntime, ManagedWSL2Runtime, TaskExecutionRecord,
    WorkflowExecutionRecord, select_compute_runtime,
)
from backend.execution.persistence import ExecutionStore
from backend.runtime import (
    ManagedRuntimeIdentity, OperatingSystem, RuntimeState, RuntimeType,
    detect_platform, runtime_paths,
)


class WindowsPlatformFoundationTests(unittest.TestCase):
    def test_platform_identity_normalizes_linux_windows_and_unknown(self):
        linux = detect_platform(system="Linux", machine="x86_64", release="test", python_bits=64)
        windows = detect_platform(system="Windows", machine="AMD64", release="11", python_bits=64)
        unknown = detect_platform(system="Plan9", machine="mystery", python_bits=32)
        self.assertEqual(linux.operating_system, OperatingSystem.LINUX)
        self.assertEqual(windows.operating_system, OperatingSystem.WINDOWS)
        self.assertEqual(windows.architecture, "amd64")
        self.assertTrue(windows.is_64_bit)
        self.assertEqual(unknown.operating_system, OperatingSystem.UNKNOWN)
        self.assertFalse(unknown.is_64_bit)

    def test_linux_paths_remain_xdg_based(self):
        with tempfile.TemporaryDirectory() as root:
            paths = runtime_paths(home=root, environ={"XDG_CONFIG_HOME": f"{root}/cfg", "XDG_DATA_HOME": f"{root}/data", "XDG_CACHE_HOME": f"{root}/cache"}, platform_name="linux")
            self.assertEqual(paths.config, Path(root) / "cfg" / "QuantumStudio")
            self.assertEqual(paths.data, Path(root) / "data" / "QuantumStudio")
            self.assertEqual(paths.workflows, paths.data / "workflows")
            self.assertEqual(paths.runtime, paths.data / "runtime")

    def test_windows_paths_use_appdata_and_localappdata(self):
        with tempfile.TemporaryDirectory() as root:
            appdata, local = Path(root) / "roaming", Path(root) / "local"
            paths = runtime_paths(home=root, platform_name="win32", environ={"APPDATA": str(appdata), "LOCALAPPDATA": str(local)})
            self.assertEqual(paths.config, appdata / "QuantumStudio")
            self.assertEqual(paths.data, local / "QuantumStudio")
            self.assertEqual(paths.cache, local / "QuantumStudio" / "cache")
            self.assertEqual(paths.logs, local / "QuantumStudio" / "logs")
            self.assertEqual(paths.runtime, local / "QuantumStudio" / "runtime")
            self.assertEqual(paths.diagnostics, local / "QuantumStudio" / "diagnostics")
            self.assertNotIn("Program Files", str(paths.data))

    def test_windows_paths_support_spaces_unicode_and_overrides(self):
        with tempfile.TemporaryDirectory(prefix="Quantum Studio ü ") as root:
            custom = Path(root) / "custom runtime"
            paths = runtime_paths(platform_name="win32", environ={"QUANTUM_STUDIO_DATA_ROOT": str(custom), "QUANTUM_STUDIO_CONFIG_ROOT": str(custom / "config")})
            self.assertEqual(paths.data, custom)
            self.assertEqual(paths.config, custom / "config")
            paths.ensure_user_dirs()
            self.assertTrue(paths.diagnostics.is_dir())

    def test_runtime_identity_distinguishes_installation_and_health(self):
        info = detect_platform(system="Windows", machine="AMD64", python_bits=64)
        identity = ManagedRuntimeIdentity.managed_wsl2(info)
        self.assertEqual(identity.runtime_type, RuntimeType.MANAGED_WSL2)
        self.assertEqual(identity.installation_state, RuntimeState.AVAILABLE_NOT_READY)
        self.assertEqual(identity.runtime_id, "managed-wsl2")

    def test_linux_provider_is_thin_adapter_and_wsl_is_not_ready(self):
        linux_info = detect_platform(system="Linux", machine="x86_64")
        linux = LocalLinuxRuntime(info=linux_info)
        self.assertEqual(linux.probe().state, RuntimeState.READY)
        self.assertEqual(linux.identity.runtime_type, RuntimeType.LOCAL_LINUX)
        wsl = ManagedWSL2Runtime(detect_platform(system="Windows", machine="AMD64"))
        self.assertEqual(wsl.probe().state, RuntimeState.AVAILABLE_NOT_READY)
        with self.assertRaises(Exception):
            wsl.execute(None)

    def test_provider_selection_is_deterministic_without_wsl_probe(self):
        linux = select_compute_runtime(info=detect_platform(system="Linux", machine="x86_64"))
        windows = select_compute_runtime(info=detect_platform(system="Windows", machine="AMD64"))
        self.assertIsInstance(linux, LocalLinuxRuntime)
        self.assertIsInstance(windows, ManagedWSL2Runtime)
        self.assertEqual(windows.probe().state, RuntimeState.AVAILABLE_NOT_READY)

    def test_execution_provider_provenance_is_optional_and_round_trips(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            store = ExecutionStore(root)
            old = WorkflowExecutionRecord("old", str(root), {"t": TaskExecutionRecord("t")}, execution_id="old")
            store.save(old)
            loaded_old = store.load("old")
            self.assertEqual(loaded_old.provider_provenance, {})
            current = WorkflowExecutionRecord("new", str(root), {"t": TaskExecutionRecord("t")}, execution_id="new", provider_provenance={"provider_type": "LOCAL_LINUX", "runtime_id": "local-linux"})
            store.save(current)
            loaded_current = store.load("new")
            self.assertEqual(loaded_current.provider_provenance["runtime_id"], "local-linux")


if __name__ == "__main__":
    unittest.main()
