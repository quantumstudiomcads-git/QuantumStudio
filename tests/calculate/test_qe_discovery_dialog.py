import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton

from frontend.calculate import CalculateWorkspace
from frontend.core import Project


class QuantumEspressoLocalToolsDialogTests(unittest.TestCase):
    def test_normal_view_is_installation_oriented(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as root:
            workspace = CalculateWorkspace(Project("QE", Path(root) / "qe.qs"))
            config = workspace.local_tool_configuration
            config.qe_version = "7.6"
            config.qe_bin_directory = "/fixture/qe/7.6/bin"
            config.tool_paths = {"pw.x": "/fixture/qe/7.6/bin/pw.x"}
            observed = {}
            def inspect():
                dialog = workspace.findChild(QDialog)
                observed["labels"] = {label.text() for label in dialog.findChildren(QLabel)}
                observed["buttons"] = {button.text() for button in dialog.findChildren(QPushButton)}
                return QDialog.DialogCode.Rejected
            with patch.object(workspace, "_start_qe_discovery"), patch.object(QDialog, "exec", autospec=True, side_effect=inspect):
                workspace._configure_local_tools()
            self.assertIn("✓ Quantum ESPRESSO 7.6 detected", observed["labels"])
            self.assertIn("Installation: /fixture/qe/7.6/bin", observed["labels"])
            self.assertIn("Rescan", observed["buttons"])
            self.assertIn("Choose Installation Folder", observed["buttons"])
            workspace.close()


