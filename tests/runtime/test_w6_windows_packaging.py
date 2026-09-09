import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

from backend.runtime.paths import runtime_paths
from backend.runtime.resources import ApplicationResources, ResourceError
from frontend.app.recent_projects import load_recent_projects, save_recent_projects
from frontend.calculations.catalog import CALCULATIONS
from scripts.windows_packaging import (PACKAGE_MARKER, WindowsBuildError, audit_package_contents, build_plan, installer_input_manifest, safe_clean_output, write_json)

REPO = Path(__file__).resolve().parents[2]

class WindowsPackagingTests(unittest.TestCase):
    def plan(self, root):
        return build_plan(repo=REPO, output=root / "dist Ω", channel="beta", version="0.2.0", commit="abc123", dirty=False, python_executable="python.exe")

    def test_windows_nuitka_plan_is_structured_and_has_product_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan=self.plan(Path(tmp)); argv=plan.nuitka_argv
            self.assertEqual(argv[:4], ("python.exe", "-m", "nuitka", "--standalone")); self.assertIn("--enable-plugin=pyside6",argv)
            self.assertIn("--windows-console-mode=disable",argv); self.assertIn("--product-name=Quantum Studio",argv)
            self.assertIn("--include-module=scipy._external.array_api_compat.numpy.fft", argv)
            self.assertIn("--output-filename=QuantumStudio.exe",argv); self.assertTrue(any(item.startswith("--include-data-dir=") for item in argv))
            self.assertNotIn("cmd.exe",str(argv)); self.assertNotIn("PowerShell",str(argv))

    def test_non_windows_build_is_plan_only_not_fake_success(self):
        result=subprocess.run([sys.executable,"scripts/build_windows.py","--dry-run","--output","dist/windows test"],cwd=REPO,capture_output=True,text=True,check=False)
        self.assertEqual(result.returncode,0); self.assertIn('"status": "PLAN_ONLY"',result.stdout)
        actual=subprocess.run([sys.executable,"scripts/build_windows.py","--output","dist/windows test"],cwd=REPO,capture_output=True,text=True,check=False)
        if sys.platform.startswith("win"):
            self.assertEqual(actual.returncode,2); self.assertIn("Refusing a dirty beta/release Windows build",actual.stderr)
        else:
            self.assertEqual(actual.returncode,2); self.assertIn("WINDOWS_BUILD_HOST_REQUIRED",actual.stderr)

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
            self.assertTrue(audit_package_contents(package)["valid"])
            (package/"pw.x").write_bytes(b"forbidden"); audit=audit_package_contents(package); self.assertFalse(audit["valid"]); self.assertIn("pw.x",audit["forbidden"])

    def test_safe_clean_requires_recognized_owned_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); plan=self.plan(root); plan.output.mkdir(parents=True)
            with self.assertRaises(WindowsBuildError): safe_clean_output(plan)
            write_json(plan.output/PACKAGE_MARKER,{"product":"Quantum Studio"}); safe_clean_output(plan); self.assertFalse(plan.output.exists())

    def test_catalogue_identity_is_preserved(self): self.assertEqual(len(CALCULATIONS),147)

class ApplicationSmokeTests(unittest.TestCase):
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
            self.assertEqual(len(calculate.catalog_descriptors), 147)
            for widget in (hub, builder, calculate, analyze): widget.close()
            app.processEvents()

class IntegrationHarnessTests(unittest.TestCase):
    def test_harness_is_read_only_and_marks_non_windows_runtime_probe_pending(self):
        result=subprocess.run([sys.executable,"scripts/windows_integration_smoke.py"],cwd=REPO,capture_output=True,text=True,check=False)
        self.assertEqual(result.returncode,0); report=json.loads(result.stdout)
        self.assertEqual(report["mode"],"READ_ONLY")
        managed=next(item for item in report["checks"] if item["name"]=="managed_wsl")
        self.assertIn(managed["state"], {"PENDING_REAL_WINDOWS", "NOT_AVAILABLE"})
