"""Application-shell access controller for entitlement-protected workspaces."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from backend.licensing.enforcement import EntitlementDenied


class EntitlementUnavailableWorkspace(QWidget):
    def __init__(self, decision, parent=None):
        super().__init__(parent)
        self.decision = decision
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel("Device Builder is not available")
        title.setObjectName("workspaceTitle")
        message = QLabel(decision.remediation or "A valid Pro or Organization entitlement is required.")
        message.setObjectName("workspaceDescription")
        message.setWordWrap(True)
        message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(message, alignment=Qt.AlignmentFlag.AlignCenter)


class DeviceBuilderAccessController:
    FEATURE_ID = "workspace:device_builder"

    def __init__(self, licensing_service=None):
        self.licensing_service = licensing_service

    def authorize(self):
        if self.licensing_service is None:
            return None
        decision = self.licensing_service.authorize_feature(self.FEATURE_ID)
        if not decision.allowed:
            raise EntitlementDenied(decision)
        return decision

    def create_workspace(self, project, parent=None):
        try:
            self.authorize()
        except EntitlementDenied as error:
            return EntitlementUnavailableWorkspace(error.decision, parent)
        from frontend.device_builder import DeviceBuilderWorkspace
        return DeviceBuilderWorkspace(project, parent)
