import os
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from backend.execution.discovery import ToolDiscoveryResult, validate_qe_installation
from backend.pseudopotentials import DownloadableProvider, PseudoProvisioner
from frontend.calculate import CalculateWorkspace
from frontend.core import Atom, Project, Structure
from tests.helpers.fake_executable import write_fake_executable


def fake_qe(root):
    directory = Path(root) / "qe" / "7.6" / "bin"
    directory.mkdir(parents=True)
    for name in ("pw.x", "bands.x", "dos.x", "ph.x", "q2r.x", "matdyn.x"):
        path = directory / name
        if name == "pw.x":
            if os.name == "nt":
                physical = write_fake_executable(path, "import sys\nsys.stdin.read()\nprint('fake-qe-ok')\n")
                path.write_text("Program PWSCF v.7.6\n", encoding="utf-8")
            else:
                path.write_text("#!/bin/sh\ncat >/dev/null\necho 'Program PWSCF v.7.6'\n", encoding="utf-8"); physical = path
        else:
            if os.name == "nt": physical = write_fake_executable(path, "pass\n"); path.write_text("fixture\n", encoding="utf-8")
            else: path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8"); physical = path
        if os.name != "nt": path.chmod(0o755)
    return directory, {name: str(directory / name) if os.name != "nt" else str(directory / (name + ".cmd")) for name in ("pw.x", "bands.x", "dos.x", "ph.x", "q2r.x", "matdyn.x")}


def pseudo_archive():
    import hashlib, io, tarfile
    body = b'<UPF version="2"><PP_HEADER element="Si" functional="PBE" pseudo_type="NC" relativistic="scalar-relativistic"/></UPF>'
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        entry = tarfile.TarInfo("Si.UPF"); entry.size = len(body); archive.addfile(entry, io.BytesIO(body))
    return stream.getvalue(), hashlib.md5(stream.getvalue()).hexdigest()


def wait(app, predicate, timeout=10):
    limit = time.monotonic() + timeout
    while not predicate() and time.monotonic() < limit:
        app.processEvents(); time.sleep(0.01)
    app.processEvents()
    return predicate()


class QuantumEspressoWorkspaceTests(unittest.TestCase):
    def test_real_run_button_auto_discovers_and_resumes(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {"QUANTUM_STUDIO_LOCAL_TOOLS": str(Path(root) / "tools.json")}, clear=False):
            directory, physical = fake_qe(root)
            if os.name == "nt":
                with patch("backend.execution.discovery.subprocess.run", return_value=type("Probe", (), {"stdout": "Program PWSCF v.7.6", "stderr": "", "returncode": 0})()):
                    installation = validate_qe_installation(directory)
                installation = replace(installation, tools=physical)
            else: installation = validate_qe_installation(directory)
            discovery = ToolDiscoveryResult((installation,), ())
            payload, checksum = pseudo_archive()
            provider = DownloadableProvider("fixture", "Fixture", "1", "https://archive.materialscloud.org/fixture.tar.gz", checksum, ("pbe",), 1024 * 1024)
            project = Project("QE", Path(root) / "qe.qs")
            structure = Structure([Atom("Si", 0, 0, 0)], [[4,0,0], [0,4,0], [0,0,4]])
            structure.periodic = [True, True, True]; project.set_structure(structure)
            with patch("frontend.calculate.qe_discovery.discover_quantum_espresso", return_value=discovery):
                workspace = CalculateWorkspace(project); workspace.show(); app.processEvents()
                self.assertTrue(wait(app, lambda: workspace._qe_discovery_worker is None))
                workspace.selected_ids = ["scf"]
                request = workspace.create_persistent_calculation({"xc_functional":"pbe", "pseudopotential_mode":"auto"}, "SCF")
                workspace._refresh_configured_calculations(request.id)
                workspace._pseudo_provisioner = PseudoProvisioner(Path(root) / "cache", (provider,), lambda *_: payload)
                responsive = []
                QTimer.singleShot(0, lambda: responsive.append(True))
                with patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok), patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Ok), patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
                    workspace.execute_button.click()
                    self.assertTrue(wait(app, lambda: bool(responsive)))
                    self.assertTrue(wait(app, lambda: workspace._preparation_worker is None and workspace._active_execution is None, 12))
                self.assertEqual(workspace.local_tool_configuration.qe_version, "7.6")
                self.assertEqual(Path(workspace.local_tool_configuration.tool_paths["pw.x"]), Path(physical["pw.x"]))
                self.assertIn("COMPLETED", workspace.execution_preview.text())
                self.assertTrue((Path(workspace._generated_root_path) / "pseudos" / "Si.UPF").is_file())
                workspace.close()


if __name__ == "__main__":
    unittest.main()
