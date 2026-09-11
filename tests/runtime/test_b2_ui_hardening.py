import logging
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMenu

from backend.runtime import PRODUCT_NAME, VERSION, configure_logging
from backend.runtime.logging_service import BACKUP_COUNT, MAX_BYTES, LOGGER_NAME
from frontend.app.project_hub import ProjectHub
from frontend.app.project_window import ProjectWindow
from frontend.app.theme import application_stylesheet
from frontend.core import Project


def app():
    return QApplication.instance() or QApplication([])


class B2UIHardeningTests(unittest.TestCase):
    def test_active_windows_have_help_about_and_diagnostics(self):
        app()
        hub = ProjectHub()
        project_window = ProjectWindow(Project("UI test"))
        for window in (hub, project_window):
            labels = [action.text() for action in window.menuBar().actions()]
            self.assertIn("Help", labels)
            menu = next(menu for menu in window.findChildren(QMenu) if menu.title() == "Help")
            action_labels = [action.text() for action in menu.actions()]
            self.assertIn(f"About {PRODUCT_NAME}", action_labels)
            self.assertIn("Export Diagnostics…", action_labels)
        project_window.close()
        hub.close()

    def test_about_and_identity_use_canonical_version_sources(self):
        app()
        hub = ProjectHub()
        self.assertIn(f"v{VERSION}", hub.product_identity_label.text())
        self.assertEqual(VERSION, "0.2.0")
        hub.close()

    def test_shared_theme_contains_focus_and_disabled_states(self):
        stylesheet = application_stylesheet()
        self.assertIn("QPushButton:focus", stylesheet)
        self.assertIn("QPushButton:disabled", stylesheet)
        self.assertIn("#36B8E8", stylesheet)

    def test_logging_is_bounded_and_unwritable_fallback_does_not_raise(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            logger = configure_logging(environ={"QUANTUM_STUDIO_DATA_ROOT": str(root)}, home=root, platform_name="win32")
            self.assertTrue((root / "logs" / "quantumstudio.log").is_file())
            handler = next(item for item in logger.handlers if getattr(item, "_quantumstudio", False))
            self.assertEqual(handler.maxBytes, MAX_BYTES)
            self.assertEqual(handler.backupCount, BACKUP_COUNT)
            logger.removeHandler(handler)
            handler.close()
