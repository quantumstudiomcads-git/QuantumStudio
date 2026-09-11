"""Shared Help, About, and diagnostics actions for active application windows."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFileDialog, QLabel, QVBoxLayout, QMessageBox

from backend.runtime import BUILD_CHANNEL, PRODUCT_NAME, VERSION, export_diagnostics


def install_help_menu(window) -> object:
    menu = window.menuBar().addMenu("Help")
    about = menu.addAction(f"About {PRODUCT_NAME}")
    about.triggered.connect(lambda: show_about(window))
    diagnostics = menu.addAction("Export Diagnostics…")
    diagnostics.setToolTip("Export privacy-safe application diagnostics")
    diagnostics.triggered.connect(lambda: export_diagnostics_from_ui(window))
    return menu


def show_about(parent) -> None:
    dialog = QDialog(parent)
    dialog.setWindowTitle(f"About {PRODUCT_NAME}")
    dialog.setMinimumWidth(360)
    layout = QVBoxLayout(dialog)
    title = QLabel(PRODUCT_NAME, dialog)
    title.setObjectName("aboutTitle")
    layout.addWidget(title)
    layout.addWidget(QLabel(f"Version {VERSION}\nBuild channel: {BUILD_CHANNEL}\n\nScientific workstation for atomistic structures and calculation workflows.", dialog))
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dialog)
    buttons.rejected.connect(dialog.reject)
    buttons.accepted.connect(dialog.accept)
    layout.addWidget(buttons)
    dialog.exec()


def export_diagnostics_from_ui(parent) -> None:
    destination, _ = QFileDialog.getSaveFileName(parent, "Export Quantum Studio Diagnostics", "quantumstudio-diagnostics.zip", "ZIP Archives (*.zip)")
    if not destination:
        return
    try:
        output = export_diagnostics(Path(destination))
    except (OSError, ValueError) as error:
        QMessageBox.warning(parent, "Diagnostics Export Failed", f"Quantum Studio could not export diagnostics. No project data was modified.\n\n{error}")
        return
    parent.statusBar().showMessage(f"Diagnostics exported to {output}", 5000)
