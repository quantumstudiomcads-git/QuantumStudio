"""
Quantum Studio — Crystal Builder

Periodic crystal construction from:

    Crystal system
    Space group
    Space-group setting
    Lattice parameters
    Unique atomic sites
    Occupancies
    Fractional / Cartesian coordinates

ASE is used for crystallographic symmetry expansion.
"""

from pathlib import Path
import tempfile

import numpy as np

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QHeaderView,
    QWidget,
)

from ase.data import chemical_symbols
from ase.geometry import cellpar_to_cell
from ase.io import write
from ase.spacegroup import Spacegroup, crystal


# ================================================================
# Crystal systems
# ================================================================

CRYSTAL_SYSTEMS = {
    "Triclinic": (1, 2),
    "Monoclinic": (3, 15),
    "Orthorhombic": (16, 74),
    "Tetragonal": (75, 142),
    "Trigonal": (143, 167),
    "Hexagonal": (168, 194),
    "Cubic": (195, 230),
}


SYSTEM_DESCRIPTIONS = {
    "Triclinic":
        "No symmetry constraints on the lattice angles or lengths.",

    "Monoclinic":
        "α = γ = 90°. β is independent.",

    "Orthorhombic":
        "α = β = γ = 90°. a, b and c are independent.",

    "Tetragonal":
        "a = b. α = β = γ = 90°. c is independent.",

    "Trigonal":
        "Rhombohedral/hexagonal setting depends on the space group.",

    "Hexagonal":
        "a = b. α = β = 90°. γ = 120°. c is independent.",

    "Cubic":
        "a = b = c. α = β = γ = 90°.",
}


# ================================================================
# Utility
# ================================================================

def crystal_system(spacegroup_number):

    number = int(spacegroup_number)

    for system, bounds in CRYSTAL_SYSTEMS.items():

        first, last = bounds

        if first <= number <= last:
            return system

    return "Unknown"


# ================================================================
# Crystal Builder Dialog
# ================================================================

class CrystalBuilderDialog(QDialog):

    def __init__(self, parent=None):

        super().__init__(parent)

        self.setWindowTitle(
            "Quantum Studio — Crystal Builder"
        )

        self.resize(
            980,
            820,
        )

        self.generated_atoms = None

        self._build_ui()

        self._populate_elements()

        self._populate_crystal_systems()

        self._add_default_site()

        self._populate_spacegroups()

        self._apply_lattice_constraints()

        self._update_coordinate_headers()

    # ============================================================
    # UI
    # ============================================================

    def _build_ui(self):

        root = QVBoxLayout(self)

        root.setContentsMargins(
            22,
            20,
            22,
            20,
        )

        root.setSpacing(
            12
        )

        # --------------------------------------------------------
        # Header
        # --------------------------------------------------------

        title = QLabel(
            "CRYSTAL BUILDER"
        )

        title.setStyleSheet(
            """
            font-size: 19px;
            font-weight: 700;
            color: #FFFFFF;
            """
        )

        root.addWidget(
            title
        )

        subtitle = QLabel(
            "Construct a periodic crystal from its "
            "space group, lattice and unique atomic sites."
        )

        subtitle.setStyleSheet(
            "color: #777D89;"
        )

        root.addWidget(
            subtitle
        )

        # --------------------------------------------------------
        # Symmetry
        # --------------------------------------------------------

        symmetry_box = QGroupBox(
            "SYMMETRY"
        )

        symmetry_layout = QFormLayout(
            symmetry_box
        )

        self.system_combo = QComboBox()

        self.system_combo.currentIndexChanged.connect(
            self._on_system_changed
        )

        symmetry_layout.addRow(
            "Crystal system:",
            self.system_combo,
        )

        self.spacegroup_combo = QComboBox()

        self.spacegroup_combo.currentIndexChanged.connect(
            self._on_spacegroup_changed
        )

        symmetry_layout.addRow(
            "Space group:",
            self.spacegroup_combo,
        )

        self.setting_combo = QComboBox()

        self.setting_combo.currentIndexChanged.connect(
            self._on_setting_changed
        )

        symmetry_layout.addRow(
            "Setting:",
            self.setting_combo,
        )

        self.system_description = QLabel(
            "—"
        )

        self.system_description.setWordWrap(
            True
        )

        self.system_description.setStyleSheet(
            "color: #89919E;"
        )

        symmetry_layout.addRow(
            "Constraints:",
            self.system_description,
        )

        root.addWidget(
            symmetry_box
        )

        # --------------------------------------------------------
        # Lattice
        # --------------------------------------------------------

        lattice_box = QGroupBox(
            "LATTICE"
        )

        lattice_root = QVBoxLayout(
            lattice_box
        )

        # First row: a b c
        lengths_row = QHBoxLayout()

        self.a = self._length_spinbox(
            5.000
        )

        self.b = self._length_spinbox(
            5.000
        )

        self.c = self._length_spinbox(
            5.000
        )

        lengths_row.addWidget(
            self._lattice_field(
                "a",
                self.a,
            )
        )

        lengths_row.addWidget(
            self._lattice_field(
                "b",
                self.b,
            )
        )

        lengths_row.addWidget(
            self._lattice_field(
                "c",
                self.c,
            )
        )

        lattice_root.addLayout(
            lengths_row
        )

        # Second row: alpha beta gamma
        angles_row = QHBoxLayout()

        self.alpha = self._angle_spinbox(
            90.0
        )

        self.beta = self._angle_spinbox(
            90.0
        )

        self.gamma = self._angle_spinbox(
            90.0
        )

        angles_row.addWidget(
            self._lattice_field(
                "α",
                self.alpha,
            )
        )

        angles_row.addWidget(
            self._lattice_field(
                "β",
                self.beta,
            )
        )

        angles_row.addWidget(
            self._lattice_field(
                "γ",
                self.gamma,
            )
        )

        lattice_root.addLayout(
            angles_row
        )

        # Connect after widgets exist.
        for widget in (
            self.a,
            self.b,
            self.c,
            self.alpha,
            self.beta,
            self.gamma,
        ):

            widget.valueChanged.connect(
                self._lattice_value_changed
            )

        root.addWidget(
            lattice_box
        )

        # --------------------------------------------------------
        # Coordinates
        # --------------------------------------------------------

        coordinate_box = QGroupBox(
            "COORDINATES"
        )

        coordinate_layout = QFormLayout(
            coordinate_box
        )

        self.coordinate_mode = QComboBox()

        self.coordinate_mode.addItems(
            [
                "Fractional",
                "Cartesian",
            ]
        )

        self.coordinate_mode.currentIndexChanged.connect(
            self._update_coordinate_headers
        )

        coordinate_layout.addRow(
            "Position coordinates:",
            self.coordinate_mode,
        )

        self.primitive_check = QCheckBox(
            "Generate primitive cell"
        )

        coordinate_layout.addRow(
            "",
            self.primitive_check
        )

        root.addWidget(
            coordinate_box
        )

        # --------------------------------------------------------
        # Atomic sites
        # --------------------------------------------------------

        sites_box = QGroupBox(
            "UNIQUE ATOMIC SITES"
        )

        sites_layout = QVBoxLayout(
            sites_box
        )

        self.sites = QTableWidget(
            0,
            5,
        )

        self.sites.setHorizontalHeaderLabels(
            [
                "Element",
                "x",
                "y",
                "z",
                "Occupancy",
            ]
        )

        self.sites.setMinimumHeight(
            210
        )

        self.sites.setAlternatingRowColors(
            False
        )

        header = self.sites.horizontalHeader()

        header.setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.Stretch,
        )

        for column in range(
            1,
            5,
        ):

            header.setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.ResizeToContents,
            )

        sites_layout.addWidget(
            self.sites
        )

        site_buttons = QHBoxLayout()

        add_button = QPushButton(
            "+ Add Site"
        )

        remove_button = QPushButton(
            "− Remove Site"
        )

        clear_button = QPushButton(
            "Clear"
        )

        add_button.clicked.connect(
            self._add_site
        )

        remove_button.clicked.connect(
            self._remove_site
        )

        clear_button.clicked.connect(
            self._clear_sites
        )

        site_buttons.addWidget(
            add_button
        )

        site_buttons.addWidget(
            remove_button
        )

        site_buttons.addWidget(
            clear_button
        )

        site_buttons.addStretch()

        sites_layout.addLayout(
            site_buttons
        )

        root.addWidget(
            sites_box,
            1,
        )

        # --------------------------------------------------------
        # Preview
        # --------------------------------------------------------

        preview_row = QHBoxLayout()

        self.preview_label = QLabel(
            "No structure generated"
        )

        self.preview_label.setStyleSheet(
            """
            background: #17191F;
            border: 1px solid #292D35;
            border-radius: 6px;
            padding: 8px;
            color: #AEB4BF;
            """
        )

        preview_row.addWidget(
            self.preview_label,
            1,
        )

        preview_button = QPushButton(
            "Preview"
        )

        preview_button.clicked.connect(
            self._preview
        )

        preview_row.addWidget(
            preview_button
        )

        root.addLayout(
            preview_row
        )

        # --------------------------------------------------------
        # Dialog buttons
        # --------------------------------------------------------

        dialog_buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            |
            QDialogButtonBox.StandardButton.Cancel
        )

        dialog_buttons.accepted.connect(
            self._validate_and_accept
        )

        dialog_buttons.rejected.connect(
            self.reject
        )

        root.addWidget(
            dialog_buttons
        )

        self._apply_style()

    # ============================================================
    # Styling
    # ============================================================

    def _apply_style(self):

        self.setStyleSheet(
            """
            QDialog {
                background: #111318;
                color: #E8EAF0;
            }

            QGroupBox {
                border: 1px solid #292D35;
                border-radius: 7px;
                margin-top: 10px;
                padding-top: 14px;
                color: #858C98;
                font-size: 10px;
                font-weight: 600;
            }

            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }

            QLabel {
                color: #D9DCE3;
            }

            QComboBox,
            QDoubleSpinBox {
                background: #17191F;
                border: 1px solid #30343D;
                border-radius: 5px;
                padding: 6px;
                color: #FFFFFF;
                min-height: 20px;
            }

            QComboBox:hover,
            QDoubleSpinBox:hover {
                border: 1px solid #4A505C;
            }

            QComboBox:disabled,
            QDoubleSpinBox:disabled {
                color: #626873;
                background: #13151A;
            }

            QTableWidget {
                background: #111318;
                border: 1px solid #292D35;
                gridline-color: #292D35;
                color: #E8EAF0;
            }

            QTableWidget::item {
                padding: 4px;
            }

            QHeaderView::section {
                background: #1A1D23;
                border: none;
                padding: 7px;
                color: #AEB4BF;
            }

            QPushButton {
                background: #252932;
                border: none;
                border-radius: 6px;
                padding: 8px 12px;
                color: #D9DCE3;
            }

            QPushButton:hover {
                background: #303540;
            }

            QCheckBox {
                color: #B9BEC8;
            }
            """
        )

    # ============================================================
    # Lattice widgets
    # ============================================================

    @staticmethod
    def _length_spinbox(
        value
    ):

        box = QDoubleSpinBox()

        box.setRange(
            0.01,
            10000.0,
        )

        box.setDecimals(
            5
        )

        box.setSingleStep(
            0.01
        )

        box.setValue(
            value
        )

        box.setSuffix(
            " Å"
        )

        return box

    @staticmethod
    def _angle_spinbox(
        value
    ):

        box = QDoubleSpinBox()

        box.setRange(
            0.01,
            179.99,
        )

        box.setDecimals(
            4
        )

        box.setSingleStep(
            0.5
        )

        box.setValue(
            value
        )

        box.setSuffix(
            "°"
        )

        return box

    @staticmethod
    def _lattice_field(
        label,
        widget,
    ):

        container = QWidget()

        layout = QVBoxLayout(
            container
        )

        layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        title = QLabel(
            label
        )

        title.setStyleSheet(
            """
            color: #858C98;
            font-size: 10px;
            font-weight: 600;
            """
        )

        layout.addWidget(
            title
        )

        layout.addWidget(
            widget
        )

        return container

    # ============================================================
    # Crystal systems
    # ============================================================

    def _populate_crystal_systems(self):

        self.system_combo.blockSignals(
            True
        )

        self.system_combo.clear()

        for system, (
            first,
            last,
        ) in CRYSTAL_SYSTEMS.items():

            count = (
                last
                - first
                + 1
            )

            self.system_combo.addItem(
                (
                    f"{system} "
                    f"({count} space groups)"
                ),
                system,
            )

        self.system_combo.setCurrentIndex(
            0
        )

        self.system_combo.blockSignals(
            False
        )

    def _selected_system(self):

        data = (
            self.system_combo.currentData()
        )

        if data in CRYSTAL_SYSTEMS:

            return data

        return "Triclinic"

    # ============================================================
    # Space groups
    # ============================================================

    def _populate_spacegroups(
        self,
        select_number=None,
    ):

        system = (
            self._selected_system()
        )

        first, last = (
            CRYSTAL_SYSTEMS[
                system
            ]
        )

        self.spacegroup_combo.blockSignals(
            True
        )

        self.spacegroup_combo.clear()

        for number in range(
            first,
            last + 1,
        ):

            try:

                sg = Spacegroup(
                    number
                )

                symbol = sg.symbol

            except Exception:

                symbol = "Unknown"

            self.spacegroup_combo.addItem(
                f"{number:3d}    {symbol}",
                number,
            )

        target_index = 0

        if select_number is not None:

            for index in range(
                self.spacegroup_combo.count()
            ):

                if (
                    self.spacegroup_combo.itemData(
                        index
                    )
                    == select_number
                ):

                    target_index = index
                    break

        self.spacegroup_combo.setCurrentIndex(
            target_index
        )

        self.spacegroup_combo.blockSignals(
            False
        )

        self._update_spacegroup_information()

    # ============================================================
    # Space-group events
    # ============================================================

    def _on_system_changed(
        self,
        *_,
    ):

        if not hasattr(
            self,
            "spacegroup_combo",
        ):

            return

        self._populate_spacegroups()

        self._apply_lattice_constraints()

    def _on_spacegroup_changed(
        self,
        *_,
    ):

        if not hasattr(
            self,
            "spacegroup_combo",
        ):

            return

        self._update_spacegroup_information()

    def _on_setting_changed(
        self,
        *_,
    ):

        if not hasattr(
            self,
            "spacegroup_combo",
        ):

            return

        self._update_spacegroup_information(
            update_settings=False
        )

    # ============================================================
    # Space-group information
    # ============================================================

    def _current_spacegroup_number(self):

        data = (
            self.spacegroup_combo.currentData()
        )

        if data is None:

            first, _ = (
                CRYSTAL_SYSTEMS[
                    self._selected_system()
                ]
            )

            return first

        return int(
            data
        )

    def _update_spacegroup_information(
        self,
        update_settings=True,
    ):

        number = (
            self._current_spacegroup_number()
        )

        system = crystal_system(
            number
        )

        self.system_description.setText(
            SYSTEM_DESCRIPTIONS.get(
                system,
                "—",
            )
        )

        if update_settings:

            self._populate_settings(
                number
            )

        self._apply_lattice_constraints()

    def _populate_settings(
        self,
        number,
    ):

        self.setting_combo.blockSignals(
            True
        )

        self.setting_combo.clear()

        valid_settings = []

        for setting in (
            1,
            2,
        ):

            try:

                Spacegroup(
                    number,
                    setting=setting,
                )

                valid_settings.append(
                    setting
                )

            except Exception:

                pass

        if not valid_settings:

            valid_settings = [
                1
            ]

        for setting in valid_settings:

            self.setting_combo.addItem(
                str(setting),
                setting,
            )

        self.setting_combo.setCurrentIndex(
            0
        )

        self.setting_combo.blockSignals(
            False
        )

    # ============================================================
    # Lattice constraints
    # ============================================================

    def _lattice_value_changed(
        self,
        *_,
    ):

        system = (
            self._selected_system()
        )

        widgets = (
            self.a,
            self.b,
            self.c,
            self.alpha,
            self.beta,
            self.gamma,
        )

        for widget in widgets:

            widget.blockSignals(
                True
            )

        try:

            if system == "Cubic":

                self.b.setValue(
                    self.a.value()
                )

                self.c.setValue(
                    self.a.value()
                )

                self.alpha.setValue(
                    90.0
                )

                self.beta.setValue(
                    90.0
                )

                self.gamma.setValue(
                    90.0
                )

            elif system == "Tetragonal":

                self.b.setValue(
                    self.a.value()
                )

                self.alpha.setValue(
                    90.0
                )

                self.beta.setValue(
                    90.0
                )

                self.gamma.setValue(
                    90.0
                )

            elif system == "Orthorhombic":

                self.alpha.setValue(
                    90.0
                )

                self.beta.setValue(
                    90.0
                )

                self.gamma.setValue(
                    90.0
                )

            elif system == "Hexagonal":

                self.b.setValue(
                    self.a.value()
                )

                self.alpha.setValue(
                    90.0
                )

                self.beta.setValue(
                    90.0
                )

                self.gamma.setValue(
                    120.0
                )

            elif system == "Trigonal":

                # Default to the hexagonal representation.
                # The actual allowed lattice depends on the
                # selected space-group setting.
                self.b.setValue(
                    self.a.value()
                )

                self.gamma.setValue(
                    120.0
                )

                self.alpha.setValue(
                    90.0
                )

                self.beta.setValue(
                    90.0
                )

            elif system == "Monoclinic":

                self.alpha.setValue(
                    90.0
                )

                self.gamma.setValue(
                    90.0
                )

        finally:

            for widget in widgets:

                widget.blockSignals(
                    False
                )

    def _apply_lattice_constraints(self):

        system = (
            self._selected_system()
        )

        widgets = {
            "a": self.a,
            "b": self.b,
            "c": self.c,
            "alpha": self.alpha,
            "beta": self.beta,
            "gamma": self.gamma,
        }

        # Everything starts editable.
        for widget in widgets.values():

            widget.setEnabled(
                True
            )

        if system == "Cubic":

            self.b.setEnabled(
                False
            )

            self.c.setEnabled(
                False
            )

            self.alpha.setEnabled(
                False
            )

            self.beta.setEnabled(
                False
            )

            self.gamma.setEnabled(
                False
            )

        elif system == "Tetragonal":

            self.b.setEnabled(
                False
            )

            self.alpha.setEnabled(
                False
            )

            self.beta.setEnabled(
                False
            )

            self.gamma.setEnabled(
                False
            )

        elif system == "Orthorhombic":

            self.alpha.setEnabled(
                False
            )

            self.beta.setEnabled(
                False
            )

            self.gamma.setEnabled(
                False
            )

        elif system == "Hexagonal":

            self.b.setEnabled(
                False
            )

            self.alpha.setEnabled(
                False
            )

            self.beta.setEnabled(
                False
            )

            self.gamma.setEnabled(
                False
            )

        elif system == "Trigonal":

            self.b.setEnabled(
                False
            )

            self.alpha.setEnabled(
                False
            )

            self.beta.setEnabled(
                False
            )

            self.gamma.setEnabled(
                False
            )

        elif system == "Monoclinic":

            self.alpha.setEnabled(
                False
            )

            self.gamma.setEnabled(
                False
            )

        self._lattice_value_changed()

    # ============================================================
    # Elements
    # ============================================================

    def _populate_elements(self):

        self.elements = [
            symbol
            for symbol in chemical_symbols
            if symbol
        ]

    # ============================================================
    # Atomic sites
    # ============================================================

    def _add_default_site(self):

        self._add_site(
            "C"
        )

    def _add_site(
        self,
        element="C",
    ):

        row = (
            self.sites.rowCount()
        )

        self.sites.insertRow(
            row
        )

        # --------------------------------------------------------
        # Element
        # --------------------------------------------------------

        element_combo = QComboBox()

        element_combo.setEditable(
            True
        )

        element_combo.addItems(
            self.elements
        )

        index = (
            element_combo.findText(
                element
            )
        )

        if index >= 0:

            element_combo.setCurrentIndex(
                index
            )

        self.sites.setCellWidget(
            row,
            0,
            element_combo,
        )

        # --------------------------------------------------------
        # Coordinates
        # --------------------------------------------------------

        for column in (
            1,
            2,
            3,
        ):

            spin = QDoubleSpinBox()

            spin.setRange(
                -100.0,
                100.0,
            )

            spin.setDecimals(
                8
            )

            spin.setValue(
                0.0
            )

            self.sites.setCellWidget(
                row,
                column,
                spin,
            )

        # --------------------------------------------------------
        # Occupancy
        # --------------------------------------------------------

        occupancy = QDoubleSpinBox()

        occupancy.setRange(
            0.0,
            1.0,
        )

        occupancy.setDecimals(
            6
        )

        occupancy.setSingleStep(
            0.01
        )

        occupancy.setValue(
            1.0
        )

        self.sites.setCellWidget(
            row,
            4,
            occupancy,
        )

    def _remove_site(self):

        row = (
            self.sites.currentRow()
        )

        if row >= 0:

            self.sites.removeRow(
                row
            )

    def _clear_sites(self):

        self.sites.setRowCount(
            0
        )

    # ============================================================
    # Coordinate labels
    # ============================================================

    def _update_coordinate_headers(
        self,
        *_,
    ):

        if not hasattr(
            self,
            "sites",
        ):

            return

        fractional = (
            self.coordinate_mode.currentText()
            == "Fractional"
        )

        if fractional:

            labels = [
                "x (fractional)",
                "y (fractional)",
                "z (fractional)",
            ]

        else:

            labels = [
                "x (Å)",
                "y (Å)",
                "z (Å)",
            ]

        for column, label in zip(
            (
                1,
                2,
                3,
            ),
            labels,
        ):

            self.sites.setHorizontalHeaderItem(
                column,
                QTableWidgetItem(
                    label
                )
            )

    # ============================================================
    # Read sites
    # ============================================================

    def _read_sites(self):

        symbols = []

        positions = []

        occupancies = []

        for row in range(
            self.sites.rowCount()
        ):

            element_widget = (
                self.sites.cellWidget(
                    row,
                    0,
                )
            )

            x_widget = (
                self.sites.cellWidget(
                    row,
                    1,
                )
            )

            y_widget = (
                self.sites.cellWidget(
                    row,
                    2,
                )
            )

            z_widget = (
                self.sites.cellWidget(
                    row,
                    3,
                )
            )

            occ_widget = (
                self.sites.cellWidget(
                    row,
                    4,
                )
            )

            symbol = (
                element_widget.currentText()
                .strip()
            )

            if symbol not in self.elements:

                raise ValueError(
                    f"Invalid element symbol: {symbol}"
                )

            symbols.append(
                symbol
            )

            positions.append(
                (
                    x_widget.value(),
                    y_widget.value(),
                    z_widget.value(),
                )
            )

            occupancies.append(
                occ_widget.value()
            )

        if not symbols:

            raise ValueError(
                "At least one atomic site is required."
            )

        return (
            symbols,
            positions,
            occupancies,
        )

    # ============================================================
    # Coordinate conversion
    # ============================================================

    def _get_cell(self):

        return np.array(
            cellpar_to_cell(
                [
                    self.a.value(),
                    self.b.value(),
                    self.c.value(),
                    self.alpha.value(),
                    self.beta.value(),
                    self.gamma.value(),
                ]
            ),
            dtype=float,
        )

    def _to_fractional(
        self,
        positions,
    ):

        if (
            self.coordinate_mode.currentText()
            == "Fractional"
        ):

            return positions

        cell = self._get_cell()

        inverse = np.linalg.inv(
            cell
        )

        result = []

        for position in positions:

            cartesian = np.asarray(
                position,
                dtype=float,
            )

            fractional = (
                cartesian @ inverse
            )

            result.append(
                tuple(
                    fractional
                )
            )

        return result

    # ============================================================
    # Generate crystal
    # ============================================================

    def _generate_atoms(self):

        (
            symbols,
            positions,
            occupancies,
        ) = self._read_sites()

        fractional_positions = (
            self._to_fractional(
                positions
            )
        )

        number = (
            self._current_spacegroup_number()
        )

        setting = (
            self.setting_combo.currentData()
        )

        if setting is None:

            setting = 1

        cellpar = [
            self.a.value(),
            self.b.value(),
            self.c.value(),
            self.alpha.value(),
            self.beta.value(),
            self.gamma.value(),
        ]

        atoms = crystal(
            symbols=symbols,
            basis=fractional_positions,
            occupancies=occupancies,
            spacegroup=number,
            setting=int(setting),
            cellpar=cellpar,
            primitive_cell=(
                self.primitive_check.isChecked()
            ),
            onduplicates="warn",
            symprec=0.001,
        )

        atoms.info[
            "quantum_studio_spacegroup"
        ] = number

        atoms.info[
            "quantum_studio_spacegroup_symbol"
        ] = Spacegroup(
            number,
            setting=int(setting),
        ).symbol

        atoms.info[
            "quantum_studio_setting"
        ] = int(setting)

        atoms.info[
            "quantum_studio_crystal_system"
        ] = crystal_system(
            number
        )

        return atoms

    # ============================================================
    # Preview
    # ============================================================

    def _preview(self):

        try:

            atoms = (
                self._generate_atoms()
            )

            self.generated_atoms = (
                atoms
            )

            formula = (
                atoms.get_chemical_formula(
                    mode="hill"
                )
            )

            number = (
                self._current_spacegroup_number()
            )

            symbol = (
                Spacegroup(
                    number
                ).symbol
            )

            self.preview_label.setText(
                (
                    f"{formula}   •   "
                    f"{len(atoms)} atoms   •   "
                    f"SG {number} {symbol}"
                )
            )

        except Exception as error:

            self.generated_atoms = None

            self.preview_label.setText(
                "Generation error"
            )

            QMessageBox.warning(
                self,
                "Crystal Builder",
                str(error),
            )

    # ============================================================
    # Validate
    # ============================================================

    def _validate_and_accept(self):

        try:

            atoms = (
                self._generate_atoms()
            )

            if len(atoms) == 0:

                raise ValueError(
                    "The generated structure contains no atoms."
                )

            self.generated_atoms = (
                atoms
            )

            self.accept()

        except Exception as error:

            QMessageBox.critical(
                self,
                "Crystal Generation Failed",
                (
                    f"{error}\n\n"
                    "Check the space group, lattice "
                    "parameters and unique atomic positions."
                ),
            )

    # ============================================================
    # Public result
    # ============================================================

    def generated_structure_atoms(self):

        return self.generated_atoms

    # ============================================================
    # Convert to Quantum Studio Structure
    # ============================================================

    def to_quantum_studio_structure(self):

        atoms = (
            self.generated_structure_atoms()
        )

        if atoms is None:

            raise RuntimeError(
                "No crystal has been generated."
            )

        from frontend.core.structure_io import (
            StructureIO,
        )

        temporary_path = None

        try:

            with tempfile.NamedTemporaryFile(
                suffix=".cif",
                delete=False,
            ) as handle:

                temporary_path = Path(
                    handle.name
                )

            write(
                str(temporary_path),
                atoms,
                format="cif",
            )

            structure = (
                StructureIO.read_structure(
                    str(temporary_path)
                )
            )

            number = (
                self._current_spacegroup_number()
            )

            setting = (
                self.setting_combo.currentData()
            )

            if setting is None:
                setting = 1

            try:

                structure.spacegroup_number = (
                    number
                )

                structure.spacegroup_symbol = (
                    Spacegroup(
                        number,
                        setting=int(setting),
                    ).symbol
                )

                structure.spacegroup_setting = (
                    int(setting)
                )

                structure.crystal_system = (
                    crystal_system(
                        number
                    )
                )

            except Exception:
                pass

            try:

                structure._record(
                    (
                        "Created with Crystal Builder: "
                        f"SG {number}"
                    )
                )

            except Exception:
                pass

            return structure

        finally:

            if (
                temporary_path is not None
                and temporary_path.exists()
            ):

                try:

                    temporary_path.unlink()

                except Exception:

                    pass
