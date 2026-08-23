import math

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QHBoxLayout,
)


class BuilderMeasureMixin:

    # ==========================================================
    # MEASURE TAB
    # ==========================================================

    def _build_measure_tab(self):

        page = QWidget()

        layout = QVBoxLayout(page)

        layout.setContentsMargins(
            2,
            8,
            2,
            8,
        )

        layout.setSpacing(10)

        # ------------------------------------------------------
        # Measurement type
        # ------------------------------------------------------

        title = QLabel(
            "MEASUREMENT"
        )

        title.setObjectName(
            "sectionTitle"
        )

        layout.addWidget(
            title
        )

        self.measure_type = QComboBox()

        self.measure_type.addItems(
            [
                "Bond Length",
                "Bond Angle",
                "Dihedral Angle",
                "Point Distance",
            ]
        )

        self.measure_type.currentIndexChanged.connect(
            self._update_measurement_form
        )

        layout.addWidget(
            self.measure_type
        )

        # ------------------------------------------------------
        # Atom measurement group
        # ------------------------------------------------------

        self.atom_measure_group = QGroupBox(
            "Atom Selection"
        )

        atom_layout = QVBoxLayout(
            self.atom_measure_group
        )

        # ------------------------------------------------------
        # Selection source
        # ------------------------------------------------------

        source_row = QHBoxLayout()

        source_label = QLabel(
            "Selection:"
        )

        self.atom_selection_mode = QComboBox()

        self.atom_selection_mode.addItems(
            [
                "Atom list",
                "Atom number",
            ]
        )

        self.atom_selection_mode.currentIndexChanged.connect(
            self._update_measurement_form
        )

        source_row.addWidget(
            source_label
        )

        source_row.addWidget(
            self.atom_selection_mode,
            1,
        )

        atom_layout.addLayout(
            source_row
        )

        # ------------------------------------------------------
        # Atom A
        # ------------------------------------------------------

        self.measure_atom_a_combo = (
            QComboBox()
        )

        self.measure_atom_a_number = (
            QSpinBox()
        )

        self.measure_atom_a_number.setMinimum(
            1
        )

        self.measure_atom_a_number.valueChanged.connect(
            self._measurement_number_changed
        )

        atom_layout.addWidget(
            QLabel("Atom A")
        )

        atom_row_a = QHBoxLayout()

        atom_row_a.addWidget(
            self.measure_atom_a_combo,
            1,
        )

        atom_row_a.addWidget(
            self.measure_atom_a_number
        )

        atom_layout.addLayout(
            atom_row_a
        )

        # ------------------------------------------------------
        # Atom B
        # ------------------------------------------------------

        self.measure_atom_b_combo = (
            QComboBox()
        )

        self.measure_atom_b_number = (
            QSpinBox()
        )

        self.measure_atom_b_number.setMinimum(
            1
        )

        self.measure_atom_b_number.valueChanged.connect(
            self._measurement_number_changed
        )

        atom_layout.addWidget(
            QLabel("Atom B")
        )

        atom_row_b = QHBoxLayout()

        atom_row_b.addWidget(
            self.measure_atom_b_combo,
            1,
        )

        atom_row_b.addWidget(
            self.measure_atom_b_number
        )

        atom_layout.addLayout(
            atom_row_b
        )

        # ------------------------------------------------------
        # Atom C
        # ------------------------------------------------------

        self.measure_atom_c_combo = (
            QComboBox()
        )

        self.measure_atom_c_number = (
            QSpinBox()
        )

        self.measure_atom_c_number.setMinimum(
            1
        )

        self.measure_atom_c_number.valueChanged.connect(
            self._measurement_number_changed
        )

        atom_layout.addWidget(
            QLabel("Atom C")
        )

        atom_row_c = QHBoxLayout()

        atom_row_c.addWidget(
            self.measure_atom_c_combo,
            1,
        )

        atom_row_c.addWidget(
            self.measure_atom_c_number
        )

        atom_layout.addLayout(
            atom_row_c
        )

        # ------------------------------------------------------
        # Atom D
        # ------------------------------------------------------

        self.measure_atom_d_combo = (
            QComboBox()
        )

        self.measure_atom_d_number = (
            QSpinBox()
        )

        self.measure_atom_d_number.setMinimum(
            1
        )

        self.measure_atom_d_number.valueChanged.connect(
            self._measurement_number_changed
        )

        atom_layout.addWidget(
            QLabel("Atom D")
        )

        atom_row_d = QHBoxLayout()

        atom_row_d.addWidget(
            self.measure_atom_d_combo,
            1,
        )

        atom_row_d.addWidget(
            self.measure_atom_d_number
        )

        atom_layout.addLayout(
            atom_row_d
        )

        layout.addWidget(
            self.atom_measure_group
        )

        # ------------------------------------------------------
        # Point measurement group
        # ------------------------------------------------------

        self.point_measure_group = QGroupBox(
            "Point Coordinates"
        )

        point_layout = QVBoxLayout(
            self.point_measure_group
        )

        point_form = QFormLayout()

        self.point_ax = QDoubleSpinBox()
        self.point_ay = QDoubleSpinBox()
        self.point_az = QDoubleSpinBox()

        self.point_bx = QDoubleSpinBox()
        self.point_by = QDoubleSpinBox()
        self.point_bz = QDoubleSpinBox()

        point_boxes = [
            self.point_ax,
            self.point_ay,
            self.point_az,
            self.point_bx,
            self.point_by,
            self.point_bz,
        ]

        for box in point_boxes:

            box.setRange(
                -10000,
                10000,
            )

            box.setDecimals(
                6
            )

            box.setSingleStep(
                0.1
            )

        point_form.addRow(
            "P1 X:",
            self.point_ax,
        )

        point_form.addRow(
            "P1 Y:",
            self.point_ay,
        )

        point_form.addRow(
            "P1 Z:",
            self.point_az,
        )

        point_form.addRow(
            "P2 X:",
            self.point_bx,
        )

        point_form.addRow(
            "P2 Y:",
            self.point_by,
        )

        point_form.addRow(
            "P2 Z:",
            self.point_bz,
        )

        point_layout.addLayout(
            point_form
        )

        self.point_from_atoms = QPushButton(
            "Use Atom Coordinates"
        )

        self.point_from_atoms.clicked.connect(
            self._use_atoms_as_points
        )

        point_layout.addWidget(
            self.point_from_atoms
        )

        layout.addWidget(
            self.point_measure_group
        )

        # ------------------------------------------------------
        # Measure button
        # ------------------------------------------------------

        self.measure_button = QPushButton(
            "Measure"
        )

        self.measure_button.setObjectName(
            "operationButton"
        )

        self.measure_button.clicked.connect(
            self._perform_measurement
        )

        layout.addWidget(
            self.measure_button
        )

        self.minimum_image = QCheckBox("Periodic minimum-image distance")
        self.minimum_image.setChecked(False)
        layout.addWidget(self.minimum_image)

        # ------------------------------------------------------
        # Clear button
        # ------------------------------------------------------

        self.clear_measurement_button = QPushButton(
            "Clear Measurement"
        )

        self.clear_measurement_button.clicked.connect(
            self._clear_measurement
        )

        layout.addWidget(
            self.clear_measurement_button
        )

        # ------------------------------------------------------
        # Result
        # ------------------------------------------------------

        result_title = QLabel(
            "RESULT"
        )

        result_title.setObjectName(
            "sectionTitle"
        )

        layout.addWidget(
            result_title
        )

        self.measurement_result = QLabel(
            "No measurement"
        )

        self.measurement_result.setObjectName(
            "measurementResult"
        )

        self.measurement_result.setWordWrap(
            True
        )

        layout.addWidget(
            self.measurement_result
        )

        layout.addStretch()

        self._update_measurement_form()

        return page

    # ==========================================================
    # ATOM LIST
    # ==========================================================

    def _refresh_measurement_atoms(self):

        if not hasattr(
            self,
            "measure_atom_a_combo",
        ):
            return

        combos = [
            self.measure_atom_a_combo,
            self.measure_atom_b_combo,
            self.measure_atom_c_combo,
            self.measure_atom_d_combo,
        ]

        numbers = [
            self.measure_atom_a_number,
            self.measure_atom_b_number,
            self.measure_atom_c_number,
            self.measure_atom_d_number,
        ]

        # Remember previous values.
        old_indices = [
            combo.currentIndex()
            for combo in combos
        ]

        for combo in combos:

            combo.blockSignals(
                True
            )

            combo.clear()

        for index, atom in enumerate(
            self.structure.atoms
        ):

            label = (
                f"{index + 1:03d}  —  "
                f"{atom.element}"
            )

            for combo in combos:

                combo.addItem(
                    label,
                    index,
                )

        count = len(
            self.structure.atoms
        )

        for number in numbers:

            number.blockSignals(
                True
            )

            number.setMaximum(
                max(1, count)
            )

        # Restore / establish sensible defaults.
        defaults = [
            0,
            1,
            2,
            3,
        ]

        for i, combo in enumerate(
            combos
        ):

            if count == 0:

                combo.setCurrentIndex(
                    -1
                )

            else:

                previous = old_indices[i]

                if (
                    0 <= previous < count
                ):

                    combo.setCurrentIndex(
                        previous
                    )

                else:

                    combo.setCurrentIndex(
                        min(
                            defaults[i],
                            count - 1,
                        )
                    )

            combo.blockSignals(
                False
            )

        for i, number in enumerate(
            numbers
        ):

            if count:

                number.setValue(
                    min(
                        defaults[i] + 1,
                        count,
                    )
                )

            else:

                number.setValue(
                    1
                )

            number.blockSignals(
                False
            )

        self._update_measurement_form()

    # ==========================================================
    # FORM VISIBILITY
    # ==========================================================

    def _update_measurement_form(
        self,
        *_,
    ):

        if not hasattr(
            self,
            "measure_type",
        ):
            return

        measurement = (
            self.measure_type.currentText()
        )

        point_mode = (
            measurement
            == "Point Distance"
        )

        self.atom_measure_group.setVisible(
            not point_mode
        )

        self.point_measure_group.setVisible(
            point_mode
        )

        if point_mode:

            return

        atom_mode = (
            self.atom_selection_mode.currentText()
        )

        use_numbers = (
            atom_mode
            == "Atom number"
        )

        combos = [
            self.measure_atom_a_combo,
            self.measure_atom_b_combo,
            self.measure_atom_c_combo,
            self.measure_atom_d_combo,
        ]

        numbers = [
            self.measure_atom_a_number,
            self.measure_atom_b_number,
            self.measure_atom_c_number,
            self.measure_atom_d_number,
        ]

        for combo, number in zip(
            combos,
            numbers,
        ):

            combo.setVisible(
                not use_numbers
            )

            number.setVisible(
                use_numbers
            )

        show_c = measurement in [
            "Bond Angle",
            "Dihedral Angle",
        ]

        show_d = measurement == (
            "Dihedral Angle"
        )

        self._set_atom_row_visibility(
            self.measure_atom_c_combo,
            self.measure_atom_c_number,
            show_c,
        )

        self._set_atom_row_visibility(
            self.measure_atom_d_combo,
            self.measure_atom_d_number,
            show_d,
        )

    # ==========================================================
    # ROW VISIBILITY
    # ==========================================================

    def _set_atom_row_visibility(
        self,
        combo,
        number,
        visible,
    ):

        combo.setVisible(
            visible
            and
            self.atom_selection_mode.currentText()
            == "Atom list"
        )

        number.setVisible(
            visible
            and
            self.atom_selection_mode.currentText()
            == "Atom number"
        )

        label = combo.parentWidget()

        if label is not None:

            # The QLabel immediately preceding each control
            # is left visible because hiding individual labels
            # is less reliable with nested layouts.
            pass

    # ==========================================================
    # GET ATOM INDEX
    # ==========================================================

    def _atom_index(
        self,
        combo,
        number,
    ):

        if (
            self.atom_selection_mode.currentText()
            == "Atom number"
        ):

            index = (
                number.value()
                - 1
            )

        else:

            index = (
                combo.currentData()
            )

        if index is None:

            raise ValueError(
                "Please select an atom."
            )

        index = int(
            index
        )

        if not (
            0
            <= index
            < len(
                self.structure.atoms
            )
        ):

            raise ValueError(
                "Atom number is outside the structure."
            )

        return index

    # ==========================================================
    # GET SELECTED ATOMS
    # ==========================================================

    def _measurement_atom_indices(
        self
    ):

        return [
            self._atom_index(
                self.measure_atom_a_combo,
                self.measure_atom_a_number,
            ),
            self._atom_index(
                self.measure_atom_b_combo,
                self.measure_atom_b_number,
            ),
            self._atom_index(
                self.measure_atom_c_combo,
                self.measure_atom_c_number,
            ),
            self._atom_index(
                self.measure_atom_d_combo,
                self.measure_atom_d_number,
            ),
        ]

    # ==========================================================
    # VECTOR HELPERS
    # ==========================================================

    @staticmethod
    def _vector(
        atom,
    ):

        return (
            float(atom.x),
            float(atom.y),
            float(atom.z),
        )

    @staticmethod
    def _sub(
        a,
        b,
    ):

        return (
            a[0] - b[0],
            a[1] - b[1],
            a[2] - b[2],
        )

    @staticmethod
    def _dot(
        a,
        b,
    ):

        return (
            a[0] * b[0]
            +
            a[1] * b[1]
            +
            a[2] * b[2]
        )

    @staticmethod
    def _cross(
        a,
        b,
    ):

        return (
            a[1] * b[2]
            - a[2] * b[1],

            a[2] * b[0]
            - a[0] * b[2],

            a[0] * b[1]
            - a[1] * b[0],
        )

    @staticmethod
    def _norm(
        v,
    ):

        return math.sqrt(
            BuilderMeasureMixin._dot(
                v,
                v,
            )
        )

    # ==========================================================
    # DISTANCE
    # ==========================================================

    @staticmethod
    def _distance(
        a,
        b,
    ):

        d = BuilderMeasureMixin._sub(
            a,
            b,
        )

        return BuilderMeasureMixin._norm(
            d
        )

    # ==========================================================
    # ANGLE
    # ==========================================================

    @staticmethod
    def _angle(
        a,
        b,
        c,
    ):

        ba = BuilderMeasureMixin._sub(
            a,
            b,
        )

        bc = BuilderMeasureMixin._sub(
            c,
            b,
        )

        norm_ba = BuilderMeasureMixin._norm(
            ba
        )

        norm_bc = BuilderMeasureMixin._norm(
            bc
        )

        if (
            norm_ba < 1e-12
            or
            norm_bc < 1e-12
        ):

            raise ValueError(
                "Cannot calculate an angle using coincident atoms."
            )

        cosine = (
            BuilderMeasureMixin._dot(
                ba,
                bc,
            )
            /
            (
                norm_ba
                *
                norm_bc
            )
        )

        cosine = max(
            -1.0,
            min(
                1.0,
                cosine,
            )
        )

        return math.degrees(
            math.acos(
                cosine
            )
        )

    # ==========================================================
    # DIHEDRAL
    # ==========================================================

    @staticmethod
    def _dihedral(
        a,
        b,
        c,
        d,
    ):

        b1 = BuilderMeasureMixin._sub(
            b,
            a,
        )

        b2 = BuilderMeasureMixin._sub(
            c,
            b,
        )

        b3 = BuilderMeasureMixin._sub(
            d,
            c,
        )

        n1 = BuilderMeasureMixin._cross(
            b1,
            b2,
        )

        n2 = BuilderMeasureMixin._cross(
            b2,
            b3,
        )

        b2_norm = BuilderMeasureMixin._norm(
            b2
        )

        if (
            BuilderMeasureMixin._norm(n1)
            < 1e-12
            or
            BuilderMeasureMixin._norm(n2)
            < 1e-12
            or
            b2_norm
            < 1e-12
        ):

            raise ValueError(
                "Cannot calculate a dihedral angle for collinear atoms."
            )

        n1_norm = BuilderMeasureMixin._norm(
            n1
        )

        n2_norm = BuilderMeasureMixin._norm(
            n2
        )

        n1 = tuple(
            x / n1_norm
            for x in n1
        )

        n2 = tuple(
            x / n2_norm
            for x in n2
        )

        b2_unit = tuple(
            x / b2_norm
            for x in b2
        )

        m1 = BuilderMeasureMixin._cross(
            n1,
            b2_unit,
        )

        x = BuilderMeasureMixin._dot(
            n1,
            n2,
        )

        y = BuilderMeasureMixin._dot(
            m1,
            n2,
        )

        return math.degrees(
            math.atan2(
                y,
                x,
            )
        )

    # ==========================================================
    # PERFORM MEASUREMENT
    # ==========================================================

    def _perform_measurement(
        self,
    ):

        try:

            measurement = (
                self.measure_type.currentText()
            )

            if measurement == (
                "Point Distance"
            ):

                p1 = (
                    self.point_ax.value(),
                    self.point_ay.value(),
                    self.point_az.value(),
                )

                p2 = (
                    self.point_bx.value(),
                    self.point_by.value(),
                    self.point_bz.value(),
                )

                value = self._distance(
                    p1,
                    p2,
                )

                self.measurement_result.setText(
                    "<b>Point distance</b><br><br>"
                    f"P1 → P2<br>"
                    f"<b>{value:.6f} Å</b>"
                )

                self.viewport.set_measurement_overlay(
                    {
                        "type": "point_distance",
                        "p1": p1,
                        "p2": p2,
                        "value": value,
                    }
                )

                return

            indices = (
                self._measurement_atom_indices()
            )

            atoms = self.structure.atoms

            if measurement == (
                "Bond Length"
            ):

                i, j = indices[:2]

                p1 = self._vector(
                    atoms[i]
                )

                p2 = self._vector(
                    atoms[j]
                )

                if getattr(self, "minimum_image", None) is not None and self.minimum_image.isChecked():
                    from frontend.builder.view.math import minimum_image_distance
                    value = minimum_image_distance(p1, p2, self.structure.cell, self.structure.periodic)
                else:
                    value = self._distance(p1, p2)

                self.measurement_result.setText(
                    "<b>Bond length</b><br><br>"
                    f"Atom {i + 1} — Atom {j + 1}<br>"
                    f"{atoms[i].element}{i + 1}"
                    f" — "
                    f"{atoms[j].element}{j + 1}<br><br>"
                    f"<b>{value:.6f} Å</b>"
                )

                self.viewport.set_measurement_overlay(
                    {
                        "type": "distance",
                        "atoms": [i, j],
                        "value": value,
                    }
                )

            elif measurement == (
                "Bond Angle"
            ):

                i, j, k = indices[:3]

                p1 = self._vector(
                    atoms[i]
                )

                p2 = self._vector(
                    atoms[j]
                )

                p3 = self._vector(
                    atoms[k]
                )

                value = self._angle(
                    p1,
                    p2,
                    p3,
                )

                self.measurement_result.setText(
                    "<b>Bond angle</b><br><br>"
                    f"{atoms[i].element}{i + 1}"
                    f" — "
                    f"{atoms[j].element}{j + 1}"
                    f" — "
                    f"{atoms[k].element}{k + 1}"
                    f"<br><br>"
                    f"<b>{value:.6f}°</b>"
                )

                self.viewport.set_measurement_overlay(
                    {
                        "type": "angle",
                        "atoms": [i, j, k],
                        "value": value,
                    }
                )

            elif measurement == (
                "Dihedral Angle"
            ):

                i, j, k, l = indices

                p1 = self._vector(
                    atoms[i]
                )

                p2 = self._vector(
                    atoms[j]
                )

                p3 = self._vector(
                    atoms[k]
                )

                p4 = self._vector(
                    atoms[l]
                )

                value = self._dihedral(
                    p1,
                    p2,
                    p3,
                    p4,
                )

                self.measurement_result.setText(
                    "<b>Dihedral angle</b><br><br>"
                    f"{atoms[i].element}{i + 1}"
                    f" — "
                    f"{atoms[j].element}{j + 1}"
                    f" — "
                    f"{atoms[k].element}{k + 1}"
                    f" — "
                    f"{atoms[l].element}{l + 1}"
                    f"<br><br>"
                    f"<b>{value:.6f}°</b>"
                )

                self.viewport.set_measurement_overlay(
                    {
                        "type": "dihedral",
                        "atoms": [i, j, k, l],
                        "value": value,
                    }
                )

        except Exception as error:

            self.measurement_result.setText(
                f"<b>Measurement error</b><br><br>"
                f"{error}"
            )

    # ==========================================================
    # USE ATOMS AS POINTS
    # ==========================================================

    def _use_atoms_as_points(self):

        try:

            i, j = (
                self._measurement_atom_indices()[:2]
            )

            a = self.structure.atoms[i]
            b = self.structure.atoms[j]

            self.point_ax.setValue(
                float(a.x)
            )

            self.point_ay.setValue(
                float(a.y)
            )

            self.point_az.setValue(
                float(a.z)
            )

            self.point_bx.setValue(
                float(b.x)
            )

            self.point_by.setValue(
                float(b.y)
            )

            self.point_bz.setValue(
                float(b.z)
            )

        except Exception as error:

            self.measurement_result.setText(
                str(error)
            )

    # ==========================================================
    # NUMBER / COMBO SYNCHRONIZATION
    # ==========================================================

    def _measurement_number_changed(
        self,
        *_,
    ):

        if not hasattr(
            self,
            "atom_selection_mode",
        ):

            return

        if (
            self.atom_selection_mode.currentText()
            != "Atom number"
        ):

            return

        numbers = [
            self.measure_atom_a_number,
            self.measure_atom_b_number,
            self.measure_atom_c_number,
            self.measure_atom_d_number,
        ]

        combos = [
            self.measure_atom_a_combo,
            self.measure_atom_b_combo,
            self.measure_atom_c_combo,
            self.measure_atom_d_combo,
        ]

        for number, combo in zip(
            numbers,
            combos,
        ):

            index = (
                number.value()
                - 1
            )

            combo.blockSignals(
                True
            )

            if (
                0
                <= index
                < combo.count()
            ):

                combo.setCurrentIndex(
                    index
                )

            combo.blockSignals(
                False
            )

    # ==========================================================
    # CLEAR
    # ==========================================================

    def _clear_measurement(self):

        self.measurement_result.setText(
            "No measurement"
        )

        self.viewport.clear_measurement_overlay()
