"""Minimal browser activation UI; all transport runs outside the Qt event loop."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from threading import Event
from PySide6.QtCore import QThread, Signal, QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton, QHBoxLayout, QVBoxLayout
from backend.runtime import VERSION
from backend.licensing.desktop_auth import DesktopActivationFlow
from backend.licensing.licence_delivery import LicenceDeliveryService
from backend.licensing.connectors.licence_delivery import WebsiteLicenceDeliveryConnector, LicenceDeliveryError
from backend.licensing.device_identity import DeviceIdentityService, production_secure_store, SecureStorageUnavailable
from backend.licensing.verifier import LeaseValidationError
from backend.licensing.lease_store import LeaseStoreError
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
                self.activation_id = data.get("activation", {}).get("activation_request_id")
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


class DeliveryWorker(QThread):
    result = Signal(str, str)

    def __init__(self, delivery, activation_id=None):
        super().__init__(QApplication.instance())
        self.delivery = delivery
        self.activation_id = activation_id
        self.cancelled = Event()

    def cancel(self):
        self.cancelled.set()

    def shutdown(self):
        self.cancel()
        self.wait(11000)

    def run(self):
        try:
            state = self.delivery.retrieve_and_install(self.activation_id, cancelled=self.cancelled)
            self.result.emit(state, "")
        except LeaseValidationError as error:
            self.result.emit("delivery_error", "Invalid licence: " + str(error))
        except (LicenceDeliveryError, SecureStorageUnavailable) as error:
            self.result.emit("delivery_error", str(error))
        except (OSError, LeaseStoreError):
            self.result.emit("delivery_error", "The licence could not be stored. No new entitlement was granted.")
        except Exception:
            self.result.emit("delivery_error", "The signed licence could not be retrieved or verified.")


class AccountLicensingDialog(QDialog):
    def __init__(self, parent=None, *, licensing_service=None, connector=None, open_browser=None, delivery_factory=None):
        super().__init__(parent)
        self.setWindowTitle("Quantum Studio Account / Licensing")
        self.setMinimumWidth(460)
        self._service = licensing_service
        self._delivery_factory = delivery_factory
        self._check_after_activation = False
        self._activation_id = None
        self._retrieval_blocked = False
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
        self.licence_summary = QLabel()
        self.licence_summary.setWordWrap(True)
        layout.addWidget(self.licence_summary)
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
        self.check_button = QPushButton("Check licence")
        self.cancel_button = QPushButton("Cancel activation")
        self.cancel_button.setEnabled(False)
        close = QPushButton("Close")
        row.addWidget(self.start_button)
        row.addWidget(self.check_button)
        row.addWidget(self.cancel_button)
        row.addWidget(close)
        layout.addLayout(row)
        self.start_button.clicked.connect(self.start_activation)
        self.check_button.clicked.connect(self.check_licence)
        self.cancel_button.clicked.connect(self.cancel_activation)
        close.clicked.connect(self.reject)
        self._refresh_licence_summary()
        if summary.get("status") == "active":
            self.status.setText("Your verified cached licence is Active. Browser sign-in is not required while it remains valid.")

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
        self._retrieval_blocked = False
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
        self.check_button.setEnabled(False)
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
        if state == "completed" and detail in ("FLAGGED", "REVOKED"):
            self._retrieval_blocked = True
            self._check_after_activation = False
            self._activation_id = None
            self.check_button.setEnabled(False)
        if state == "completed" and detail == "AUTHORIZED":
            self._activation_id = getattr(self._worker, "activation_id", None)
            self._check_after_activation = True
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
        self.check_button.setEnabled(not self._retrieval_blocked)
        self._refresh_licence_summary()
        if self._check_after_activation and not self._closing:
            self._check_after_activation = False
            if self._service is not None and self._service.lease_store is not None:
                self.check_licence()
            else:
                self.status.setText("Device authorized (AUTHORIZED) - licence pending. Persistent licensing service is unavailable.")

    def _refresh_licence_summary(self):
        summary = self._service.diagnostics_summary() if self._service else {}
        raw_status = summary.get("status", "auth_required")
        status = {"active": "Active", "auth_required": "Auth Required", "expired": "Expired",
                  "invalid": "Invalid licence", "licence_cache_invalid": "Invalid licence",
                  "test_trust_invalid": "Invalid TEST trust configuration"}.get(raw_status, str(raw_status).replace("_", " ").title())
        expiry = summary.get("expires_at")
        if expiry:
            expiry = datetime.fromtimestamp(expiry, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        mode = "TEST LICENSING - explicit local trust\n" if summary.get("test_mode") else ""
        self.licence_summary.setText(f"{mode}Licence status: {status}\nPlan: {summary.get('plan_id') or 'None'}\nExpiry: {expiry or 'Not available'}\nLicence ID: {summary.get('licence_id') or 'None'}")
        self.start_button.setVisible(raw_status != "active")

    def check_licence(self):
        if self._worker is not None or self._closing or self._retrieval_blocked:
            return
        try:
            if self._delivery_factory:
                delivery = self._delivery_factory()
            else:
                if self._service is None or self._service.lease_store is None:
                    raise LicenceDeliveryError("Persistent licensing is unavailable.")
                connector = WebsiteLicenceDeliveryConnector(os.environ.get("QS_WEBSITE_URL", ""),
                    allow_local_http=os.environ.get("QS_DESKTOP_AUTH_ALLOW_LOCAL_HTTP") == "1")
                identity_service = DeviceIdentityService(production_secure_store(self._service.lease_store.paths))
                trust_loader = (lambda: self._service.reload_local_test_trust(
                    os.environ.get("QS_TEST_LICENCE_TRUST_FILE", ""))) if self._service.test_mode else None
                delivery = LicenceDeliveryService(self._service, connector, identity_service, trust_loader=trust_loader)
        except (DesktopAuthError, LicenceDeliveryError, SecureStorageUnavailable) as error:
            self.status.setText("Licence check unavailable. " + str(error))
            return
        worker = DeliveryWorker(delivery, self._activation_id)
        self._worker = worker
        _RUNNING.add(worker)
        worker.result.connect(self._show_delivery_result)
        worker.finished.connect(self._finished)
        worker.finished.connect(lambda: _RUNNING.discard(worker))
        worker.finished.connect(worker.deleteLater)
        QApplication.instance().aboutToQuit.connect(worker.shutdown)
        self.start_button.setEnabled(False)
        self.check_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.status.setText("Checking signed licence with device proof...")
        worker.start()

    def _show_delivery_result(self, state, detail):
        if self._closing:
            return
        self._refresh_licence_summary()
        if state == "installed":
            self.status.setText("Active - signed licence verified and stored for offline startup.")
        elif state == "pending":
            self.status.setText("Device authorized - licence pending. No signed licence has been published yet.")
        else:
            self.status.setText(detail)

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
