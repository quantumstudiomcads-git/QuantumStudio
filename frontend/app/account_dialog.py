"""Minimal browser activation UI; all transport runs outside the Qt event loop."""
from __future__ import annotations

import os
from threading import Event
from PySide6.QtCore import QThread, Signal, QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton, QHBoxLayout, QVBoxLayout
from backend.runtime import VERSION
from backend.licensing.desktop_auth import DesktopActivationFlow
from backend.licensing.connectors.desktop_auth import DesktopAuthError, WebsiteDesktopActivationConnector

_RUNNING = set()


class ActivationWorker(QThread):
    browser_requested = Signal(str)
    result = Signal(str, str)

    def __init__(self, connector, device):
        super().__init__(QApplication.instance())
        self.connector = connector
        self.device = device
        self.cancelled = Event()

    def cancel(self):
        self.cancelled.set()

    def shutdown(self):
        self.cancel()
        self.wait(11000)  # At most one bounded request plus best-effort cancellation.

    def run(self):
        flow = None
        try:
            flow = DesktopActivationFlow(self.connector, self.device, VERSION)
            url = flow.start()
            if not self.cancelled.is_set():
                self.browser_requested.emit(url)
            while not self.cancelled.wait(flow.interval):
                try:
                    data = flow.poll()
                except DesktopAuthError as error:
                    if error.code == "slow_down":
                        continue
                    raise
                if self.cancelled.is_set():
                    flow.cancel()
                    self.result.emit("cancelled", "")
                    return
                state = data["state"]
                if state == "pending":
                    continue
                self.result.emit(state, data.get("activation", {}).get("status", ""))
                return
            flow.cancel()
            self.result.emit("cancelled", "")
        except DesktopAuthError as error:
            if flow is not None:
                flow.cancel()
            self.result.emit("cancelled" if self.cancelled.is_set() else "error", str(error))
        except Exception:
            if flow is not None:
                flow.cancel()
            self.result.emit("error", "Desktop activation could not be completed. Please try again.")


class AccountLicensingDialog(QDialog):
    def __init__(self, parent=None, *, licensing_service=None, connector=None, open_browser=None):
        super().__init__(parent)
        self.setWindowTitle("Quantum Studio Account / Licensing")
        self.setMinimumWidth(460)
        self._service = licensing_service
        self._connector = connector
        self._open_browser = open_browser or (lambda url: QDesktopServices.openUrl(QUrl(url)))
        self._worker = None
        self._closing = False
        self._browser_error = False
        layout = QVBoxLayout(self)
        title = QLabel("Account / Licensing")
        layout.addWidget(title)
        summary = licensing_service.diagnostics_summary() if licensing_service else {}
        local_status = str(summary.get('status', 'unavailable')).replace('_', ' ').title()
        layout.addWidget(QLabel(f"Licence status: {local_status}\nPlan: {summary.get('plan_id') or 'None'}\nExpiry: {summary.get('expires_at') or 'Not available'}"))
        device = getattr(licensing_service, "device_identity", None)
        device_label = QLabel(f"Device: {device.device_id if device else 'Unavailable'}")
        device_label.setWordWrap(True)
        device_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(device_label)
        note = QLabel("Existing projects and results remain available when an entitlement expires.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.status = QLabel("Sign in in your browser to register this device. Device activation does not install a licence.")
        self.status.setWordWrap(True)
        self.status.setAccessibleName("Desktop activation status")
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.start_button = QPushButton("Sign in / Activate")
        self.cancel_button = QPushButton("Cancel activation")
        self.cancel_button.setEnabled(False)
        close = QPushButton("Close")
        row.addWidget(self.start_button)
        row.addWidget(self.cancel_button)
        row.addWidget(close)
        layout.addLayout(row)
        self.start_button.clicked.connect(self.start_activation)
        self.cancel_button.clicked.connect(self.cancel_activation)
        close.clicked.connect(self.reject)

    def start_activation(self):
        if self._worker is not None:
            return
        try:
            connector = self._connector or WebsiteDesktopActivationConnector(
                os.environ.get("QS_WEBSITE_URL", ""),
                allow_local_http=os.environ.get("QS_DESKTOP_AUTH_ALLOW_LOCAL_HTTP") == "1")
            device = getattr(self._service, "device_identity", None)
            if device is None:
                raise DesktopAuthError("The protected device identity is unavailable. Sign-in requires the existing Windows DPAPI identity.")
        except DesktopAuthError as error:
            self.status.setText(str(error))
            return
        self._browser_error = False
        worker = ActivationWorker(connector, device)
        self._worker = worker
        _RUNNING.add(worker)
        worker.browser_requested.connect(self._launch_browser)
        worker.result.connect(self._show_result)
        worker.finished.connect(self._finished)
        worker.finished.connect(lambda: _RUNNING.discard(worker))
        worker.finished.connect(worker.deleteLater)
        QApplication.instance().aboutToQuit.connect(worker.shutdown)
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.status.setText("Starting secure browser sign-in?")
        worker.start()

    def _launch_browser(self, url):
        if self._closing or self._worker is None or self._worker.cancelled.is_set():
            return
        try:
            opened = self._open_browser(url)
        except Exception:
            opened = False
        if not opened:
            self._browser_error = True
            self.cancel_activation()
            self.status.setText("The system browser could not be opened. Retry Sign in / Activate.")
            return
        self.status.setText("Waiting for browser confirmation. Sign in and confirm this device on the Quantum Studio website.")

    def _show_result(self, state, detail):
        if self._closing:
            return
        if state == "cancelled" and self._browser_error:
            self.status.setText("The system browser could not be opened. Retry Sign in / Activate.")
            return
        messages = {
            "completed": {"AUTHORIZED": "Device authorized (AUTHORIZED).", "FLAGGED": "Device needs review (FLAGGED). Contact Quantum Studio support.", "REVOKED": "This device registration is revoked."}.get(detail, "Activation could not be confirmed."),
            "expired": "Sign-in timed out. Start Sign in / Activate again.",
            "cancelled": "Activation cancelled.",
            "consumed": "This challenge was already consumed. Start again to check device activation.",
            "failed": "Device activation failed. Check that your account has a linked beta application, then try again.",
            "error": detail,
        }
        self.status.setText(messages.get(state, "Activation could not be completed."))

    def _finished(self):
        self._worker = None
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

    def cancel_activation(self):
        if self._worker is not None:
            self._worker.cancel()
            self.cancel_button.setEnabled(False)
            self.status.setText("Cancelling activation?")

    def reject(self):
        self._closing = True
        self.cancel_activation()
        super().reject()

    def closeEvent(self, event):
        self._closing = True
        self.cancel_activation()
        super().closeEvent(event)
