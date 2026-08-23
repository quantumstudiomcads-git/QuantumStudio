from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox,
    QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from frontend.device_builder.model import InterfaceMode


class InterfaceControls(QWidget):
    """Compact interface inputs; matching remains in the Device Builder service."""

    match_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        group = QGroupBox("INTERFACE")
        form = QFormLayout(group)
        self.region_a = QComboBox()
        self.region_b = QComboBox()
        self.mode = QComboBox()
        self.mode.addItem("Aligned", InterfaceMode.ALIGNED)
        self.mode.addItem("Twisted / Moiré", InterfaceMode.TWISTED)
        self.twist = QDoubleSpinBox()
        self.twist.setRange(-360.0, 360.0)
        self.twist.setDecimals(8)
        self.max_strain = QDoubleSpinBox()
        self.max_strain.setRange(0.0, 1.0)
        self.max_strain.setDecimals(8)
        self.max_strain.setValue(0.05)
        self.strain_mode = QComboBox()
        self.strain_mode.addItem("Balanced", "balanced")
        self.strain_mode.addItem("Deform Region A", "bottom")
        self.strain_mode.addItem("Deform Region B", "top")
        self.max_index = QSpinBox()
        self.max_index.setRange(1, 8)
        self.max_index.setValue(3)
        self.gap = QDoubleSpinBox()
        self.gap.setRange(0.0, 1000000.0)
        self.gap.setDecimals(6)
        self.gap.setValue(3.0)
        self.fit_cell = QCheckBox("Fit Device Cell after match")
        self.match_button = QPushButton("Find / Match Interface")
        self.diagnostics = QLabel("No interface match computed.")
        self.diagnostics.setWordWrap(True)
        form.addRow("Region A", self.region_a)
        form.addRow("Region B", self.region_b)
        form.addRow("Mode", self.mode)
        form.addRow("Twist (deg)", self.twist)
        form.addRow("Max Strain", self.max_strain)
        form.addRow("Strain", self.strain_mode)
        form.addRow("Max Index", self.max_index)
        form.addRow("Gap (Å)", self.gap)
        form.addRow("", self.fit_cell)
        form.addRow(self.match_button)
        form.addRow("Diagnostics", self.diagnostics)
        layout.addWidget(group)
        self.mode.currentIndexChanged.connect(self._update_mode)
        self.match_button.clicked.connect(self.match_requested)
        self._update_mode()

    def _update_mode(self, *_):
        self.twist.setEnabled(self.mode.currentData() is InterfaceMode.TWISTED)

    def set_device(self, device):
        current_a = self.region_a.currentData()
        current_b = self.region_b.currentData()
        blockers = (QSignalBlocker(self.region_a), QSignalBlocker(self.region_b))
        self.region_a.clear()
        self.region_b.clear()
        for region in device.regions:
            self.region_a.addItem(region.name, region.id)
            self.region_b.addItem(region.name, region.id)
        for combo, current in ((self.region_a, current_a), (self.region_b, current_b)):
            index = combo.findData(current)
            if index >= 0:
                combo.setCurrentIndex(index)
        if self.region_b.count() > 1 and self.region_a.currentIndex() == self.region_b.currentIndex():
            self.region_b.setCurrentIndex(1)

    def parameters(self):
        mode = self.mode.currentData()
        return {
            "region_a_id": self.region_a.currentData(),
            "region_b_id": self.region_b.currentData(),
            "mode": mode,
            "requested_twist_deg": self.twist.value() if mode is InterfaceMode.TWISTED else 0.0,
            "max_strain": self.max_strain.value(),
            "strain_mode": self.strain_mode.currentData(),
            "gap": self.gap.value(),
            "max_index": self.max_index.value(),
            "fit_cell_after_match": self.fit_cell.isChecked(),
        }

    def set_busy(self, busy):
        self.match_button.setEnabled(not busy)
        self.match_button.setText("Matching…" if busy else "Find / Match Interface")

    def show_diagnostics(self, diagnostics):
        if not diagnostics:
            self.diagnostics.setText("No interface diagnostics available.")
            return
        self.diagnostics.setText(
            "det A/B: {}/{}; atoms: {}; max strain: {:.6g}; residual rotation: {:.6g}°; residual: {:.3g}; gap: {:.4g} Å".format(
                diagnostics.get("determinant_a", "?"), diagnostics.get("determinant_b", "?"),
                diagnostics.get("final_atom_count", "?"), float(diagnostics.get("max_principal_strain", 0.0)),
                float(diagnostics.get("residual_rotation_deg", 0.0)), float(diagnostics.get("cartesian_residual", 0.0)),
                float(diagnostics.get("gap", 0.0)),
            )
        )
