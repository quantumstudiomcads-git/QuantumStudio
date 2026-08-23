"""
Quantum Studio
Builder — Build / Structure Construction

Build operations:
    Import
    Supercell
    Slab
    Vacuum
    Strain
    Nanotube
    Heterostructure
    Layered Structure
    Moiré Structure
    Crystal Builder
"""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from frontend.builder.build.operations import (
    create_supercell,
    create_slab,
    add_vacuum,
    apply_strain,
    create_nanotube,
    create_heterostructure,
    create_layered_structure,
    create_moire_structure,
)



class SupercellDialog(QDialog):

    def __init__(
        self,
        parent=None,
    ):

        super().__init__(
            parent
        )

        self.setWindowTitle(
            "Create Supercell"
        )

        self.setMinimumWidth(
            360
        )

        layout = QVBoxLayout(
            self
        )

        form = QFormLayout()

        self.nx = QSpinBox()
        self.ny = QSpinBox()
        self.nz = QSpinBox()

        for box in (
            self.nx,
            self.ny,
            self.nz,
        ):

            box.setRange(
                1,
                50,
            )

            box.setValue(
                1
            )

        form.addRow(
            "A scaling:",
            self.nx,
        )

        form.addRow(
            "B scaling:",
            self.ny,
        )

        form.addRow(
            "C scaling:",
            self.nz,
        )

        layout.addLayout(
            form
        )

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            |
            QDialogButtonBox.StandardButton.Cancel
        )

        buttons.accepted.connect(
            self.accept
        )

        buttons.rejected.connect(
            self.reject
        )

        layout.addWidget(
            buttons
        )


class HeterostructureDialog(QDialog):

    def __init__(
        self,
        parent=None,
        moire=False,
    ):

        super().__init__(
            parent
        )

        self.moire = moire

        self.setWindowTitle(
            (
                "Quantum Studio — "
                + (
                    "Moiré Builder"
                    if moire
                    else "Heterostructure Builder"
                )
            )
        )

        self.resize(
            620,
            520,
        )

        self._build_ui()

    def _build_ui(self):

        root = QVBoxLayout(
            self
        )

        title = QLabel(
            (
                "MOIRÉ BUILDER"
                if self.moire
                else "HETEROSTRUCTURE BUILDER"
            )
        )

        title.setStyleSheet(
            """
            font-size: 18px;
            font-weight: 700;
            """
        )

        root.addWidget(
            title
        )

        subtitle = QLabel(
            (
                "Construct a commensurate twisted bilayer."
                if self.moire
                else
                "Combine two crystal structures into a "
                "commensurate heterostructure."
            )
        )

        subtitle.setStyleSheet(
            "color: #858C98;"
        )

        subtitle.setWordWrap(
            True
        )

        root.addWidget(
            subtitle
        )

        # --------------------------------------------------------
        # Input layers
        # --------------------------------------------------------

        input_box = QGroupBox(
            "INPUT STRUCTURES"
        )

        input_layout = QFormLayout(
            input_box
        )

        self.bottom_path = QLineEditCompat()

        bottom_button = QPushButton(
            "Browse…"
        )

        bottom_button.clicked.connect(
            lambda: self._browse(
                self.bottom_path
            )
        )

        bottom_row = QWidget()

        bottom_layout = QHBoxLayout(
            bottom_row
        )

        bottom_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        bottom_layout.addWidget(
            self.bottom_path
        )

        bottom_layout.addWidget(
            bottom_button
        )

        input_layout.addRow(
            "Bottom layer:",
            bottom_row,
        )

        self.top_path = QLineEditCompat()

        top_button = QPushButton(
            "Browse…"
        )

        top_button.clicked.connect(
            lambda: self._browse(
                self.top_path
            )
        )

        top_row = QWidget()

        top_layout = QHBoxLayout(
            top_row
        )

        top_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        top_layout.addWidget(
            self.top_path
        )

        top_layout.addWidget(
            top_button
        )

        input_layout.addRow(
            "Top layer:",
            top_row,
        )

        root.addWidget(
            input_box
        )

        # --------------------------------------------------------
        # Matching
        # --------------------------------------------------------

        match_box = QGroupBox(
            "LATTICE MATCHING"
        )

        match_layout = QFormLayout(
            match_box
        )

        self.max_index = QSpinBox()

        self.max_index.setRange(
            1,
            15,
        )

        self.max_index.setValue(
            6 if not self.moire else 8
        )

        match_layout.addRow(
            "Maximum supercell index:",
            self.max_index,
        )

        self.max_strain = QDoubleSpinBox()

        self.max_strain.setRange(
            0.0,
            0.50,
        )

        self.max_strain.setDecimals(
            4
        )

        self.max_strain.setSingleStep(
            0.001
        )

        self.max_strain.setValue(
            0.05 if not self.moire else 0.01
        )

        self.max_strain.setSuffix(
            "  (fraction)"
        )

        match_layout.addRow(
            "Maximum strain:",
            self.max_strain,
        )

        self.strain_mode = QComboBox()

        self.strain_mode.addItems(
            [
                "Balanced",
                "Bottom layer",
                "Top layer",
            ]
        )

        match_layout.addRow(
            "Strain distribution:",
            self.strain_mode,
        )

        root.addWidget(
            match_box
        )

        # --------------------------------------------------------
        # Geometry
        # --------------------------------------------------------

        geometry_box = QGroupBox(
            "GEOMETRY"
        )

        geometry_layout = QFormLayout(
            geometry_box
        )

        self.interlayer = QDoubleSpinBox()

        self.interlayer.setRange(
            0.5,
            20.0,
        )

        self.interlayer.setDecimals(
            3
        )

        self.interlayer.setValue(
            3.4
        )

        self.interlayer.setSuffix(
            " Å"
        )

        geometry_layout.addRow(
            "Interlayer distance:",
            self.interlayer,
        )

        self.vacuum = QDoubleSpinBox()

        self.vacuum.setRange(
            0.0,
            100.0,
        )

        self.vacuum.setDecimals(
            2
        )

        self.vacuum.setValue(
            15.0
        )

        self.vacuum.setSuffix(
            " Å"
        )

        geometry_layout.addRow(
            "Vacuum:",
            self.vacuum,
        )

        self.twist = QDoubleSpinBox()

        self.twist.setRange(
            -180.0,
            180.0,
        )

        self.twist.setDecimals(
            6
        )

        self.twist.setSingleStep(
            0.1
        )

        self.twist.setValue(
            0.0
        )

        self.twist.setSuffix(
            "°"
        )

        geometry_layout.addRow(
            "Twist angle:",
            self.twist,
        )

        if not self.moire:

            self.twist.setEnabled(
                True
            )

        root.addWidget(
            geometry_box
        )

        # --------------------------------------------------------
        # Info
        # --------------------------------------------------------

        info = QLabel(
            (
                "The builder searches integer 2D supercells "
                "for a common in-plane lattice. Smaller "
                "mismatch and smaller supercells are preferred."
            )
        )

        info.setWordWrap(
            True
        )

        info.setStyleSheet(
            """
            color: #858C98;
            background: #17191F;
            border: 1px solid #292D35;
            border-radius: 6px;
            padding: 9px;
            """
        )

        root.addWidget(
            info
        )

        root.addStretch()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            |
            QDialogButtonBox.StandardButton.Cancel
        )

        buttons.accepted.connect(
            self.accept
        )

        buttons.rejected.connect(
            self.reject
        )

        root.addWidget(
            buttons
        )

    def _browse(
        self,
        line_edit,
    ):

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Crystal Structure",
            "",
            (
                "Crystal structures "
                "(*.cif *.vasp *.poscar *.xsf *.xyz "
                "*.pdb *.res *.cell);;"
                "All files (*)"
            ),
        )

        if path:

            line_edit.setText(
                path
            )

    def values(self):

        modes = [
            "balanced",
            "bottom",
            "top",
        ]

        return {
            "bottom": self.bottom_path.text().strip(),
            "top": self.top_path.text().strip(),
            "max_index": self.max_index.value(),
            "max_strain": self.max_strain.value(),
            "strain_mode": modes[
                self.strain_mode.currentIndex()
            ],
            "interlayer_distance":
                self.interlayer.value(),
            "vacuum":
                self.vacuum.value(),
            "twist_angle":
                self.twist.value(),
        }


class LabeledPathWidget(QWidget):

    pass


class QLineEditCompat(QWidget):

    def __init__(
        self,
        parent=None,
    ):

        super().__init__(
            parent
        )

        from PySide6.QtWidgets import (
            QLineEdit,
        )

        self._line = QLineEdit()

        layout = QHBoxLayout(
            self
        )

        layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        layout.addWidget(
            self._line
        )

    def text(self):

        return self._line.text()

    def setText(
        self,
        text,
    ):

        self._line.setText(
            text
        )


# ================================================================
# Builder Build Mixin
# ================================================================

class BuilderBuildMixin:

    def _build_build_tab(self):
        """
        Compatibility entry point used by Builder.

        The actual Build UI is implemented by
        _build_build_panel().
        """
        return self._build_build_panel()


    def _build_build_tab(self):
        """
        Compatibility entry point used by Builder.

        The actual Build UI is implemented by
        _build_build_panel().
        """
        return self._build_build_panel()


    def _build_build_tab(self):
        """
        Compatibility entry point used by Builder.

        The actual Build UI is implemented by
        _build_build_panel().
        """
        return self._build_build_panel()


    def _build_build_panel(
        self,
    ):

        """
        Build-panel entry point.

        Existing Builder implementations can call this
        method when constructing the Build tab.
        """

        panel = QWidget()

        layout = QVBoxLayout(
            panel
        )

        layout.setContentsMargins(
            8,
            8,
            8,
            8,
        )

        # --------------------------------------------------------
        # Structure input
        # --------------------------------------------------------

        section = QLabel(
            "STRUCTURE INPUT"
        )

        section.setStyleSheet(
            "font-size: 10px; color: #858C98;"
        )

        layout.addWidget(
            section
        )

        import_button = QPushButton(
            "Import Structure"
        )

        import_button.clicked.connect(
            self._build_import_structure
        )

        layout.addWidget(
            import_button
        )

        crystal_button = QPushButton(
            "Crystal Builder"
        )

        crystal_button.clicked.connect(
            self._build_crystal_builder
        )

        layout.addWidget(
            crystal_button
        )

        # --------------------------------------------------------
        # Basic construction
        # --------------------------------------------------------

        section = QLabel(
            "BUILD"
        )

        section.setStyleSheet(
            "font-size: 10px; color: #858C98;"
        )

        layout.addWidget(
            section
        )

        buttons = [
            (
                "Create Supercell",
                self._build_supercell,
            ),
            (
                "Create Slab",
                self._build_slab,
            ),
            (
                "Add Vacuum",
                self._build_vacuum,
            ),
            (
                "Apply Strain",
                self._build_strain,
            ),
            (
                "Create Nanotube",
                self._build_nanotube,
            ),
            (
                "Create Heterostructure",
                self._build_heterostructure,
            ),
            (
                "Create Moiré Structure",
                self._build_moire,
            ),
            (
                "Create Layered Structure",
                self._build_layered,
            ),
        ]

        for text, callback in buttons:

            button = QPushButton(
                text
            )

            button.clicked.connect(
                callback
            )

            layout.addWidget(
                button
            )

        layout.addStretch()

        return panel

    # ============================================================
    # Helpers
    # ============================================================

    def _set_generated_structure(
        self,
        atoms,
        description="Structure generated",
    ):

        if atoms is None:

            raise RuntimeError(
                "No structure was generated."
            )

        # Build operations may use ASE internally, but the Builder
        # and Project always operate on Quantum Studio native Structure.
        from ase import Atoms
        from frontend.core.structure import Structure
        from frontend.core.structure_io import StructureIO

        if isinstance(atoms, Atoms):

            structure = StructureIO.from_ase(
                atoms,
                name=description,
            )

        elif isinstance(atoms, Structure):

            structure = atoms

        else:

            raise TypeError(
                "Generated structure must be an ASE Atoms object "
                "or a Quantum Studio Structure."
            )

        # The main Builder has historically used different
        # names for its active structure. Handle the common cases.
        if hasattr(
            self,
            "atoms",
        ):

            self.atoms = structure

        if hasattr(
            self,
            "structure",
        ):

            self.structure = structure

        if hasattr(
            self,
            "_structure",
        ):

            self._structure = structure

        commit = getattr(
            self,
            "_commit",
            None,
        )

        if callable(commit):

            commit()

        else:

            # Preserve compatibility with non-Builder consumers
            # that provide a refresh method but no Project commit path.
            for method_name in (
                "_refresh_structure_view",
                "_refresh_view",
                "refresh_view",
                "_update_structure_view",
                "_render_structure",
            ):

                method = getattr(
                    self,
                    method_name,
                    None,
                )

                if callable(method):

                    try:

                        method()

                    except TypeError:

                        pass

                    break


        # Refresh status.
        status = getattr(
            self,
            "statusBar",
            None,
        )

        if callable(status):

            try:

                status().showMessage(
                    description
                )

            except Exception:

                pass

    # ============================================================
    # Import
    # ============================================================

    def _build_import_structure(
        self,
    ):

        try:

            path, _ = QFileDialog.getOpenFileName(
                self,
                "Import Crystal Structure",
                "",
                (
                    "Crystal structures "
                    "(*.cif *.CIF "
                    "*.vasp *.VASP "
                    "*.poscar *.POSCAR "
                    "POSCAR CONTCAR "
                    "POSCAR_* CONTCAR_* "
                    "*.xsf *.XSF "
                    "*.xyz *.XYZ "
                    "*.pdb *.PDB "
                    "*.res *.RES "
                    "*.cell *.CELL);;"
                    "All files (*)"
                    "All files (*)"
                ),
            )

            if not path:

                return

            from ase.io import read

            atoms = read(
                path
            )

            self._set_generated_structure(
                atoms,
                f"Imported {Path(path).name}",
            )

        except Exception as error:

            QMessageBox.critical(
                self,
                "Import Failed",
                str(error),
            )

    # ============================================================
    # Crystal Builder
    # ============================================================

    def _build_crystal_builder(
        self,
    ):

        try:

            from frontend.builder.build.crystal import (
                CrystalBuilderDialog,
            )

            dialog = (
                CrystalBuilderDialog(
                    self
                )
            )

            if (
                dialog.exec()
                != QDialog.DialogCode.Accepted
            ):

                return

            atoms = (
                dialog.generated_structure_atoms()
            )

            self._set_generated_structure(
                atoms,
                "Crystal generated",
            )

        except Exception as error:

            QMessageBox.critical(
                self,
                "Crystal Builder Failed",
                str(error),
            )

    # ============================================================
    # Supercell
    # ============================================================

    def _build_supercell(
        self,
    ):

        dialog = SupercellDialog(
            self
        )

        if (
            dialog.exec()
            != QDialog.DialogCode.Accepted
        ):
            return

        try:

            structure = self._get_active_structure()

            nx = dialog.nx.value()
            ny = dialog.ny.value()
            nz = dialog.nz.value()

            if not hasattr(
                structure,
                "make_supercell",
            ):

                raise RuntimeError(
                    "The active structure does not support "
                    "native supercell generation."
                )

            structure.make_supercell(
                nx,
                ny,
                nz,
            )

            if hasattr(
                self,
                "_commit",
            ):

                self._commit()

            else:

                self._set_generated_structure(
                    structure,
                    f"Supercell {nx}×{ny}×{nz}",
                )

        except Exception as error:

            QMessageBox.critical(
                self,
                "Supercell Failed",
                str(error),
            )


    # ============================================================
    # Slab
    # ============================================================

    def _build_slab(
        self,
    ):

        try:

            from PySide6.QtWidgets import QInputDialog

            vacuum, ok = QInputDialog.getDouble(
                self,
                "Create Slab",
                "Vacuum (Å):",
                15.0,
                0.0,
                100.0,
                2,
            )

            if not ok:
                return

            structure = (
                self._get_active_structure()
            )

            atoms = create_slab(
                structure,
                vacuum=vacuum,
            )

            self._set_generated_structure(
                atoms,
                "Slab generated",
            )

        except Exception as error:

            QMessageBox.critical(
                self,
                "Slab Failed",
                str(error),
            )

    # ============================================================
    # Vacuum
    # ============================================================

    def _build_vacuum(
        self,
    ):

        try:

            from PySide6.QtWidgets import QInputDialog

            vacuum, ok = QInputDialog.getDouble(
                self,
                "Add Vacuum",
                "Additional vacuum (Å):",
                10.0,
                0.0,
                100.0,
                2,
            )

            if not ok:
                return

            atoms = add_vacuum(
                self._get_active_structure(),
                vacuum,
            )

            self._set_generated_structure(
                atoms,
                f"Added {vacuum:.2f} Å vacuum",
            )

        except Exception as error:

            QMessageBox.critical(
                self,
                "Vacuum Failed",
                str(error),
            )

    # ============================================================
    # Strain
    # ============================================================

    def _build_strain(
        self,
    ):

        try:

            from PySide6.QtWidgets import QInputDialog

            strain, ok = QInputDialog.getDouble(
                self,
                "Apply Strain",
                "Biaxial strain (%):",
                0.0,
                -99.0,
                500.0,
                3,
            )

            if not ok:
                return

            fraction = (
                strain / 100.0
            )

            atoms = apply_strain(
                self._get_active_structure(),
                strain_x=fraction,
                strain_y=fraction,
            )

            self._set_generated_structure(
                atoms,
                f"Applied {strain:.3f}% biaxial strain",
            )

        except Exception as error:

            QMessageBox.critical(
                self,
                "Strain Failed",
                str(error),
            )

    # ============================================================
    # Nanotube
    # ============================================================

    def _build_nanotube(
        self,
    ):

        try:

            from PySide6.QtWidgets import QInputDialog

            radius, ok = QInputDialog.getDouble(
                self,
                "Create Nanotube",
                "Radius (Å):",
                10.0,
                0.5,
                500.0,
                2,
            )

            if not ok:
                return

            atoms = create_nanotube(
                self._get_active_structure(),
                radius,
            )

            self._set_generated_structure(
                atoms,
                f"Nanotube radius {radius:.2f} Å",
            )

        except Exception as error:

            QMessageBox.critical(
                self,
                "Nanotube Failed",
                str(error),
            )

    # ============================================================
    # Heterostructure
    # ============================================================

    def _build_heterostructure(
        self,
    ):

        try:

            dialog = (
                HeterostructureDialog(
                    self,
                    moire=False,
                )
            )

            if (
                dialog.exec()
                != QDialog.DialogCode.Accepted
            ):

                return

            values = (
                dialog.values()
            )

            if not values["bottom"]:

                raise ValueError(
                    "Select the bottom-layer structure."
                )

            if not values["top"]:

                raise ValueError(
                    "Select the top-layer structure."
                )

            atoms = create_heterostructure(
                values["bottom"],
                values["top"],
                interlayer_distance=(
                    values["interlayer_distance"]
                ),
                max_index=(
                    values["max_index"]
                ),
                max_strain=(
                    values["max_strain"]
                ),
                strain_mode=(
                    values["strain_mode"]
                ),
                twist_angle=(
                    values["twist_angle"]
                ),
                vacuum=(
                    values["vacuum"]
                ),
            )

            mismatch = atoms.info.get(
                "heterostructure_mismatch",
                0.0,
            )

            self._set_generated_structure(
                atoms,
                (
                    "Heterostructure generated — "
                    f"mismatch {100*mismatch:.3f}%"
                ),
            )

        except Exception as error:

            QMessageBox.critical(
                self,
                "Heterostructure Failed",
                str(error),
            )

    # ============================================================
    # Moiré
    # ============================================================

    def _build_moire(
        self,
    ):

        try:

            dialog = (
                HeterostructureDialog(
                    self,
                    moire=True,
                )
            )

            if (
                dialog.exec()
                != QDialog.DialogCode.Accepted
            ):

                return

            values = (
                dialog.values()
            )

            if not values["bottom"]:

                raise ValueError(
                    "Select the bottom-layer structure."
                )

            if not values["top"]:

                raise ValueError(
                    "Select the top-layer structure."
                )

            atoms = create_moire_structure(
                values["bottom"],
                values["top"],
                twist_angle=(
                    values["twist_angle"]
                ),
                max_index=(
                    values["max_index"]
                ),
                max_strain=(
                    values["max_strain"]
                ),
                interlayer_distance=(
                    values["interlayer_distance"]
                ),
                vacuum=(
                    values["vacuum"]
                ),
                strain_mode=(
                    values["strain_mode"]
                ),
            )

            self._set_generated_structure(
                atoms,
                (
                    "Moiré structure generated — "
                    f"twist {values['twist_angle']:.4f}°"
                ),
            )

        except Exception as error:

            QMessageBox.critical(
                self,
                "Moiré Builder Failed",
                str(error),
            )

    # ============================================================
    # Layered structure
    # ============================================================

    def _build_layered(
        self,
    ):

        try:

            from PySide6.QtWidgets import (
                QInputDialog,
            )

            count, ok = QInputDialog.getInt(
                self,
                "Layered Structure",
                "Number of layers:",
                2,
                2,
                20,
            )

            if not ok:
                return

            files = []

            for index in range(
                count
            ):

                path, _ = QFileDialog.getOpenFileName(
                    self,
                    f"Select Layer {index + 1}",
                    "",
                    (
                        "Crystal structures "
                        "(*.cif *.vasp *.poscar *.xsf *.xyz);;"
                        "All files (*)"
                    ),
                )

                if not path:

                    return

                files.append(
                    path
                )

            distance, ok = QInputDialog.getDouble(
                self,
                "Layered Structure",
                "Interlayer distance (Å):",
                3.4,
                0.5,
                20.0,
                3,
            )

            if not ok:
                return

            stacking, ok = QInputDialog.getItem(
                self,
                "Layered Structure",
                "Stacking:",
                [
                    "AA",
                    "AB",
                ],
                0,
                False,
            )

            if not ok:
                return

            atoms = create_layered_structure(
                files,
                interlayer_distance=distance,
                stacking=stacking,
            )

            self._set_generated_structure(
                atoms,
                (
                    f"{count}-layer structure generated"
                ),
            )

        except Exception as error:

            QMessageBox.critical(
                self,
                "Layered Structure Failed",
                str(error),
            )

    # ============================================================
    # Active structure
    # ============================================================

    def _get_active_structure(
        self,
    ):

        for name in (
            "atoms",
            "structure",
            "_structure",
        ):

            if hasattr(
                self,
                name,
            ):

                value = getattr(
                    self,
                    name,
                )

                if value is not None:

                    return value

        raise RuntimeError(
            "No structure is currently loaded."
        )
