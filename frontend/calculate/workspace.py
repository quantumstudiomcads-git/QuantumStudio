"""
Quantum Studio — Calculate Workspace

The Calculate workspace reads the active structure from the shared
Project object, allows calculation selection from the frontend catalog,
and communicates with the Quantum Studio backend through the API.

The workspace does not modify the structure.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from frontend.calculations.catalog import CALCULATIONS
from frontend.services.calculation_service import CalculationService


class CalculateWorkspace(QWidget):

    selection_changed = Signal(list)

    def __init__(
        self,
        project,
        parent=None,
    ):

        super().__init__(parent)

        self.project = project
        self.calculation_service = CalculationService(
            CALCULATIONS
        )

        self.selected_ids = []

        self.execution_plan = None

        self._build_ui()
        self._apply_style()
        self._populate_categories()
        self._populate_calculations()


    # ============================================================
    # QUANTUM STUDIO — CALCULATE WORKSPACE DARK THEME
    # ============================================================

    def _apply_style(self):

        self.setStyleSheet(
            """
            CalculateWorkspace {
                background: #111318;
                color: #E8EAF0;
            }

            QFrame#calculationPanel {
                background: #17191F;
                border: 1px solid #292C34;
                border-radius: 8px;
            }

            QLineEdit {
                background: #111318;
                color: #E8EAF0;
                border: 1px solid #30343D;
                border-radius: 6px;
                padding: 7px 10px;
                selection-background-color: #2A2E38;
            }

            QLineEdit:focus {
                border: 1px solid #4B5360;
            }

            QLineEdit::placeholder {
                color: #777D89;
            }

            QComboBox {
                background: #111318;
                color: #E8EAF0;
                border: 1px solid #30343D;
                border-radius: 6px;
                padding: 7px 10px;
                min-height: 18px;
            }

            QComboBox:hover {
                background: #181B21;
                border-color: #414753;
            }

            QComboBox QAbstractItemView {
                background: #17191F;
                color: #E8EAF0;
                border: 1px solid #30343D;
                selection-background-color: #2A2E38;
                selection-color: #FFFFFF;
                outline: none;
            }

            QListWidget {
                background: #111318;
                color: #C9CDD5;
                border: 1px solid #292C34;
                border-radius: 7px;
                padding: 4px;
            }

            QListWidget::item {
                background: transparent;
                color: #C9CDD5;
                padding: 7px 8px;
                border-radius: 5px;
            }

            QListWidget::item:hover {
                background: #22252D;
                color: #FFFFFF;
            }

            QListWidget::item:selected {
                background: #2A2E38;
                color: #FFFFFF;
            }

            QCheckBox {
                color: #C9CDD5;
                spacing: 7px;
            }

            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                background: #111318;
                border: 1px solid #555C68;
                border-radius: 3px;
            }

            QCheckBox::indicator:hover {
                border-color: #89909C;
            }

            QCheckBox::indicator:checked {
                background: #3A4655;
                border-color: #657182;
            }

            QPushButton {
                background: #252932;
                color: #D9DCE3;
                border: none;
                border-radius: 6px;
                padding: 8px 12px;
            }

            QPushButton:hover {
                background: #303540;
                color: #FFFFFF;
            }

            QPushButton:pressed {
                background: #1D2027;
            }

            QPushButton:disabled {
                background: #191B20;
                color: #555A64;
            }

            QPushButton#compileButton {
                background: #2A2E36;
                border: 1px solid #3A404B;
                color: #E0E3E8;
            }

            QPushButton#compileButton:hover {
                background: #353B46;
            }

            QPushButton#executeButton {
                background: #2D3744;
                border: 1px solid #435064;
                color: #F2F3F5;
                font-weight: 600;
            }

            QPushButton#executeButton:hover {
                background: #374353;
            }

            QFrame#executionPreview {
                background: #111318;
                border: 1px solid #292C34;
                border-radius: 7px;
            }

            QLabel#calculateTitle {
                color: #F2F3F5;
                font-size: 16px;
                font-weight: 600;
            }

            QLabel#calculateSubtitle,
            QLabel#structureSummary,
            QLabel#catalogCount,
            QLabel#selectedCount,
            QLabel#previewText {
                color: #777D89;
                font-size: 11px;
            }

            QLabel#panelTitle,
            QLabel#previewTitle {
                color: #E0E3E8;
                font-size: 11px;
                font-weight: 600;
            }

            QSplitter::handle {
                background: #242832;
                width: 1px;
            }
            """
        )


    # ============================================================
    # UI
    # ============================================================

    def _build_ui(self):

        root = QVBoxLayout(self)

        root.setContentsMargins(
            24,
            20,
            24,
            20,
        )

        root.setSpacing(14)

        # --------------------------------------------------------
        # Header
        # --------------------------------------------------------

        header = QHBoxLayout()

        title_box = QVBoxLayout()

        title = QLabel(
            "Calculate"
        )

        title.setObjectName(
            "calculateTitle"
        )

        subtitle = QLabel(
            "Select calculations, compile the workflow, and execute."
        )

        subtitle.setObjectName(
            "calculateSubtitle"
        )

        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        header.addLayout(title_box)

        header.addStretch()

        self.structure_label = QLabel()

        self.structure_label.setObjectName(
            "structureSummary"
        )

        self.structure_label.setAlignment(
            Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignVCenter
        )

        header.addWidget(
            self.structure_label
        )

        root.addLayout(header)

        # --------------------------------------------------------
        # Main splitter
        # --------------------------------------------------------

        splitter = QSplitter(
            Qt.Orientation.Horizontal
        )

        splitter.setChildrenCollapsible(
            False
        )

        # ========================================================
        # LEFT — CATALOG
        # ========================================================

        catalog_panel = QFrame()

        catalog_panel.setObjectName(
            "calculationPanel"
        )

        catalog_layout = QVBoxLayout(
            catalog_panel
        )

        catalog_layout.setContentsMargins(
            16,
            16,
            16,
            16,
        )

        catalog_layout.setSpacing(10)

        catalog_header = QLabel(
            "Calculation Catalog"
        )

        catalog_header.setObjectName(
            "panelTitle"
        )

        catalog_layout.addWidget(
            catalog_header
        )

        controls = QHBoxLayout()

        self.search = QLineEdit()

        self.search.setPlaceholderText(
            "Search calculations..."
        )

        self.search.textChanged.connect(
            self._populate_calculations
        )

        self.category_combo = QComboBox()

        self.category_combo.currentTextChanged.connect(
            self._populate_calculations
        )

        controls.addWidget(
            self.search,
            1,
        )

        controls.addWidget(
            self.category_combo
        )

        catalog_layout.addLayout(
            controls
        )

        self.calculation_list = QListWidget()

        self.calculation_list.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection
        )

        self.calculation_list.itemChanged.connect(
            self._calculation_item_changed
        )

        catalog_layout.addWidget(
            self.calculation_list,
            1,
        )

        # ========================================================
        # RIGHT — WORKFLOW
        # ========================================================

        selection_panel = QFrame()

        selection_panel.setObjectName(
            "calculationPanel"
        )

        selection_panel.setMinimumWidth(
            340
        )

        selection_layout = QVBoxLayout(
            selection_panel
        )

        selection_layout.setContentsMargins(
            16,
            16,
            16,
            16,
        )

        selection_layout.setSpacing(10)

        selected_header = QHBoxLayout()

        selected_title = QLabel(
            "Selected"
        )

        selected_title.setObjectName(
            "panelTitle"
        )

        self.selected_count = QLabel(
            "0 calculations"
        )

        self.selected_count.setObjectName(
            "selectedCount"
        )

        selected_header.addWidget(
            selected_title
        )

        selected_header.addStretch()

        selected_header.addWidget(
            self.selected_count
        )

        selection_layout.addLayout(
            selected_header
        )

        self.selected_list = QListWidget()

        self.selected_list.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection
        )

        selection_layout.addWidget(
            self.selected_list,
            1,
        )

        clear_button = QPushButton(
            "Clear Selection"
        )

        clear_button.clicked.connect(
            self._clear_selection
        )

        selection_layout.addWidget(
            clear_button
        )

        # --------------------------------------------------------
        # Execution preview
        # --------------------------------------------------------

        preview = QFrame()

        preview.setObjectName(
            "executionPreview"
        )

        preview_layout = QVBoxLayout(
            preview
        )

        preview_layout.setContentsMargins(
            12,
            12,
            12,
            12,
        )

        preview_title = QLabel(
            "Execution Plan"
        )

        preview_title.setObjectName(
            "previewTitle"
        )

        self.execution_preview = QLabel(
            "Select one or more calculations."
        )

        self.execution_preview.setWordWrap(
            True
        )

        self.execution_preview.setObjectName(
            "previewText"
        )

        preview_layout.addWidget(
            preview_title
        )

        preview_layout.addWidget(
            self.execution_preview
        )

        selection_layout.addWidget(
            preview
        )

        splitter.addWidget(
            catalog_panel
        )

        splitter.addWidget(
            selection_panel
        )

        splitter.setSizes(
            [900, 360]
        )

        root.addWidget(
            splitter,
            1,
        )

        # --------------------------------------------------------
        # Footer
        # --------------------------------------------------------

        footer = QHBoxLayout()

        self.catalog_count = QLabel()

        self.catalog_count.setObjectName(
            "catalogCount"
        )

        footer.addWidget(
            self.catalog_count
        )

        footer.addStretch()

        self.compile_button = QPushButton(
            "Compile Workflow"
        )

        self.compile_button.setObjectName(
            "compileButton"
        )

        self.compile_button.setEnabled(
            False
        )

        self.compile_button.clicked.connect(
            self._compile_requested
        )

        footer.addWidget(
            self.compile_button
        )

        self.execute_button = QPushButton(
            "Execute Calculation"
        )

        self.execute_button.setObjectName(
            "executeButton"
        )

        self.execute_button.setEnabled(
            False
        )

        self.execute_button.clicked.connect(
            self._execute_requested
        )

        footer.addWidget(
            self.execute_button
        )

        root.addLayout(
            footer
        )

        self._refresh_structure_summary()

    # ============================================================
    # CATEGORY / CATALOG
    # ============================================================

    def _populate_categories(self):

        categories = sorted(
            {
                calculation.category
                for calculation in CALCULATIONS
            }
        )

        self.category_combo.blockSignals(
            True
        )

        self.category_combo.clear()

        self.category_combo.addItem(
            "All Categories"
        )

        for category in categories:

            self.category_combo.addItem(
                category
            )

        self.category_combo.blockSignals(
            False
        )

    def _populate_calculations(self):

        query = (
            self.search.text()
            .strip()
            .lower()
        )

        category = (
            self.category_combo.currentText()
        )

        self.calculation_list.blockSignals(
            True
        )

        self.calculation_list.clear()

        filtered = []

        for calculation in CALCULATIONS:

            if (
                category != "All Categories"
                and calculation.category != category
            ):
                continue

            searchable = " ".join(
                [
                    calculation.id,
                    calculation.name,
                    calculation.category,
                ]
            ).lower()

            if query and query not in searchable:
                continue

            filtered.append(
                calculation
            )

        for calculation in filtered:

            item = QListWidgetItem(
                calculation.name
            )

            item.setData(
                Qt.ItemDataRole.UserRole,
                calculation.id,
            )

            item.setToolTip(
                f"{calculation.name}\n"
                f"{calculation.category}\n"
                f"Status: {calculation.status}"
            )

            item.setFlags(
                item.flags()
                | Qt.ItemFlag.ItemIsUserCheckable
            )

            if calculation.id in self.selected_ids:

                item.setCheckState(
                    Qt.CheckState.Checked
                )

            else:

                item.setCheckState(
                    Qt.CheckState.Unchecked
                )

            self.calculation_list.addItem(
                item
            )

        self.calculation_list.blockSignals(
            False
        )

        self.catalog_count.setText(
            f"{len(filtered)} calculations shown"
        )

    # ============================================================
    # SELECTION
    # ============================================================

    def _calculation_item_changed(
        self,
        item,
    ):

        calculation_id = item.data(
            Qt.ItemDataRole.UserRole
        )

        if item.checkState() == Qt.CheckState.Checked:

            if calculation_id not in self.selected_ids:

                self.selected_ids.append(
                    calculation_id
                )

        else:

            if calculation_id in self.selected_ids:

                self.selected_ids.remove(
                    calculation_id
                )

        # A changed selection invalidates the old plan.
        self.execution_plan = None

        self.execute_button.setEnabled(
            False
        )

        self._refresh_selection()

    def _refresh_selection(self):

        self.selected_list.clear()

        calculation_map = {
            calculation.id: calculation
            for calculation in CALCULATIONS
        }

        for calculation_id in self.selected_ids:

            calculation = calculation_map.get(
                calculation_id
            )

            if calculation is None:
                continue

            item = QListWidgetItem(
                calculation.name
            )

            item.setData(
                Qt.ItemDataRole.UserRole,
                calculation_id,
            )

            item.setToolTip(
                f"{calculation.category}\n"
                f"Status: {calculation.status}"
            )

            self.selected_list.addItem(
                item
            )

        count = len(
            self.selected_ids
        )

        label = (
            "calculation"
            if count == 1
            else "calculations"
        )

        self.selected_count.setText(
            f"{count} {label}"
        )

        self.compile_button.setEnabled(
            count > 0
        )

        if count == 0:

            self.execution_preview.setText(
                "Select one or more calculations."
            )

        else:

            names = []

            for calculation_id in self.selected_ids:

                calculation = calculation_map.get(
                    calculation_id
                )

                if calculation:

                    names.append(
                        calculation.name
                    )

            self.execution_preview.setText(
                "Selected calculations:\n\n"
                + "\n".join(
                    f"• {name}"
                    for name in names
                )
                + "\n\nCompile the workflow to resolve "
                  "dependencies and parameters."
            )

        self.selection_changed.emit(
            list(self.selected_ids)
        )

    def _clear_selection(self):

        self.selected_ids.clear()

        self.execution_plan = None

        self.execute_button.setEnabled(
            False
        )

        self._populate_calculations()

        self._refresh_selection()

    # ============================================================
    # STRUCTURE SERIALIZATION
    # ============================================================

    def _get_structure_payload(self):

        structure = self.project.get_structure()

        atoms = []

        for atom in structure.atoms:

            atoms.append(
                {
                    "element": atom.element,

                    "position": [
                        atom.x,
                        atom.y,
                        atom.z,
                    ],
                }
            )

        return {
            "name": structure.name,

            "lattice": [
                list(vector)
                for vector in structure.cell
            ],

            "atoms": atoms,
        }

    # ============================================================
    # STRUCTURE
    # ============================================================

    def _refresh_structure_summary(self):

        try:

            structure = self.project.get_structure()

            atom_count = len(
                structure.atoms
            )

            if atom_count == 0:

                self.structure_label.setText(
                    "No active structure"
                )

            else:

                elements = sorted(
                    {
                        atom.element
                        for atom in structure.atoms
                    }
                )

                self.structure_label.setText(
                    f"{structure.name}  •  "
                    f"{atom_count} atoms  •  "
                    f"{', '.join(elements)}"
                )

        except Exception:

            self.structure_label.setText(
                "Structure unavailable"
            )

    def refresh(self):

        self._refresh_structure_summary()

    # ============================================================
    # PUBLIC API
    # ============================================================

    def selected_calculations(self):

        return list(
            self.selected_ids
        )

    # ============================================================
    # COMPILE
    # ============================================================

    def _get_calculation_map(self):

        return self.calculation_service.get_calculation_map()


    def _resolve_calculation_order(self):

        return self.calculation_service.resolve_calculation_order(
            self.selected_ids
        )


    def _validate_structure_for_workflow(self):

        return self.calculation_service.validate_structure(
            self.project
        )


    def _compile_requested(self):

        if not self.selected_ids:

            return

        try:

            self.compile_button.setEnabled(False)

            self.compile_button.setText(
                "Compiling..."
            )

            # ----------------------------------------------------
            # 1. Validate active structure
            # ----------------------------------------------------

            structure, summary = (
                self._validate_structure_for_workflow()
            )

            # ----------------------------------------------------
            # 2. Resolve dependencies locally
            # ----------------------------------------------------

            resolved = (
                self._resolve_calculation_order()
            )

            # ----------------------------------------------------
            # 3. Create local execution plan
            # ----------------------------------------------------

            self.execution_plan = {
                "structure": {
                    "name": summary.name,
                    "atom_count": summary.atom_count,
                },

                "selected": list(
                    self.selected_ids
                ),

                "resolved": resolved,

                "parameters": {},

                "execution_target": "local",

                "compiled": True,
            }

            # ----------------------------------------------------
            # 4. Display execution plan
            # ----------------------------------------------------

            self._display_execution_plan()

            # ----------------------------------------------------
            # 5. Enable execution
            # ----------------------------------------------------

            self.execute_button.setEnabled(True)


        except Exception as error:

            self.execution_plan = None

            self.execute_button.setEnabled(False)

            QMessageBox.critical(
                self,
                "Compilation Failed",
                str(error),
            )


        finally:

            self.compile_button.setText(
                "Compile Workflow"
            )

            self.compile_button.setEnabled(
                bool(self.selected_ids)
            )


    def _display_execution_plan(self):

        if self.execution_plan is None:

            return

        resolved = self.execution_plan.get(
            "resolved",
            [],
        )

        calculation_map = (
            self._get_calculation_map()
        )

        structure_info = (
            self.execution_plan.get(
                "structure",
                {},
            )
        )

        structure_name = (
            structure_info.get(
                "name",
                "Active Structure",
            )
        )

        atom_count = (
            structure_info.get(
                "atom_count",
                0,
            )
        )

        lines = [
            f"Structure: {structure_name}",
            f"Atoms: {atom_count}",
            "",
            "Resolved execution sequence:",
            "",
        ]

        for index, calculation_id in enumerate(
            resolved,
            start=1,
        ):

            calculation = calculation_map.get(
                calculation_id
            )

            if calculation is not None:

                name = calculation.name

            else:

                name = calculation_id

            lines.append(
                f"{index}. {name}"
            )

        lines.extend(
            [
                "",
                "✓ Workflow compiled",
                "✓ Dependencies resolved",
                "✓ Active structure validated",
                "✓ Ready for execution",
            ]
        )

        self.execution_preview.setText(
            "\n".join(lines)
        )


    # ============================================================
    # EXECUTE
    # ============================================================

    def _execute_requested(self):

        if self.execution_plan is None:

            QMessageBox.warning(
                self,
                "No Compiled Workflow",
                "Compile the calculation workflow before "
                "attempting execution.",
            )

            return

        resolved = self.execution_plan.get(
            "resolved",
            [],
        )

        calculation_map = (
            self._get_calculation_map()
        )

        lines = []

        for index, calculation_id in enumerate(
            resolved,
            start=1,
        ):

            calculation = calculation_map.get(
                calculation_id
            )

            name = (
                calculation.name
                if calculation is not None
                else calculation_id
            )

            lines.append(
                f"{index}. {name}"
            )

        QMessageBox.information(
            self,
            "Execution Plan Ready",
            "The workflow has been compiled successfully.\n\n"
            "Execution sequence:\n\n"
            + "\n".join(lines)
            + "\n\n"
              "The workflow compiler is operating locally.\n"
              "The QE execution backend will be connected "
              "as a separate execution layer.",
        )

