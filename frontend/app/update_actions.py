"""Thin asynchronous GUI integration for the platform-neutral updater."""
from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QMessageBox

from backend.update.config import configured_update_client
from backend.update.models import UpdateState


class _UpdateCheckWorker(QObject):
    finished = Signal(object)

    def __init__(self, client):
        super().__init__()
        self.client = client

    def run(self):
        self.finished.emit(self.client.check())


def _check(parent, *, interactive: bool) -> None:
    client = configured_update_client()
    if client is None:
        if interactive:
            QMessageBox.information(parent, "Check for Updates", "No approved Quantum Studio update source is configured for this build. The current installation remains usable.")
        return
    thread = QThread(parent); worker = _UpdateCheckWorker(client); worker.moveToThread(thread)
    thread.started.connect(worker.run)

    def complete(result):
        try:
            if interactive:
                if result.state is UpdateState.UPDATE_AVAILABLE:
                    notes = result.manifest.release_notes_summary or result.manifest.release_notes_url or "Release notes are available from the publisher."
                    QMessageBox.information(parent, "Quantum Studio Update Available", f"Current version: {result.current_version}\nNew version: {result.manifest.version}\nChannel: {result.manifest.channel}\nDownload size: {result.app_artifact.size} bytes\n\n{notes}\n\nDownload and installation are available after verification.")
                elif result.state is UpdateState.UP_TO_DATE:
                    QMessageBox.information(parent, "Check for Updates", f"Quantum Studio {result.current_version} is up to date on the selected channel.")
                else:
                    QMessageBox.warning(parent, "Update Check Failed", f"Quantum Studio could not verify update metadata. The current installation remains usable.\n\n{result.error}")
        finally:
            thread.quit()

    worker.finished.connect(complete)
    thread.finished.connect(worker.deleteLater); thread.finished.connect(thread.deleteLater)
    thread.start()


def check_for_updates_from_ui(parent) -> None:
    _check(parent, interactive=True)


def schedule_startup_update_check(parent) -> None:
    """Start an optional check after the window is visible; never block startup."""
    _check(parent, interactive=False)
