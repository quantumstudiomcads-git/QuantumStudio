"""
Quantum Studio — Visualizer Tools

Additional V1 structure functionality:

    Undo / redo
    Structure export
    Coordinate editing
    Cartesian / fractional coordinates
    Symmetry detection
    Wyckoff positions
    Periodic image settings
    3D measurement-label settings
    Surface/slab analysis
    Crystal packing / coordination information
"""

from copy import deepcopy
from pathlib import Path

import numpy as np

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from frontend.structure_operations import (
    StructureOperations,
)

from frontend.crystallography import (
    Crystallography,
)


class ToolsMixin:

    # ================================================================
    # TOOLS TAB
    # ================================================================

    def _build_tools_tab(self):

        tab = QWidget()

        layout = QVBoxLayout(tab)

        title = QLabel("TOOLS")

        title.setObjectName(
            "sectionTitle"
        )

        layout.addWidget(title)

        tabs = QTabWidget()

        tabs.addTab(
            self._history_page(),
            "History",
        )

        tabs.addTab(
            self._coordinates_page(),
            "Coordinates",
        )

        tabs.addTab(
            self._symmetry_page(),
            "Symmetry",
        )

        tabs.addTab(
            self._periodic_page(),
            "Periodic",
        )

        tabs.addTab(
            self._surface_page(),
            "Surface",
        )

        tabs.addTab(
            self._packing_page(),
            "Packing",
        )

        tabs.addTab(
            self._export_page(),
            "Export",
        )

        layout.addWidget(
            tabs,
            1,
        )

        return tab

    # ================================================================
    # HISTORY
    # ================================================================

    def _history_page(self):

        page = QWidget()
        layout = QVBoxLayout(page)

        undo = QPushButton(
            "Undo"
        )

        undo.clicked.connect(
            self._qs_undo
        )

        redo = QPushButton(
            "Redo"
        )

        redo.clicked.connect(
            self._qs_redo
        )

        row = QHBoxLayout()

        row.addWidget(undo)
        row.addWidget(redo)

        layout.addLayout(row)

        self.operation_history = QListWidget()

        layout.addWidget(
            QLabel("STRUCTURE HISTORY")
        )

        layout.addWidget(
            self.operation_history
        )

        return page

    def _qs_initialize_history(self):

        if not hasattr(
            self,
            "_qs_undo_stack",
        ):

            self._qs_undo_stack = []

        if not hasattr(
            self,
            "_qs_redo_stack",
        ):

            self._qs_redo_stack = []

    def _qs_snapshot(self):

        self._qs_initialize_history()

        self._qs_undo_stack.append(
            deepcopy(
                self.structure
            )
        )

        self._qs_redo_stack.clear()

    def _qs_undo(self):

        self._qs_initialize_history()

        if not self._qs_undo_stack:

            self._qs_message(
                "Undo",
                "Nothing to undo."
            )

            return

        self._qs_redo_stack.append(
            deepcopy(
                self.structure
            )
        )

        self.structure = (
            self._qs_undo_stack.pop()
        )

        self._qs_refresh_after_structure_change(
            "Undo"
        )

    def _qs_redo(self):

        self._qs_initialize_history()

        if not self._qs_redo_stack:

            self._qs_message(
                "Redo",
                "Nothing to redo."
            )

            return

        self._qs_undo_stack.append(
            deepcopy(
                self.structure
            )
        )

        self.structure = (
            self._qs_redo_stack.pop()
        )

        self._qs_refresh_after_structure_change(
            "Redo"
        )

    def _qs_refresh_after_structure_change(
        self,
        operation,
    ):

        try:
            self._refresh_measurement_atoms()
        except Exception:
            pass

        try:
            self._refresh_structure()
        except Exception:
            pass

        try:
            self.operation_history.addItem(
                operation
            )
        except Exception:
            pass

    # ================================================================
    # COORDINATES
    # ================================================================

    def _coordinates_page(self):

        page = QWidget()
        layout = QVBoxLayout(page)

        self.coordinate_mode = QComboBox()

        self.coordinate_mode.addItems(
            [
                "Cartesian",
                "Fractional",
            ]
        )

        form = QFormLayout()

        form.addRow(
            "Coordinate system:",
            self.coordinate_mode,
        )

        layout.addLayout(form)

        self.coordinate_atom = QSpinBox()

        self.coordinate_atom.setMinimum(1)
        self.coordinate_atom.setMaximum(1)

        self.coordinate_atom.valueChanged.connect(
            self._load_coordinate_editor
        )

        form.addRow(
            "Atom:",
            self.coordinate_atom,
        )

        self.coordinate_element = QLabel(
            "-"
        )

        form.addRow(
            "Element:",
            self.coordinate_element,
        )

        self.coordinate_x = QDoubleSpinBox()
        self.coordinate_y = QDoubleSpinBox()
        self.coordinate_z = QDoubleSpinBox()

        for widget in (
            self.coordinate_x,
            self.coordinate_y,
            self.coordinate_z,
        ):

            widget.setDecimals(8)
            widget.setRange(
                -100000,
                100000,
            )

        form.addRow(
            "X / a:",
            self.coordinate_x,
        )

        form.addRow(
            "Y / b:",
            self.coordinate_y,
        )

        form.addRow(
            "Z / c:",
            self.coordinate_z,
        )

        self.coordinate_mode.currentIndexChanged.connect(
            self._load_coordinate_editor
        )

        load = QPushButton(
            "Load Atom"
        )

        load.clicked.connect(
            self._load_coordinate_editor
        )

        layout.addWidget(load)

        apply_button = QPushButton(
            "Apply Coordinate Change"
        )

        apply_button.clicked.connect(
            self._apply_coordinate_change
        )

        layout.addWidget(
            apply_button
        )

        normalize = QPushButton(
            "Wrap All Atoms into Unit Cell"
        )

        normalize.clicked.connect(
            self._wrap_structure
        )

        layout.addWidget(
            normalize
        )

        layout.addStretch()

        return page

    def _refresh_coordinate_editor(self):

        if not hasattr(
            self,
            "coordinate_atom",
        ):
            return

        count = len(
            self.structure.atoms
        )

        self.coordinate_atom.setMaximum(
            max(1, count)
        )

        if count:
            self._load_coordinate_editor()

    def _load_coordinate_editor(self):

        if not self.structure.atoms:
            return

        index = (
            self.coordinate_atom.value()
            - 1
        )

        index = max(
            0,
            min(
                index,
                len(
                    self.structure.atoms
                ) - 1,
            )
        )

        atom = self.structure.atoms[
            index
        ]

        self.coordinate_element.setText(
            atom.element
        )

        position = np.array(
            [
                atom.x,
                atom.y,
                atom.z,
            ],
            dtype=float,
        )

        if (
            self.coordinate_mode.currentText()
            == "Fractional"
        ):

            position = (
                StructureOperations
                .cartesian_to_fractional(
                    self.structure,
                    position,
                )
            )

        self.coordinate_x.setValue(
            float(position[0])
        )

        self.coordinate_y.setValue(
            float(position[1])
        )

        self.coordinate_z.setValue(
            float(position[2])
        )

    def _apply_coordinate_change(self):

        try:

            index = (
                self.coordinate_atom.value()
                - 1
            )

            if index < 0 or index >= len(
                self.structure.atoms
            ):

                raise ValueError(
                    "Invalid atom."
                )

            self._qs_snapshot()

            position = np.array(
                [
                    self.coordinate_x.value(),
                    self.coordinate_y.value(),
                    self.coordinate_z.value(),
                ]
            )

            atom = self.structure.atoms[
                index
            ]

            if (
                self.coordinate_mode.currentText()
                == "Fractional"
            ):

                position = (
                    StructureOperations
                    .fractional_to_cartesian(
                        self.structure,
                        position,
                    )
                )

            StructureOperations.set_atom_cartesian(
                atom,
                position,
            )

            self._qs_refresh_after_structure_change(
                "Coordinate edit"
            )

        except Exception as error:

            self._qs_message(
                "Coordinate error",
                str(error),
            )

    def _wrap_structure(self):

        try:

            self._qs_snapshot()

            for atom in self.structure.atoms:

                p = np.array(
                    [
                        atom.x,
                        atom.y,
                        atom.z,
                    ]
                )

                f = (
                    StructureOperations
                    .cartesian_to_fractional(
                        self.structure,
                        p,
                    )
                )

                f -= np.floor(f)

                p = (
                    StructureOperations
                    .fractional_to_cartesian(
                        self.structure,
                        f,
                    )
                )

                StructureOperations.set_atom_cartesian(
                    atom,
                    p,
                )

            self._qs_refresh_after_structure_change(
                "Wrap coordinates"
            )

        except Exception as error:

            self._qs_message(
                "Wrap error",
                str(error),
            )

    # ================================================================
    # SYMMETRY
    # ================================================================

    def _symmetry_page(self):

        page = QWidget()
        layout = QVBoxLayout(page)

        detect = QPushButton(
            "Detect Space Group"
        )

        detect.clicked.connect(
            self._detect_symmetry
        )

        layout.addWidget(detect)

        wyckoff = QPushButton(
            "Show Wyckoff Positions"
        )

        wyckoff.clicked.connect(
            self._show_wyckoff
        )

        layout.addWidget(wyckoff)

        primitive = QPushButton(
            "Analyze Primitive Cell"
        )

        primitive.clicked.connect(
            self._analyze_primitive
        )

        layout.addWidget(primitive)

        conventional = QPushButton(
            "Analyze Conventional Cell"
        )

        conventional.clicked.connect(
            self._analyze_conventional
        )

        layout.addWidget(conventional)

        self.symmetry_result = QTextEdit()

        self.symmetry_result.setReadOnly(
            True
        )

        layout.addWidget(
            self.symmetry_result
        )

        return page

    def _symmetry_data(self):

        return Crystallography.symmetry(
            self.structure
        )

    def _detect_symmetry(self):

        result = self._symmetry_data()

        if not result.get(
            "available",
            False,
        ):

            self.symmetry_result.setPlainText(
                result.get(
                    "error",
                    "Symmetry unavailable.",
                )
            )

            return

        if "error" in result:

            self.symmetry_result.setPlainText(
                result["error"]
            )

            return

        text = (
            f"Space group: "
            f"{result['international']}\n"
            f"Number: "
            f"{result['number']}\n"
            f"Hall symbol: "
            f"{result['hall']}\n"
            f"Point group: "
            f"{result['pointgroup']}"
        )

        self.symmetry_result.setPlainText(
            text
        )

    def _show_wyckoff(self):

        result = self._symmetry_data()

        if "wyckoffs" not in result:

            self.symmetry_result.setPlainText(
                result.get(
                    "error",
                    "Wyckoff data unavailable.",
                )
            )

            return

        lines = [
            "Wyckoff positions",
            "──────────────────",
        ]

        for i, site in enumerate(
            result["wyckoffs"]
        ):

            atom = self.structure.atoms[i]

            lines.append(
                f"{i + 1:03d} "
                f"{atom.element:>2}    "
                f"{site}"
            )

        self.symmetry_result.setPlainText(
            "\n".join(lines)
        )

    def _analyze_primitive(self):

        primitive = (
            Crystallography
            .primitive_structure(
                self.structure
            )
        )

        if primitive is None:

            self.symmetry_result.setPlainText(
                "Primitive-cell analysis "
                "requires spglib."
            )

            return

        cell, positions, numbers = primitive

        self.symmetry_result.setPlainText(
            "Primitive-cell analysis\n"
            "───────────────────────\n"
            f"Atoms: {len(numbers)}\n\n"
            f"a = {np.linalg.norm(cell[0]):.6f} Å\n"
            f"b = {np.linalg.norm(cell[1]):.6f} Å\n"
            f"c = {np.linalg.norm(cell[2]):.6f} Å"
        )

    def _analyze_conventional(self):

        conventional = (
            Crystallography
            .conventional_structure(
                self.structure
            )
        )

        if conventional is None:

            self.symmetry_result.setPlainText(
                "Conventional-cell analysis "
                "requires spglib."
            )

            return

        cell, positions, numbers = conventional

        self.symmetry_result.setPlainText(
            "Conventional-cell analysis\n"
            "──────────────────────────\n"
            f"Atoms: {len(numbers)}\n\n"
            f"a = {np.linalg.norm(cell[0]):.6f} Å\n"
            f"b = {np.linalg.norm(cell[1]):.6f} Å\n"
            f"c = {np.linalg.norm(cell[2]):.6f} Å"
        )

    # ================================================================
    # PERIODIC IMAGES
    # ================================================================

    def _periodic_page(self):

        page = QWidget()
        layout = QVBoxLayout(page)

        form = QFormLayout()

        self.periodic_x = QSpinBox()
        self.periodic_y = QSpinBox()
        self.periodic_z = QSpinBox()

        for spin in (
            self.periodic_x,
            self.periodic_y,
            self.periodic_z,
        ):

            spin.setRange(
                0,
                5,
            )

        form.addRow(
            "±X images:",
            self.periodic_x,
        )

        form.addRow(
            "±Y images:",
            self.periodic_y,
        )

        form.addRow(
            "±Z images:",
            self.periodic_z,
        )

        layout.addLayout(form)

        apply_button = QPushButton(
            "Apply Periodic Images"
        )

        apply_button.clicked.connect(
            self._apply_periodic_images
        )

        layout.addWidget(
            apply_button
        )

        clear_button = QPushButton(
            "Clear Periodic Images"
        )

        clear_button.clicked.connect(
            self._clear_periodic_images
        )

        layout.addWidget(
            clear_button
        )

        layout.addWidget(
            QLabel(
                "Periodic images are a visualization "
                "setting and do not modify the structure."
            )
        )

        layout.addStretch()

        return page

    def _apply_periodic_images(self):

        try:

            if hasattr(
                self,
                "viewport",
            ) and hasattr(
                self.viewport,
                "set_periodic_images",
            ):

                self.viewport.set_periodic_images(
                    self.periodic_x.value(),
                    self.periodic_y.value(),
                    self.periodic_z.value(),
                )

            elif hasattr(
                self,
                "set_periodic_images",
            ):

                self.set_periodic_images(
                    self.periodic_x.value(),
                    self.periodic_y.value(),
                    self.periodic_z.value(),
                )

            else:

                self._qs_message(
                    "Periodic images",
                    "Periodic-image controls are ready, "
                    "but the 3D viewport has not exposed "
                    "the image API yet.",
                )

        except Exception as error:

            self._qs_message(
                "Periodic image error",
                str(error),
            )

    def _clear_periodic_images(self):

        try:

            if hasattr(
                self,
                "viewport",
            ) and hasattr(
                self.viewport,
                "set_periodic_images",
            ):

                self.viewport.set_periodic_images(
                    0,
                    0,
                    0,
                )

            else:

                self._qs_message(
                    "Periodic images",
                    "Periodic images cleared."
                )

        except Exception as error:

            self._qs_message(
                "Periodic image error",
                str(error),
            )

    # ================================================================
    # SURFACE
    # ================================================================

    def _surface_page(self):

        page = QWidget()
        layout = QVBoxLayout(page)

        form = QFormLayout()

        self.surface_axis = QComboBox()

        self.surface_axis.addItems(
            [
                "X",
                "Y",
                "Z",
            ]
        )

        form.addRow(
            "Surface normal:",
            self.surface_axis,
        )

        self.surface_tol = QDoubleSpinBox()

        self.surface_tol.setRange(
            0.01,
            10.0,
        )

        self.surface_tol.setValue(
            0.5
        )

        self.surface_tol.setSuffix(
            " Å"
        )

        form.addRow(
            "Layer tolerance:",
            self.surface_tol,
        )

        layout.addLayout(form)

        detect = QPushButton(
            "Analyze Surface Layers"
        )

        detect.clicked.connect(
            self._surface_analysis
        )

        layout.addWidget(detect)

        self.surface_result = QTextEdit()

        self.surface_result.setReadOnly(
            True
        )

        layout.addWidget(
            self.surface_result
        )

        return page

    def _surface_analysis(self):

        try:

            axis = {
                "X": 0,
                "Y": 1,
                "Z": 2,
            }[
                self.surface_axis.currentText()
            ]

            layers = (
                StructureOperations.layer_groups(
                    self.structure,
                    axis,
                    self.surface_tol.value(),
                )
            )

            if not layers:

                raise ValueError(
                    "No layers detected."
                )

            centers = []

            for layer in layers:

                values = [
                    value
                    for value, index in layer
                ]

                centers.append(
                    float(
                        np.mean(values)
                    )
                )

            lines = [
                f"Layers detected: "
                f"{len(layers)}",
                "",
            ]

            for i, (layer, center) in enumerate(
                zip(layers, centers),
                start=1,
            ):

                lines.append(
                    f"Layer {i}: "
                    f"{len(layer)} atoms, "
                    f"center = {center:.5f} Å"
                )

            lines.append("")
            lines.append(
                "Interlayer distances:"
            )

            for i in range(
                len(centers) - 1
            ):

                lines.append(
                    f"{i + 1} → {i + 2}: "
                    f"{centers[i + 1] - centers[i]:.5f} Å"
                )

            self.surface_result.setPlainText(
                "\n".join(lines)
            )

        except Exception as error:

            self.surface_result.setPlainText(
                str(error)
            )

    # ================================================================
    # PACKING / POLYHEDRA
    # ================================================================

    def _packing_page(self):

        page = QWidget()
        layout = QVBoxLayout(page)

        form = QFormLayout()

        self.packing_atom = QSpinBox()

        self.packing_atom.setMinimum(1)
        self.packing_atom.setMaximum(1)

        form.addRow(
            "Central atom:",
            self.packing_atom,
        )

        self.packing_cutoff = QDoubleSpinBox()

        self.packing_cutoff.setRange(
            0.5,
            10.0,
        )

        self.packing_cutoff.setValue(
            2.0
        )

        self.packing_cutoff.setSuffix(
            " Å"
        )

        form.addRow(
            "Neighbor cutoff:",
            self.packing_cutoff,
        )

        layout.addLayout(form)

        analyze = QPushButton(
            "Analyze Coordination Polyhedron"
        )

        analyze.clicked.connect(
            self._packing_analysis
        )

        layout.addWidget(analyze)

        self.packing_result = QTextEdit()

        self.packing_result.setReadOnly(
            True
        )

        layout.addWidget(
            self.packing_result
        )

        return page

    def _packing_analysis(self):

        try:

            index = (
                self.packing_atom.value()
                - 1
            )

            neighbors = (
                StructureOperations.coordination(
                    self.structure,
                    index,
                    self.packing_cutoff.value(),
                )
            )

            if not neighbors:

                raise ValueError(
                    "No neighbors found."
                )

            central = self.structure.atoms[
                index
            ]

            elements = {}

            for _, element, distance in neighbors:

                elements.setdefault(
                    element,
                    [],
                ).append(distance)

            lines = [
                "Coordination polyhedron",
                "────────────────────────",
                f"Central atom: "
                f"{index + 1} "
                f"{central.element}",
                f"Coordination number: "
                f"{len(neighbors)}",
                "",
            ]

            for element, distances in elements.items():

                lines.append(
                    f"{element}: "
                    f"{len(distances)} neighbors"
                )

                lines.append(
                    "  distances: "
                    +
                    ", ".join(
                        f"{d:.4f}"
                        for d in distances
                    )
                    +
                    " Å"
                )

            self.packing_result.setPlainText(
                "\n".join(lines)
            )

        except Exception as error:

            self.packing_result.setPlainText(
                str(error)
            )

    # ================================================================
    # EXPORT
    # ================================================================

    def _export_page(self):

        page = QWidget()
        layout = QVBoxLayout(page)

        layout.addWidget(
            QLabel(
                "Export the current structure independently "
                "of the .qs project."
            )
        )

        formats = [
            ("XYZ", "*.xyz"),
            ("CIF", "*.cif"),
            ("POSCAR", "*.vasp"),
        ]

        for name, pattern in formats:

            button = QPushButton(
                f"Export {name}"
            )

            button.clicked.connect(
                lambda checked=False,
                n=name,
                p=pattern:
                self._export_structure(
                    n,
                    p,
                )
            )

            layout.addWidget(button)

        layout.addStretch()

        return page

    def _export_structure(
        self,
        format_name,
        pattern,
    ):

        path, _ = QFileDialog.getSaveFileName(
            self,
            f"Export {format_name}",
            str(Path.home()),
            f"{format_name} (*{pattern[1:]})",
        )

        if not path:
            return

        try:

            if format_name == "XYZ":
                self._write_xyz(path)

            elif format_name == "CIF":
                self._write_cif(path)

            elif format_name == "POSCAR":
                self._write_poscar(path)

            self._qs_message(
                "Export complete",
                f"Structure exported to:\n{path}",
            )

        except Exception as error:

            self._qs_message(
                "Export failed",
                str(error),
            )

    def _write_xyz(self, path):

        with open(
            path,
            "w",
        ) as f:

            f.write(
                f"{len(self.structure.atoms)}\n"
            )

            f.write(
                "Quantum Studio structure\n"
            )

            for atom in self.structure.atoms:

                f.write(
                    f"{atom.element} "
                    f"{atom.x:.10f} "
                    f"{atom.y:.10f} "
                    f"{atom.z:.10f}\n"
                )

    def _write_poscar(self, path):

        cell = np.asarray(
            self.structure.cell,
            dtype=float,
        )

        with open(
            path,
            "w",
        ) as f:

            f.write(
                "Quantum Studio structure\n"
            )

            f.write("1.0\n")

            for vector in cell:

                f.write(
                    " ".join(
                        f"{x:.10f}"
                        for x in vector
                    )
                    + "\n"
                )

            species = []

            for atom in self.structure.atoms:

                if atom.element not in species:

                    species.append(
                        atom.element
                    )

            f.write(
                " ".join(species)
                + "\n"
            )

            counts = [
                sum(
                    1
                    for atom in self.structure.atoms
                    if atom.element == species_name
                )
                for species_name in species
            ]

            f.write(
                " ".join(
                    str(x)
                    for x in counts
                )
                + "\n"
            )

            f.write(
                "Cartesian\n"
            )

            for species_name in species:

                for atom in self.structure.atoms:

                    if atom.element == species_name:

                        f.write(
                            f"{atom.x:.10f} "
                            f"{atom.y:.10f} "
                            f"{atom.z:.10f}\n"
                        )

    def _write_cif(self, path):

        cell = np.asarray(
            self.structure.cell,
            dtype=float,
        )

        params = (
            StructureOperations
            .cell_parameters(
                self.structure
            )
        )

        with open(
            path,
            "w",
        ) as f:

            f.write(
                "data_quantum_studio\n\n"
            )

            f.write(
                f"_cell_length_a "
                f"{params['a']:.8f}\n"
            )

            f.write(
                f"_cell_length_b "
                f"{params['b']:.8f}\n"
            )

            f.write(
                f"_cell_length_c "
                f"{params['c']:.8f}\n"
            )

            f.write(
                f"_cell_angle_alpha "
                f"{params['alpha']:.8f}\n"
            )

            f.write(
                f"_cell_angle_beta "
                f"{params['beta']:.8f}\n"
            )

            f.write(
                f"_cell_angle_gamma "
                f"{params['gamma']:.8f}\n\n"
            )

            f.write(
                "loop_\n"
                "_atom_site_label\n"
                "_atom_site_type_symbol\n"
                "_atom_site_Cartn_x\n"
                "_atom_site_Cartn_y\n"
                "_atom_site_Cartn_z\n"
            )

            counters = {}

            for atom in self.structure.atoms:

                counters[atom.element] = (
                    counters.get(
                        atom.element,
                        0,
                    )
                    + 1
                )

                label = (
                    f"{atom.element}"
                    f"{counters[atom.element]}"
                )

                f.write(
                    f"{label} "
                    f"{atom.element} "
                    f"{atom.x:.8f} "
                    f"{atom.y:.8f} "
                    f"{atom.z:.8f}\n"
                )

    # ================================================================
    # HELPERS
    # ================================================================

    def _qs_message(
        self,
        title,
        text,
    ):

        QMessageBox.information(
            self,
            title,
            text,
        )
