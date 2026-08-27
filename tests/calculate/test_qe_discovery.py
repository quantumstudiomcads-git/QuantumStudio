import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.execution.discovery import discover_quantum_espresso, validate_qe_installation


def make_qe(root, version="7.6", tools=("pw.x", "bands.x", "dos.x", "ph.x")):
    directory = Path(root) / "qe" / version / "bin"
    directory.mkdir(parents=True)
    for tool in tools:
        path = directory / tool
        if tool == "pw.x":
            path.write_text(f"#!/bin/sh\necho 'Program PWSCF v.{version}'\n", encoding="utf-8")
        else:
            path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        path.chmod(0o755)
    return directory


class QuantumEspressoDiscoveryTests(unittest.TestCase):
    def test_directory_root_and_file_inputs_populate_siblings(self):
        with tempfile.TemporaryDirectory() as root:
            directory = make_qe(root)
            for candidate in (directory, directory.parent, directory / "pw.x"):
                installation = validate_qe_installation(candidate)
                self.assertIsNotNone(installation)
                self.assertEqual(installation.version, "7.6")
                self.assertEqual(Path(installation.tools["pw.x"]), directory / "pw.x")
                self.assertIn("bands.x", installation.tools)
                self.assertIn("ph.x", installation.tools)

    def test_false_pw_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "pw.x"
            path.write_text("#!/bin/sh\necho 'Other tool v.7.6'\n", encoding="utf-8")
            path.chmod(0o755)
            self.assertIsNone(validate_qe_installation(path))

    def test_path_and_repository_candidates_prefer_76(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            path_bin = make_qe(root / "path", "7.6")
            repo_bin = root / "software" / "engines" / "qe" / "7.6" / "bin"
            repo_bin.parent.mkdir(parents=True)
            source = make_qe(root / "repo", "7.6")
            repo_bin.mkdir(parents=True)
            for item in source.iterdir():
                target = repo_bin / item.name
                target.write_bytes(item.read_bytes())
                target.chmod(0o755)
            import backend.execution.discovery as module
            with patch.object(module, "_repo_root", return_value=root), patch.object(module, "Path") as path_class:
                path_class.home.return_value = root / "empty-home"
                path_class.side_effect = Path
                result = discover_quantum_espresso(environment={"PATH": str(path_bin)})
            self.assertEqual(result.preferred.version, "7.6")
            self.assertEqual(Path(result.preferred.bin_directory), path_bin)

    def test_saved_path_is_used_when_path_is_empty(self):
        with tempfile.TemporaryDirectory() as root:
            directory = make_qe(root, "7.6")
            import backend.execution.discovery as module
            with patch.object(module, "_known_candidates", return_value=((directory, "saved"),)):
                result = discover_quantum_espresso(existing_directory=str(directory), environment={"PATH": "/missing"})
            self.assertEqual(result.preferred.version, "7.6")
            self.assertEqual(Path(result.preferred.pw_path), directory / "pw.x")


if __name__ == "__main__":
    unittest.main()
