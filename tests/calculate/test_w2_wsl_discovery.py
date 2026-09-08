import unittest

from backend.execution import ManagedWSL2Runtime
from backend.runtime import (
    MANAGED_DISTRO_NAME,
    ManagedWSLHealth,
    OperatingSystem,
    WSLCommandResult,
    WSLDiscovery,
    WSLDistributionState,
    WSLHostState,
    WSLProbeError,
    WSLRuntimeState,
    detect_platform,
    parse_wsl_distributions,
)


class FakeWSLRunner:
    def __init__(self, results, available=True):
        self.results = results
        self.available_value = available
        self.calls = []

    def available(self):
        return self.available_value

    def run(self, arguments):
        args = tuple(arguments)
        self.calls.append(args)
        return self.results.get(args, WSLCommandResult(("wsl.exe", *args), returncode=1, error=WSLProbeError.COMMAND_FAILED))


def result(args, stdout=b"", returncode=0, error=None):
    return WSLCommandResult(("wsl.exe", *args), returncode=returncode, stdout=stdout, error=error)


WINDOWS = detect_platform(system="Windows", machine="AMD64", python_bits=64)
LIST_HEADER = b"  NAME      STATE           VERSION\r\n"


class WSLDiscoveryTests(unittest.TestCase):
    def test_linux_does_not_invoke_wsl_and_keeps_non_windows_report(self):
        runner = FakeWSLRunner({})
        report = WSLDiscovery(runner, detect_platform(system="Linux", machine="x86_64")).probe()
        self.assertEqual(report.host_state, WSLHostState.NON_WINDOWS)
        self.assertEqual(report.probe_errors, (WSLProbeError.UNSUPPORTED_PLATFORM.value,))
        self.assertEqual(runner.calls, [])

    def test_missing_wsl_executable_is_controlled(self):
        report = WSLDiscovery(FakeWSLRunner({}, available=False), WINDOWS).probe()
        self.assertEqual(report.host_state, WSLHostState.COMMAND_MISSING)
        self.assertEqual(report.managed_runtime.health_state, WSLRuntimeState.RUNTIME_NOT_INSTALLED)
        self.assertIn(WSLProbeError.EXECUTABLE_NOT_FOUND.value, report.probe_errors)

    def test_empty_distribution_table_and_optional_version_failure(self):
        runner = FakeWSLRunner({
            ("--list", "--verbose"): result(("--list", "--verbose"), LIST_HEADER),
            ("--version",): result(("--version",), returncode=1),
        })
        report = WSLDiscovery(runner, WINDOWS).probe()
        self.assertEqual(report.host_state, WSLHostState.AVAILABLE)
        self.assertEqual(report.distributions, ())
        self.assertFalse(report.managed_runtime.registered)
        self.assertIn(WSLProbeError.COMMAND_FAILED.value, report.probe_errors)

    def test_user_distro_is_not_adopted(self):
        output = LIST_HEADER + b"* Ubuntu-24.04 Running 2\r\n"
        runner = FakeWSLRunner({
            ("--list", "--verbose"): result(("--list", "--verbose"), output),
            ("--version",): result(("--version",), returncode=1),
        })
        report = WSLDiscovery(runner, WINDOWS).probe()
        self.assertEqual(report.host_state, WSLHostState.WSL2_AVAILABLE)
        self.assertEqual(report.distributions[0].name, "Ubuntu-24.04")
        self.assertTrue(report.distributions[0].is_default)
        self.assertEqual(report.managed_runtime.health_state, WSLRuntimeState.RUNTIME_NOT_INSTALLED)

    def test_exact_managed_runtime_is_detected_but_not_verified_ready(self):
        output = (LIST_HEADER + b"Ubuntu Running 2\r\n"
                  + MANAGED_DISTRO_NAME.encode() + b" Stopped 2\r\n")
        runner = FakeWSLRunner({
            ("--list", "--verbose"): result(("--list", "--verbose"), output),
            ("--version",): result(("--version",), returncode=0, stdout=b"WSL version: 2.4\n"),
        })
        report = WSLDiscovery(runner, WINDOWS).probe()
        self.assertEqual(report.managed_runtime.name, MANAGED_DISTRO_NAME)
        self.assertEqual(report.managed_runtime.health_state, WSLRuntimeState.REGISTERED_WSL2)
        self.assertEqual(report.managed_runtime.distro_state, WSLDistributionState.STOPPED)
        self.assertEqual(runner.calls, [("--list", "--verbose"), ("--version",)])
        runtime = ManagedWSL2Runtime(WINDOWS, report)
        self.assertEqual(runtime.probe().state.value, "AVAILABLE_NOT_READY")

    def test_wsl1_managed_runtime_is_degraded(self):
        output = LIST_HEADER + b"QuantumStudioRuntime Running 1\r\n"
        runner = FakeWSLRunner({
            ("--list", "--verbose"): result(("--list", "--verbose"), output),
            ("--version",): result(("--version",), returncode=0),
        })
        report = WSLDiscovery(runner, WINDOWS).probe()
        self.assertEqual(report.managed_runtime.health_state, WSLRuntimeState.REGISTERED_WSL1)

    def test_timeout_and_nonzero_failure_are_controlled(self):
        timeout_runner = FakeWSLRunner({
            ("--list", "--verbose"): result(("--list", "--verbose"), error=WSLProbeError.TIMEOUT),
        })
        self.assertEqual(WSLDiscovery(timeout_runner, WINDOWS).probe().host_state, WSLHostState.PROBE_TIMEOUT)
        failed_runner = FakeWSLRunner({
            ("--list", "--verbose"): result(("--list", "--verbose"), returncode=42),
        })
        self.assertEqual(WSLDiscovery(failed_runner, WINDOWS).probe().host_state, WSLHostState.UNAVAILABLE)

    def test_parser_handles_unicode_spaces_markers_and_exact_names(self):
        text = ("NAME STATE VERSION\r\n"
                "* My Test Distro Running 2\r\n"
                "QuantumStudioRuntime-old Stopped 2\r\n"
                "MyQuantumStudioRuntime Stopped 2\r\n"
                "量子实验室 Stopped 1\r\n")
        records, errors = parse_wsl_distributions(text)
        self.assertEqual(errors, ())
        self.assertEqual([item.name for item in records], ["My Test Distro", "QuantumStudioRuntime-old", "MyQuantumStudioRuntime", "量子实验室"])
        self.assertTrue(records[0].is_default)

    def test_malformed_table_does_not_adopt_arbitrary_text(self):
        runner = FakeWSLRunner({
            ("--list", "--verbose"): result(("--list", "--verbose"), b"unexpected output\n"),
        })
        report = WSLDiscovery(runner, WINDOWS).probe()
        self.assertEqual(report.host_state, WSLHostState.PROBE_ERROR)
        self.assertEqual(report.managed_runtime.health_state, WSLRuntimeState.RUNTIME_NOT_INSTALLED)
        self.assertIn(WSLProbeError.MALFORMED_OUTPUT.value, report.probe_errors)


if __name__ == "__main__":
    unittest.main()
