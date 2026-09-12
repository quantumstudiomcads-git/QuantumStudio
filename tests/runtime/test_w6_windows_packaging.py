import json
import io
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from backend.runtime.paths import runtime_paths
from backend.runtime.resources import ApplicationResources, ResourceError
from frontend.app.recent_projects import load_recent_projects, save_recent_projects
from frontend.calculations.catalog import CALCULATIONS
from scripts import build_windows
from scripts.windows_packaging import (PACKAGE_MARKER, WindowsBuildError, audit_package_contents, build_plan, installer_input_manifest, safe_clean_output, write_json)

REPO = Path(__file__).resolve().parents[2]

class WindowsPackagingTests(unittest.TestCase):
    def plan(self, root):
        return build_plan(repo=REPO, output=root / "dist Ω", channel="beta", version="0.2.0", commit="abc123", dirty=False, python_executable="python.exe")

    def test_windows_nuitka_plan_is_structured_and_has_product_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan=self.plan(Path(tmp)); argv=plan.nuitka_argv
            self.assertEqual(argv[:4], ("python.exe", "-m", "nuitka", "--standalone")); self.assertIn("--enable-plugin=pyside6",argv)
            self.assertIn("--msvc=latest", argv)
            self.assertIn("--jobs=4", argv)
            self.assertIn("--windows-console-mode=disable",argv); self.assertIn("--product-name=Quantum Studio",argv)
            self.assertIn("--include-module=scipy._external.array_api_compat.numpy.fft", argv)
            self.assertIn("--output-filename=QuantumStudio.exe",argv); self.assertTrue(any(item.startswith("--include-data-dir=") for item in argv))
            self.assertNotIn("cmd.exe",str(argv)); self.assertNotIn("PowerShell",str(argv))

    def test_windows_msvc_environment_appends_verified_low_optimization_option(self):
        environment = build_windows.windows_build_environment(channel="beta", commit="abc123", timestamp="2026-09-11T00:00:00Z", inherited={"KEEP": "value", "_CL_": "/Zi"})
        self.assertEqual(environment["_CL_"], "/Od")
        self.assertEqual(environment["QUANTUM_STUDIO_BUILD_CHANNEL"], "beta")
        self.assertEqual(environment["QUANTUM_STUDIO_BUILD_COMMIT"], "abc123")
        self.assertEqual(environment["KEEP"], "value")

    def test_non_windows_build_is_plan_only_not_fake_success(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(build_windows.sys, "platform", "linux"), patch.object(build_windows, "git_value", return_value=""):
            planned_stdout, planned_stderr = io.StringIO(), io.StringIO()
            with redirect_stdout(planned_stdout), redirect_stderr(planned_stderr):
                planned = build_windows.main(["--dry-run", "--output", str(Path(tmp) / "dist")])
            self.assertEqual(planned, 0); self.assertIn('"status": "PLAN_ONLY"', planned_stdout.getvalue()); self.assertEqual(planned_stderr.getvalue(), "")
            actual_stdout, actual_stderr = io.StringIO(), io.StringIO()
            with redirect_stdout(actual_stdout), redirect_stderr(actual_stderr):
                actual = build_windows.main(["--output", str(Path(tmp) / "dist")])
            self.assertEqual(actual, 2); self.assertIn("WINDOWS_BUILD_HOST_REQUIRED", actual_stderr.getvalue())
            self.assertEqual(list(Path(tmp).rglob("QuantumStudio.exe")), [])

    def test_dirty_windows_beta_build_is_refused_before_toolchain(self):
        def fake_git_value(_repo, *arguments):
            return "abc123" if arguments == ("rev-parse", "HEAD") else " M synthetic-test-state"

        with tempfile.TemporaryDirectory() as tmp, patch.object(build_windows.sys, "platform", "win32"), patch.object(build_windows, "git_value", side_effect=fake_git_value):
            output, errors = io.StringIO(), io.StringIO()
            with redirect_stdout(output), redirect_stderr(errors):
                result = build_windows.main(["--output", str(Path(tmp) / "dist")])
            self.assertEqual(result, 2)
            self.assertIn("Refusing a dirty beta/release Windows build", errors.getvalue())
            self.assertEqual(output.getvalue(), "")
            self.assertEqual(list(Path(tmp).rglob("QuantumStudio.exe")), [])

    def test_real_windows_build_requires_an_exact_git_commit(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(build_windows.sys, "platform", "win32"), patch.object(build_windows, "git_value", return_value=""):
            output, errors = io.StringIO(), io.StringIO()
            with redirect_stdout(output), redirect_stderr(errors):
                result = build_windows.main(["--output", str(Path(tmp) / "dist")])
            self.assertEqual(result, 2)
            self.assertIn("GIT_COMMIT_UNAVAILABLE", errors.getvalue())
            self.assertEqual(list(Path(tmp).rglob("QuantumStudio.exe")), [])

    def test_incomplete_standalone_output_is_never_reported_as_built(self):
        class Result: returncode = 0
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "dist"

            def fake_nuitka(command, **_kwargs):
                output_dir = next(Path(item.split("=", 1)[1]) for item in command if item.startswith("--output-dir="))
                bundle = output_dir / "main.dist"
                bundle.mkdir(parents=True)
                (bundle / "QuantumStudio.exe").write_bytes(b"linked-only")
                return Result()

            with patch.object(build_windows.sys, "platform", "win32"), \
                 patch.object(build_windows, "git_value", side_effect=lambda _repo, *arguments: "abc123" if arguments == ("rev-parse", "HEAD") else ""), \
                 patch.object(build_windows, "dependency_version", return_value="test"), \
                 patch.object(build_windows, "generate_icon"), \
                 patch.object(build_windows.subprocess, "run", side_effect=fake_nuitka):
                stdout, stderr = io.StringIO(), io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    result = build_windows.main(["--output", str(output)])
            self.assertEqual(result, 2)
            self.assertIn("PACKAGE_AUDIT_FAILED: PACKAGE_INCOMPLETE", stderr.getvalue())
            self.assertFalse((output / "main.dist" / PACKAGE_MARKER).exists())

    def test_git_provenance_scopes_safe_directory_to_the_selected_checkout(self):
        class Result: stdout = "abc123\n"
        with patch.object(build_windows.subprocess, "run", return_value=Result()) as run:
            self.assertEqual(build_windows.git_value(REPO, "rev-parse", "HEAD"), "abc123")
        command = run.call_args.args[0]
        self.assertEqual(command[:3], ["git", "-c", f"safe.directory={REPO.resolve()}"])
        self.assertEqual(command[3:], ["rev-parse", "HEAD"])

    def test_windows_paths_resources_and_recent_projects_do_not_write_install_root(self):
        with tempfile.TemporaryDirectory(prefix="bundle Ω ") as tmp:
            root=Path(tmp); bundle=root/"read only bundle"; (bundle/"assets").mkdir(parents=True); asset=bundle/"assets"/"logo.svg"; asset.write_text("x"); bundle.chmod(stat.S_IREAD|stat.S_IEXEC)
            resources=ApplicationResources.discover(executable=bundle/"QuantumStudio.exe",frozen=True)
            self.assertEqual(resources.path("assets/logo.svg"),asset); self.assertTrue(resources.packaged)
            with self.assertRaises(ResourceError): resources.path("../outside")
            env={"APPDATA":str(root/"App Data Ω"),"LOCALAPPDATA":str(root/"Local Data Ω")}; paths=runtime_paths(environ=env,home=root,platform_name="win32")
            self.assertEqual(paths.config,root/"App Data Ω"/"QuantumStudio"); self.assertEqual(paths.data,root/"Local Data Ω"/"QuantumStudio")
            project=root/"project Ω.qs"; project.write_text("{}")
            save_recent_projects([project],environ=env,home=root,platform_name="win32")
            self.assertEqual(load_recent_projects(environ=env,home=root,platform_name="win32"),[str(project.resolve())]); self.assertFalse((bundle/"recent_projects.json").exists())

    def test_manifest_installer_slots_and_package_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); plan=self.plan(root); manifest=plan.manifest(python_version="3.13",pyside6_version="6.11.2",nuitka_version="4.1.1",timestamp="2026-01-01T00:00:00Z")
            self.assertEqual(manifest["entry_executable"],"QuantumStudio.exe"); self.assertFalse(manifest["dirty"])
            inputs=installer_input_manifest(plan,manifest); self.assertEqual(inputs["runtime_image"]["status"],"PENDING_W7"); self.assertEqual(inputs["engine_pack"]["status"],"PENDING_LEGAL_AND_W7")
            package=root/"QuantumStudio.dist"; package.mkdir(); (package/"QuantumStudio.exe").write_bytes(b"native")
            incomplete = audit_package_contents(package)
            self.assertFalse(incomplete["valid"]); self.assertEqual(incomplete["reason"], "PACKAGE_INCOMPLETE")
            for relative in ("assets/quantum-studio-v0.1.svg", "PySide6/qt-plugins/platforms/qwindows.dll", "cryptography/hazmat/bindings/_rust.pyd"):
                target = package / relative; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(b"runtime")
            self.assertTrue(audit_package_contents(package)["valid"])
            (package/"pw.x").write_bytes(b"forbidden"); audit=audit_package_contents(package); self.assertFalse(audit["valid"]); self.assertIn("pw.x",audit["forbidden"])

    def test_safe_clean_requires_recognized_owned_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); plan=self.plan(root); plan.output.mkdir(parents=True)
            with self.assertRaises(WindowsBuildError): safe_clean_output(plan)
            write_json(plan.output/PACKAGE_MARKER,{"product":"Quantum Studio"}); safe_clean_output(plan); self.assertFalse(plan.output.exists())

    def test_catalogue_identity_is_preserved(self): self.assertEqual(len(CALCULATIONS),148)

    def test_public_catalogue_snapshot_and_calculate_widget_cover_each_public_family(self):
        from collections import Counter
        from frontend.calculations.catalog import public_catalogue_snapshot
        from frontend.calculate import CalculateWorkspace
        from frontend.core.project import Project
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        snapshot = public_catalogue_snapshot()
        self.assertEqual(len(snapshot), 148)
        self.assertEqual(len({item["id"] for item in snapshot}), 148)
        workspace = CalculateWorkspace(Project("Catalogue parity"))
        try:
            visible = {workspace.calculation_list.item(row).data(Qt.ItemDataRole.UserRole) for row in range(workspace.calculation_list.count())}
            self.assertEqual(visible, {item["id"] for item in snapshot})
            expected = {"bands", "dielectric", "phonons", "seebeck", "transmission", "md_nvt", "wannierization", "xrd", "free_energy", "scf"}
            self.assertTrue(expected <= visible)
            category_counts = Counter(item["category"] for item in snapshot)
            self.assertEqual(set(category_counts), {workspace.category_combo.itemText(index) for index in range(1, workspace.category_combo.count())})
            for category, expected_count in category_counts.items():
                workspace.category_combo.setCurrentText(category)
                app.processEvents()
                self.assertEqual(workspace.calculation_list.count(), expected_count)
        finally:
            workspace.close(); app.processEvents()

class ApplicationSmokeTests(unittest.TestCase):
    def test_project_hub_footer_uses_canonical_product_identity(self):
        from PySide6.QtWidgets import QApplication
        from backend.runtime import PRODUCT_NAME, VERSION
        from frontend.app.project_hub import ProjectHub
        app = QApplication.instance() or QApplication([])
        hub = ProjectHub()
        try:
            self.assertEqual(hub.product_identity_label.text(), f"{PRODUCT_NAME} · v{VERSION}")
            self.assertNotIn("v0.1", hub.product_identity_label.text())
        finally:
            hub.close(); app.processEvents()

    def test_offscreen_workspaces_and_qs_roundtrip_need_no_runtime_or_engine(self):
        from unittest.mock import patch
        from PySide6.QtWidgets import QApplication
        from frontend.app.project_hub import ProjectHub
        from frontend.builder import Builder
        from frontend.calculate import CalculateWorkspace
        from frontend.analyze import AnalyzeWorkspace
        from frontend.core.project import Project
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory(prefix="Quantum Studio Ω ") as tmp, patch.dict("os.environ", {"APPDATA": str(Path(tmp) / "App Data"), "LOCALAPPDATA": str(Path(tmp) / "Local Data")}, clear=False):
            project = Project("Packaged no-runtime smoke")
            project_path = Path(tmp) / "project Ω.qs"; project.save(project_path)
            self.assertEqual(Project.load(project_path).name, project.name)
            hub, builder, calculate, analyze = ProjectHub(), Builder(project), CalculateWorkspace(project), AnalyzeWorkspace(project)
            self.assertEqual(len(calculate.catalog_descriptors), 148)
            for widget in (hub, builder, calculate, analyze): widget.close()
            app.processEvents()

class IntegrationHarnessTests(unittest.TestCase):
    def test_harness_is_read_only_and_marks_non_windows_runtime_probe_pending(self):
        result=subprocess.run([sys.executable,"scripts/windows_integration_smoke.py"],cwd=REPO,capture_output=True,text=True,check=False)
        self.assertEqual(result.returncode,0); report=json.loads(result.stdout)
        self.assertEqual(report["mode"],"READ_ONLY")
        managed=next(item for item in report["checks"] if item["name"]=="managed_wsl")
        self.assertIn(managed["state"], {"PENDING_REAL_WINDOWS", "NOT_AVAILABLE"})
