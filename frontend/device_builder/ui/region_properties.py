from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QLineEdit, QVBoxLayout, QWidget
from frontend.device_builder.model.roles import RegionRole, role_label

class RegionProperties(QWidget):
    region_changed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        group = QGroupBox("REGION PROPERTIES")
        form = QFormLayout(group)
        self.name = QLineEdit()
        self.role = QComboBox()
        for role in RegionRole:
            self.role.addItem(role_label(role), role)
        self.visible = QCheckBox("Visible")
        self.translation = [self._spin() for _ in range(3)]
        self.rotation = [self._spin() for _ in range(3)]
        form.addRow("Name", self.name)
        form.addRow("Role", self.role)
        form.addRow("", self.visible)
        for label, editor in zip(("Translation X (Angstrom)", "Translation Y (Angstrom)", "Translation Z (Angstrom)"), self.translation):
            form.addRow(label, editor)
        for label, editor in zip(("Rotation X (deg)", "Rotation Y (deg)", "Rotation Z (deg)"), self.rotation):
            form.addRow(label, editor)
        layout.addWidget(group)
        layout.addStretch()
        self._region_id = None
        self.name.editingFinished.connect(self._emit_changed)
        self.role.currentIndexChanged.connect(self._emit_changed)
        self.visible.toggled.connect(self._emit_changed)
        for editor in (*self.translation, *self.rotation):
            editor.editingFinished.connect(self._emit_changed)
        self.set_region(None)

    @staticmethod
    def _spin():
        spin = QDoubleSpinBox()
        spin.setRange(-1000000.0, 1000000.0)
        spin.setDecimals(6)
        return spin

    def set_region(self, region):
        widgets = [self.name, self.role, self.visible, *self.translation, *self.rotation]
        blockers = [QSignalBlocker(widget) for widget in widgets]
        self._region_id = None if region is None else region.id
        for widget in widgets:
            widget.setEnabled(region is not None)
        if region is None:
            self.name.setText("")
            self.visible.setChecked(False)
            for editor in (*self.translation, *self.rotation):
                editor.setValue(0.0)
            return
        self.name.setText(region.name)
        self.role.setCurrentIndex(self.role.findData(region.role))
        self.visible.setChecked(region.visible)
        for editor, value in zip(self.translation, region.translation):
            editor.setValue(value)
        for editor, value in zip(self.rotation, region.rotation):
            editor.setValue(value)

    def _emit_changed(self, *_):
        if self._region_id is None:
            return
        self.region_changed.emit({
            "id": self._region_id,
            "name": self.name.text().strip() or "Region",
            "role": self.role.currentData(),
            "visible": self.visible.isChecked(),
            "translation": tuple(editor.value() for editor in self.translation),
            "rotation": tuple(editor.value() for editor in self.rotation),
        })
