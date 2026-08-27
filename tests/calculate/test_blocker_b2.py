import hashlib
import io
import os
import tarfile
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from backend.pseudopotentials import DownloadableProvider, ProvisionError, PseudoProvisioner
from frontend.calculate import CalculateWorkspace
from frontend.core import Atom, Project, Structure


def _archive(members, directory=True):
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w:gz") as archive:
        if directory:
            info = tarfile.TarInfo(".")
            info.type = tarfile.DIRTYPE
            archive.addfile(info)
        for name, body in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(body)
            archive.addfile(info, io.BytesIO(body))
    return payload.getvalue()


def _upf_v2(element="Si"):
    return (f'<UPF version="2.0.1"><PP_HEADER element=" {element} " functional=" PBE " '
            'pseudo_type="USPP" relativistic="scalar"/></UPF>').encode()


def _upf_v1(element="Zr"):
    return (f"<PP_INFO>The Pseudo was generated with a Scalar-Relativistic Calculation</PP_INFO>\n"
            f"<PP_HEADER>\n  0 Version Number\n  {element} Element\n  US Ultrasoft pseudopotential\n"
            "SLA PW PBE PBE PBE Exchange-Correlation functional\n</PP_HEADER>").encode()


def _workspace(root):
    project = Project("B2", Path(root) / "b2.qs")
    structure = Structure([Atom("Si", 0, 0, 0)], [[4, 0, 0], [0, 4, 0], [0, 0, 4]])
    structure.periodic = [True, True, True]
    project.set_structure(structure)
    workspace = CalculateWorkspace(project)
    workspace.show()
    workspace.selected_ids = ["scf"]
    request = workspace.create_persistent_calculation(
        {"xc_functional": "pbe", "pseudopotential_mode": "auto"}, "SCF"
    )
    workspace._refresh_configured_calculations(request.id)
    return workspace


def _wait(app, predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()
    return predicate()


class BlockerB2Tests(unittest.TestCase):
    def test_official_archive_shape_legacy_upf_and_metadata_are_installed(self):
        payload = _archive({"./Zr_pbe_v1.uspp.F.UPF": _upf_v1(), "./Si.pbe.UPF": _upf_v2()})
        metadata = b'{"Si":{"filename":"Si.pbe.UPF","cutoff_wfc":30.0,"cutoff_rho":240.0}}'
        provider = DownloadableProvider(
            "sssp_efficiency", "SSSP Efficiency", "1.3.0",
            "https://archive.materialscloud.org/archive.tar.gz", hashlib.md5(payload).hexdigest(),
            ("pbe",), 1024 * 1024, metadata_url="https://archive.materialscloud.org/metadata.json",
        )
        calls = []
        def transport(url, maximum):
            calls.append(url)
            return metadata if url.endswith("metadata.json") else payload
        with tempfile.TemporaryDirectory() as root:
            provisioner = PseudoProvisioner(root, (provider,), transport)
            first = provisioner.provision("Si", "pbe")
            count = len(calls)
            second = provisioner.provision("Si", "pbe")
            self.assertTrue(first.downloaded)
            self.assertFalse(second.downloaded)
            self.assertEqual(len(calls), count)
            self.assertEqual(len(provisioner._records(provider)), 2)
            self.assertEqual(first.record.recommended_ecutwfc_ry, 30.0)
            self.assertEqual(first.record.recommended_ecutrho_ry, 240.0)
            self.assertEqual(first.record.sha256, hashlib.sha256(_upf_v2()).hexdigest())

    def test_generate_preparation_is_async_and_recovers_buttons(self):
        app = QApplication.instance() or QApplication([])
        payload = _archive({"Si.UPF": _upf_v2()})
        provider = DownloadableProvider(
            "fixture", "Slow Fixture", "1", "https://archive.materialscloud.org/slow.tar.gz",
            hashlib.md5(payload).hexdigest(), ("pbe",), 1024 * 1024,
        )
        with tempfile.TemporaryDirectory() as root:
            workspace = _workspace(root)
            def slow_transport(url, maximum):
                time.sleep(0.2)
                return payload
            workspace._pseudo_provisioner = PseudoProvisioner(Path(root) / "cache", (provider,), slow_transport)
            responsive = []
            QTimer.singleShot(0, lambda: responsive.append(True))
            with patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok), patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Ok):
                workspace.generate_qe_button.click()
                self.assertIsNotNone(workspace._preparation_worker)
                self.assertTrue(_wait(app, lambda: bool(responsive), 1))
                self.assertTrue(_wait(app, lambda: workspace._preparation_worker is None))
            self.assertTrue(workspace._workflow_generated)
            self.assertTrue(workspace.execute_button.isEnabled())
            self.assertTrue(list(Path(workspace._generated_root_path).rglob("scf.in")))
            workspace.close()

    def test_preparation_error_keeps_gui_responsive_and_restores_actions(self):
        app = QApplication.instance() or QApplication([])
        provider = DownloadableProvider("fixture", "Broken", "1", "https://archive.materialscloud.org/broken.tar.gz")
        with tempfile.TemporaryDirectory() as root:
            workspace = _workspace(root)
            def fail(url, maximum):
                time.sleep(0.1)
                raise ProvisionError("Could not reach the SSSP provider. No compatible cached pseudopotential is available.")
            workspace._pseudo_provisioner = PseudoProvisioner(Path(root) / "cache", (provider,), fail)
            messages = []
            with patch.object(QMessageBox, "warning", side_effect=lambda parent, title, message: messages.append(message)):
                workspace.generate_qe_button.click()
                self.assertTrue(_wait(app, lambda: workspace._preparation_worker is None))
            self.assertTrue(workspace.generate_qe_button.isEnabled())
            self.assertTrue(workspace.execute_button.isEnabled())
            self.assertTrue(workspace.edit_parameters_button.isEnabled())
            self.assertIn("Could not reach", messages[-1])
            workspace.close()

    def test_real_run_button_prepares_and_executes_fake_pw(self):
        app = QApplication.instance() or QApplication([])
        payload = _archive({"Si.UPF": _upf_v2()})
        provider = DownloadableProvider(
            "fixture", "Fixture", "1", "https://archive.materialscloud.org/fixture.tar.gz",
            hashlib.md5(payload).hexdigest(), ("pbe",), 1024 * 1024,
        )
        with tempfile.TemporaryDirectory() as root:
            fake = Path(root) / "pw.x"
            fake.write_text("#!/bin/sh\ncat >/dev/null\necho fake-qe-ok\n", encoding="utf-8")
            fake.chmod(0o755)
            workspace = _workspace(root)
            workspace._pseudo_provisioner = PseudoProvisioner(Path(root) / "cache", (provider,), lambda *_: payload)
            workspace.local_tool_configuration.tool_paths = {"pw.x": str(fake)}
            with patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok), patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Ok), patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
                workspace.execute_button.click()
                self.assertTrue(_wait(app, lambda: workspace._preparation_worker is None and workspace._active_execution is None, 12))
            self.assertTrue(workspace._workflow_generated)
            self.assertEqual(workspace.execute_button.text(), "Run")
            self.assertIn("COMPLETED", workspace.execution_preview.text())
            workspace.close()


if __name__ == "__main__":
    unittest.main()
