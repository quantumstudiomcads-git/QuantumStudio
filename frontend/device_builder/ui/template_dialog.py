"""Template-specific Qt input dialog; template domain code remains Qt-free."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QHBoxLayout, QLabel, QSpinBox, QVBoxLayout, QWidget,
)


class TemplateDialog(QDialog):
    """Collect compact template parameters from pre-existing canonical Structures."""

    def __init__(self, template, source_options, parent=None):
        super().__init__(parent)
        self.template = template
        self.source_options = tuple(source_options)
        self._sources = {}
        self._values = {}
        self.setWindowTitle(template.name)
        layout = QVBoxLayout(self)
        description = QLabel(template.description)
        description.setWordWrap(True)
        layout.addWidget(description)
        self.form = QFormLayout()
        layout.addLayout(self.form)
        self._build_form()
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _source(self, key, label):
        combo = QComboBox()
        for title, structure in self.source_options:
            combo.addItem(title, structure)
        self.form.addRow(label, combo)
        self._sources[key] = combo

    def _distance(self, key, label, value=3.0, *, allow_negative=False):
        editor = QDoubleSpinBox()
        editor.setRange(-1000000.0 if allow_negative else 0.0, 1000000.0)
        editor.setDecimals(6)
        editor.setValue(value)
        self.form.addRow(label, editor)
        self._values[key] = editor

    def _padding(self, default=(5.0, 5.0, 5.0)):
        editors = []
        for label, value in zip(("Padding X (Å)", "Padding Y (Å)", "Padding Z / Vacuum (Å)"), default):
            editor = QDoubleSpinBox()
            editor.setRange(0.0, 1000000.0)
            editor.setDecimals(6)
            editor.setValue(value)
            self.form.addRow(label, editor)
            editors.append(editor)
        self._values["padding"] = editors

    def _build_form(self):
        template_id = self.template.id
        if template_id == "vertical_stack":
            self._source("bottom_structure", "Bottom Structure")
            self._source("top_structure", "Top Structure")
            self._distance("gap", "Gap (Å)")
            matching = QCheckBox("Use commensurate interface matching")
            self.form.addRow("", matching)
            self._values["interface_matching"] = matching
            self._distance("twist_angle_deg", "Twist (deg)", 0.0, allow_negative=True)
            self._distance("max_strain", "Max Strain", 0.05)
            max_index = QSpinBox(); max_index.setRange(1, 8); max_index.setValue(3)
            self.form.addRow("Max Index", max_index); self._values["max_index"] = max_index
            strain = QComboBox()
            strain.addItem("Balanced", "balanced")
            strain.addItem("Deform Bottom", "bottom")
            strain.addItem("Deform Top", "top")
            self.form.addRow("Strain", strain); self._values["strain_mode"] = strain
            self._padding()
        elif template_id in {"lateral_two_probe", "tunnel_junction"}:
            self._source("left_structure", "Left Structure")
            self._source("center_structure" if template_id == "lateral_two_probe" else "barrier_structure", "Center Structure" if template_id == "lateral_two_probe" else "Barrier Structure")
            self._source("right_structure", "Right Structure")
            self._distance("left_gap", "Left Gap (Å)")
            self._distance("right_gap", "Right Gap (Å)")
            self._padding()
        elif template_id == "surface_adsorbate":
            self._source("substrate_structure", "Substrate Structure")
            self._source("adsorbate_structure", "Adsorbate Structure")
            self._distance("separation", "Vertical Separation (Å)")
            self._distance("offset_x", "Lateral Offset X (Å)", 0.0, allow_negative=True)
            self._distance("offset_y", "Lateral Offset Y (Å)", 0.0, allow_negative=True)
            rotations = []
            for label in ("Adsorbate Rotation X (deg)", "Adsorbate Rotation Y (deg)", "Adsorbate Rotation Z (deg)"):
                editor = QDoubleSpinBox(); editor.setRange(-360.0, 360.0); editor.setDecimals(6)
                self.form.addRow(label, editor); rotations.append(editor)
            self._values["rotation"] = rotations
            self._padding((5.0, 5.0, 8.0))
        else:
            self.form.addRow(QLabel("This template has no registered input form."))

    def parameters(self):
        values = {key: combo.currentData() for key, combo in self._sources.items()}
        for key, editor in self._values.items():
            if isinstance(editor, QCheckBox):
                values[key] = editor.isChecked()
            elif isinstance(editor, QComboBox):
                values[key] = editor.currentData()
            elif isinstance(editor, QSpinBox):
                values[key] = editor.value()
            elif isinstance(editor, list):
                values[key] = tuple(item.value() for item in editor)
            else:
                values[key] = editor.value()
        return values
