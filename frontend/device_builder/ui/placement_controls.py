from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFormLayout, QGridLayout, QGroupBox,
    QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from frontend.device_builder.assembly import MAX_REPEAT_COUNT


class PlacementControls(QWidget):
    """Compact UI controls; geometry decisions remain in assembly helpers."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        placement = QGroupBox("PLACEMENT")
        placement_form = QFormLayout(placement)
        self.reference_region = QComboBox()
        self.gap = self._distance_spin(3.0)
        placement_form.addRow("Reference Region", self.reference_region)
        placement_form.addRow("Gap (Å)", self.gap)
        placement_actions = QGridLayout()
        self.above_button = QPushButton("Above")
        self.below_button = QPushButton("Below")
        self.left_button = QPushButton("Left")
        self.right_button = QPushButton("Right")
        for index, button in enumerate((self.above_button, self.below_button, self.left_button, self.right_button)):
            placement_actions.addWidget(button, index // 2, index % 2)
        placement_form.addRow(placement_actions)
        layout.addWidget(placement)

        alignment = QGroupBox("ALIGN")
        alignment_layout = QGridLayout(alignment)
        self.align_x_button = QPushButton("Align X")
        self.align_y_button = QPushButton("Align Y")
        self.align_z_button = QPushButton("Align Z")
        self.align_xy_button = QPushButton("Align XY")
        self.align_xyz_button = QPushButton("Align XYZ")
        self.align_top_button = QPushButton("Top")
        self.align_bottom_button = QPushButton("Bottom")
        self.align_left_button = QPushButton("Left Surface")
        self.align_right_button = QPushButton("Right Surface")
        buttons = (
            self.align_x_button, self.align_y_button, self.align_z_button,
            self.align_xy_button, self.align_xyz_button, self.align_top_button,
            self.align_bottom_button, self.align_left_button, self.align_right_button,
        )
        for index, button in enumerate(buttons):
            alignment_layout.addWidget(button, index // 3, index % 3)
        layout.addWidget(alignment)

        repeat = QGroupBox("REPEAT")
        repeat_form = QFormLayout(repeat)
        self.repeat_counts = [self._repeat_spin() for _ in range(3)]
        for label, editor in zip(("Nx", "Ny", "Nz"), self.repeat_counts):
            repeat_form.addRow(label, editor)
        self.repeat_button = QPushButton("Repeat Region")
        repeat_form.addRow(self.repeat_button)
        layout.addWidget(repeat)

        device_cell = QGroupBox("DEVICE CELL")
        cell_form = QFormLayout(device_cell)
        self.padding = [self._distance_spin(5.0) for _ in range(3)]
        for label, editor in zip(("Padding X (Å)", "Padding Y (Å)", "Z Padding / Vacuum (Å)"), self.padding):
            cell_form.addRow(label, editor)
        self.fit_cell_button = QPushButton("Fit Cell to Device")
        cell_form.addRow(self.fit_cell_button)
        layout.addWidget(device_cell)

        validation = QGroupBox("VALIDATION")
        validation_layout = QHBoxLayout(validation)
        self.check_overlaps_button = QPushButton("Check Overlaps")
        validation_layout.addWidget(self.check_overlaps_button)
        layout.addWidget(validation)

    @staticmethod
    def _distance_spin(value):
        editor = QDoubleSpinBox()
        editor.setRange(0.0, 1000000.0)
        editor.setDecimals(6)
        editor.setValue(value)
        return editor

    @staticmethod
    def _repeat_spin():
        editor = QSpinBox()
        editor.setRange(1, MAX_REPEAT_COUNT)
        editor.setValue(1)
        return editor

    def set_device(self, device, selected_id=None):
        blocker = QSignalBlocker(self.reference_region)
        previous = self.reference_region.currentData()
        self.reference_region.clear()
        for region in device.regions:
            self.reference_region.addItem(region.name, region.id)
        target = previous if device.get_region(previous) is not None else selected_id
        if target is not None:
            index = self.reference_region.findData(target)
            if index >= 0:
                self.reference_region.setCurrentIndex(index)
        for editor, value in zip(self.padding, getattr(device, "padding", (5.0, 5.0, 5.0))):
            editor.setValue(float(value))

    def reference_region_id(self):
        return self.reference_region.currentData()

    def repeat_values(self):
        return tuple(editor.value() for editor in self.repeat_counts)

    def padding_values(self):
        return tuple(editor.value() for editor in self.padding)
