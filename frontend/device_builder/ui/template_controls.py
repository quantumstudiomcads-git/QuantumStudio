"""Compact Device Template selector; template parameters live in a dialog."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QFormLayout, QGroupBox, QLabel, QPushButton, QVBoxLayout, QWidget


class TemplateControls(QWidget):
    """Registry-driven template entry point without workspace-specific branching."""

    create_requested = Signal(str)

    def __init__(self, registry, parent=None):
        super().__init__(parent)
        self.registry = registry
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        group = QGroupBox("DEVICE TEMPLATE")
        form = QFormLayout(group)
        self.template = QComboBox()
        for item in registry.list_templates():
            self.template.addItem(item.name, item.id)
        self.description = QLabel()
        self.description.setWordWrap(True)
        self.create_button = QPushButton("Create…")
        form.addRow("Template", self.template)
        form.addRow("Description", self.description)
        form.addRow(self.create_button)
        layout.addWidget(group)
        self.template.currentIndexChanged.connect(self._update_description)
        self.create_button.clicked.connect(lambda: self.create_requested.emit(self.template.currentData()))
        self._update_description()

    def _update_description(self, *_):
        try:
            self.description.setText(self.registry.get(self.template.currentData()).description)
        except (KeyError, TypeError):
            self.description.setText("")
