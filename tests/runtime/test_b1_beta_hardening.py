import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile

from backend.runtime.diagnostics_service import export_diagnostics
from frontend.app.recent_projects import load_recent_projects, save_recent_projects
from frontend.core.project import Project, ProjectLoadError


class B1BetaHardeningTests(unittest.TestCase):
    def test_corrupt_project_fixtures_fail_actionably_without_rewrite(self):
        fixtures = [
            "",
            "{\"format\": \"qstudio\", \"version\": \"9.0\"}",
            json.dumps({"format": "qstudio", "version": "0.4", "structure": []}),
            json.dumps({"format": "qstudio", "version": "0.4", "structure": {"atoms": [{"element": "Si", "x": "bad", "y": 0, "z": 0}]}}),
        ]
        with TemporaryDirectory() as directory:
            for index, contents in enumerate(fixtures):
                path = Path(directory) / f"broken-{index}.qs"
                path.write_text(contents, encoding="utf-8")
                original = path.read_bytes()
                with self.assertRaises(ProjectLoadError) as failure:
                    Project.load(path)
                self.assertTrue(str(failure.exception))
                self.assertEqual(path.read_bytes(), original)

    def test_save_as_failure_does_not_change_project_identity(self):
        with TemporaryDirectory() as directory:
            original = Path(directory) / "original.qs"
            project = Project("safe", original)
            project.save()
            before = project.file_path
            # A file used as a parent is a deterministic permission/path failure.
            blocked = Path(directory) / "file-parent"
            blocked.write_text("not a directory", encoding="utf-8")
            with self.assertRaises(OSError):
                project.save(blocked / "target.qs")
            self.assertEqual(project.file_path, before)
            self.assertTrue(original.is_file())

    def test_recent_state_ignores_malformed_entries_and_writes_atomically(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            env = {"QUANTUM_STUDIO_CONFIG_ROOT": str(root / "config")}
            recent = root / "config" / "recent_projects.json"
            recent.parent.mkdir()
            recent.write_text(json.dumps([None, 3, str(root / "missing.qs")]), encoding="utf-8")
            self.assertEqual(load_recent_projects(environ=env, home=root, platform_name="win32"), [])
            project = root / "ok.qs"
            project.write_text("{}", encoding="utf-8")
            save_recent_projects([project, project, None], environ=env, home=root, platform_name="win32")
            self.assertEqual(load_recent_projects(environ=env, home=root, platform_name="win32"), [str(project.resolve())])
            self.assertFalse(list(recent.parent.glob(".*.tmp")))

    def test_diagnostics_export_contains_manifest_only(self):
        with TemporaryDirectory() as directory:
            output = export_diagnostics(Path(directory) / "diagnostics.zip", environ={"QUANTUM_STUDIO_DATA_ROOT": directory}, home=directory, platform_name="win32")
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(archive.namelist(), ["manifest.json"])
                manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(manifest["schema_version"], "1")
            self.assertNotIn("project", manifest)
            self.assertNotIn("atomic_coordinates", manifest)
