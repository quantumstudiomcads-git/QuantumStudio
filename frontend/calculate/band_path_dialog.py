"""Structured band-path selector backed by the public BZ path API."""
from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFormLayout,
                               QHBoxLayout, QLabel, QPushButton, QSpinBox,
                               QTableWidget, QTableWidgetItem, QVBoxLayout)
from frontend.builder.brillouin_zone.path_api import materialize_path, recommended_band_path


class BandPathDialog(QDialog):
    def __init__(self, structure_snapshot, current_path=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Band Path")
        self._recommendation = recommended_band_path(structure_snapshot)
        self._value = list(current_path or [])
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Band Path"))
        self.zone = QLabel(f"Brillouin zone: {self._recommendation.bravais_label}")
        layout.addWidget(self.zone)
        if self._recommendation.message:
            message = QLabel(self._recommendation.message)
            message.setWordWrap(True)
            layout.addWidget(message)
        self._checks = []
        for segment in self._recommendation.segments:
            check = QCheckBox(segment.label, self)
            check.setChecked(True)
            check.toggled.connect(self._refresh_preview)
            self._checks.append(check)
            layout.addWidget(check)
        options = QFormLayout()
        self.points = QSpinBox(self)
        self.points.setRange(1, 10000)
        self.points.setValue(int((self._value or [{"points": 40}])[0].get("points", 40)))
        self.points.valueChanged.connect(self._refresh_preview)
        options.addRow("Points per segment", self.points)
        layout.addLayout(options)
        self.preview = QLabel(self)
        self.preview.setWordWrap(True)
        layout.addWidget(self.preview)
        reset = QPushButton("Reset to Recommended", self)
        reset.clicked.connect(self._reset)
        layout.addWidget(reset)
        layout.addWidget(QLabel("Custom Path (expert)"))
        self.table = QTableWidget(0, 5, self)
        self.table.setHorizontalHeaderLabels(("Label", "kx", "ky", "kz", "Points"))
        layout.addWidget(self.table, 1)
        actions = QHBoxLayout()
        add = QPushButton("Add Point", self); add.clicked.connect(self._add_row)
        remove = QPushButton("Remove Point", self); remove.clicked.connect(self._remove_row)
        actions.addWidget(add); actions.addWidget(remove); actions.addStretch()
        layout.addLayout(actions)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self._accept); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._load_custom(self._value)
        self._refresh_preview()
        self.resize(620, 620)

    def _reset(self):
        for check in self._checks:
            check.setChecked(True)
        self._refresh_preview()

    def _load_custom(self, path):
        for point in path:
            self._add_row(point)

    def _add_row(self, point=None):
        point = point or {"label": "", "coordinates": [0.0, 0.0, 0.0], "points": self.points.value()}
        row = self.table.rowCount(); self.table.insertRow(row)
        values = (point.get("label", ""), *point.get("coordinates", [0.0, 0.0, 0.0]), point.get("points", self.points.value()))
        for column, value in enumerate(values):
            self.table.setItem(row, column, QTableWidgetItem(str(value)))

    def _remove_row(self):
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)

    def _recommended(self):
        return materialize_path(self._recommendation.segments, tuple(check.isChecked() for check in self._checks), self.points.value())

    def _refresh_preview(self):
        try:
            path = self._recommended()
            self.preview.setText("Selected path: " + (" — ".join(point["label"] for point in path) if path else "none"))
        except ValueError as error:
            self.preview.setText("Path error: " + str(error))

    def _custom(self):
        points = []
        for row in range(self.table.rowCount()):
            try:
                label = self.table.item(row, 0).text().strip()
                coordinates = [float(self.table.item(row, column).text()) for column in (1, 2, 3)]
                count = int(self.table.item(row, 4).text())
            except (AttributeError, ValueError):
                raise ValueError("Custom band-path points require a label, three numeric coordinates, and a positive point count.")
            if not label or count < 1:
                raise ValueError("Custom band-path labels and point counts must be valid.")
            points.append({"label": label, "coordinates": coordinates, "points": count})
        return points

    def _accept(self):
        try:
            custom = self._custom()
            self._value = custom if len(custom) >= 2 else self._recommended()
            if len(self._value) < 2:
                raise ValueError("Band path requires at least two connected points.")
        except ValueError as error:
            self.preview.setText("Path error: " + str(error)); return
        self.accept()

    def value(self):
        return list(self._value)
