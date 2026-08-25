"""
Quantum Studio — Calculate Workspace

The Calculate workspace reads the active structure from the shared
Project object, allows calculation selection from the frontend catalog,
and communicates with the Quantum Studio backend through the API.

The workspace does not modify the structure.
"""

import json

from PySide6.QtCore import Qt, QTimer, Signal
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
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFileDialog,
    QPlainTextEdit,
    QWidget,
    QMenu,
    QToolButton,
    QSpinBox,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
)

from frontend.calculations.catalog import CALCULATIONS
from frontend.services.calculation_service import CalculationService
from frontend.services.result_service import ResultService
from frontend.calculate.parameter_session import PRESETS, descriptors, parse_value, preset_parameters
from frontend.calculate.functional_pseudo_dialog import FunctionalPseudoDialog
from frontend.calculate.band_path_dialog import BandPathDialog
from frontend.calculate.results_dialog import ResultsDialog
from frontend.calculate.typed_parameter_controls import control_value, make_control
from backend.execution import ExecutionStore, LocalExecutionManager, LocalExecutionService, LocalToolConfiguration, RecoveryState, available_logical_cpus


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
        # The service owns the catalog/registry boundary; Qt sees descriptors,
        # never backend registry internals.
        self.catalog_descriptors = self.calculation_service.get_calculation_descriptors()
        self.catalog_descriptor_map = {
            descriptor.id: descriptor
            for descriptor in self.catalog_descriptors
        }
        self.selected_support_error = ""

        self.selected_ids = []

        self.execution_plan = None
        self.calculation_request = None
        self.current_structure_summary = None
        self._local_execution_service = None
        self._active_execution = None
        self.local_tool_configuration = LocalToolConfiguration()
        self.result_service = ResultService()

        self._build_ui()
        self._apply_style()
        self._populate_categories()
        self._populate_calculations()
        self._refresh_configured_calculations()


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

            QLineEdit, QSpinBox {
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

            QToolButton {
                background: #252932;
                color: #D9DCE3;
                border: none;
                border-radius: 6px;
                padding: 8px 12px;
            }

            QMenu {
                background: #17191F;
                color: #E8EAF0;
                border: 1px solid #30343D;
            }

            QMenu::item:selected { background: #2A2E38; }

            QToolTip {
                background: #17191F;
                color: #E8EAF0;
                border: 1px solid #3A4655;
                padding: 5px 7px;
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

        self.catalog_create_button = QPushButton("Create Selected", catalog_panel)
        self.catalog_create_button.setEnabled(False)
        self.catalog_create_button.clicked.connect(self._create_calculation_requested)
        catalog_layout.addWidget(self.catalog_create_button)

        # ========================================================
        # RIGHT — WORKFLOW
        # ========================================================

        selection_panel = QFrame()

        selection_panel.setObjectName(
            "calculationPanel"
        )

        selection_panel.setMinimumWidth(360)
        selection_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

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

        configured_header = QLabel("Configured Calculations")
        configured_header.setObjectName("panelTitle")
        selection_layout.addWidget(configured_header)
        self.configured_list = QListWidget()
        self.configured_list.setMaximumHeight(140)
        self.configured_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.configured_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.configured_list.customContextMenuRequested.connect(self._configured_context_menu)
        self.configured_list.itemDoubleClicked.connect(lambda item: self._configure_configured_item(item))
        self.configured_list.itemSelectionChanged.connect(self._configured_selection_changed)
        selection_layout.addWidget(self.configured_list)
        self.request_name = QLineEdit()
        self.request_name.setPlaceholderText("Calculation name")
        # Serialized request parameters remain JSON-compatible internally, but are not
        # part of the normal user flow.  Scientific editing happens in typed controls.
        self.parameters_input = QLineEdit()
        self.parameters_input.setVisible(False)
        # Keep the primary configuration action visible; infrequent mutations live
        # in a compact menu so their full labels cannot be clipped by the column.
        self.save_request_button = QPushButton("Save Parameters")
        self.duplicate_request_button = QPushButton("Duplicate")
        self.remove_request_button = QPushButton("Remove")
        self.update_structure_button = QPushButton("Update From Current Structure")
        for button in (self.save_request_button, self.duplicate_request_button, self.remove_request_button, self.update_structure_button):
            button.setEnabled(False)
            button.setVisible(False)
        selection_layout.addWidget(self.request_name)
        self.edit_parameters_button = QPushButton("Configure Parameters…")
        self.edit_parameters_button.clicked.connect(self._configure_parameters)
        selection_layout.addWidget(self.edit_parameters_button)
        self.request_more_button = QToolButton(selection_panel)
        self.request_more_button.setText("More actions ▾")
        self.request_more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        request_menu = QMenu(self.request_more_button)
        self._request_save_action = request_menu.addAction("Save Parameters", self.save_request_button.click)
        self._request_duplicate_action = request_menu.addAction("Duplicate", self.duplicate_request_button.click)
        self._request_remove_action = request_menu.addAction("Remove", self.remove_request_button.click)
        self._request_update_action = request_menu.addAction("Update From Current Structure", self.update_structure_button.click)
        self.request_more_button.setMenu(request_menu)
        selection_layout.addWidget(self.request_more_button)
        self.save_request_button.clicked.connect(self._save_selected_request)
        self.duplicate_request_button.clicked.connect(self._duplicate_selected_request)
        self.remove_request_button.clicked.connect(self._remove_selected_request)
        self.update_structure_button.clicked.connect(self._update_selected_request_structure)

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
        # Local execution resources — runtime-only, never request state.
        # --------------------------------------------------------
        resource_frame = QFrame()
        resource_frame.setObjectName("executionPreview")
        resource_layout = QVBoxLayout(resource_frame)
        resource_layout.setContentsMargins(12, 10, 12, 10)
        resource_head = QHBoxLayout(); resource_head.addWidget(QLabel("Execution", resource_frame)); resource_head.addStretch(); resource_layout.addLayout(resource_head)
        resources = QFormLayout()
        self.cpu_cores_spin = QSpinBox(resource_frame)
        self.available_cpu_count = max(1, available_logical_cpus())
        resources.addRow("Target", QLabel("Local Machine", resource_frame))
        core_row = QHBoxLayout()
        core_row.addWidget(self.cpu_cores_spin)
        self.available_cpu_label = QLabel(resource_frame)
        self.available_cpu_label.setToolTip("Logical CPUs available to this process.")
        core_row.addWidget(self.available_cpu_label)
        core_row.addStretch()
        resources.addRow("CPU cores", core_row)
        resource_layout.addLayout(resources)
        self.execution_advanced_button = QPushButton("▶ Advanced Execution Settings", resource_frame); self.execution_advanced_button.setCheckable(True); resource_layout.addWidget(self.execution_advanced_button)
        self.execution_advanced_panel = QWidget(resource_frame); advanced = QFormLayout(self.execution_advanced_panel); self.mpi_launcher_input = QLineEdit("Auto", self.execution_advanced_panel); self.mpi_launcher_input.setPlaceholderText("Auto or absolute launcher path"); self.omp_threads_spin = QSpinBox(self.execution_advanced_panel); self.omp_threads_spin.setRange(1, self.available_cpu_count); self.omp_threads_spin.setValue(1); advanced.addRow("MPI launcher", self.mpi_launcher_input); advanced.addRow("OpenMP threads", self.omp_threads_spin); self.execution_advanced_panel.setVisible(False); resource_layout.addWidget(self.execution_advanced_panel)
        def toggle_execution_advanced(visible): self.execution_advanced_panel.setVisible(visible); self.execution_advanced_button.setText("▼ Advanced Execution Settings" if visible else "▶ Advanced Execution Settings")
        self.execution_advanced_button.toggled.connect(toggle_execution_advanced); self.cpu_cores_spin.valueChanged.connect(self._sync_resource_configuration); self.omp_threads_spin.valueChanged.connect(self._sync_resource_configuration); self.mpi_launcher_input.editingFinished.connect(self._sync_resource_configuration)
        self._refresh_resource_bounds()
        selection_layout.addWidget(resource_frame)

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

        selection_scroll = QScrollArea()
        selection_scroll.setObjectName("selectionScroll")
        selection_scroll.setWidgetResizable(True)
        selection_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        selection_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        selection_scroll.setMinimumWidth(360)
        selection_scroll.setWidget(selection_panel)
        self.selection_scroll = selection_scroll
        splitter.addWidget(selection_scroll)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([max(500, self.width() - 420), 380])

        root.addWidget(
            splitter,
            1,
        )

        # --------------------------------------------------------
        # Footer
        # --------------------------------------------------------

        footer = QHBoxLayout()
        self.workflow_status = QLabel("Status: Select a calculation")
        self.workflow_status.setObjectName("catalogCount")
        footer.addWidget(self.workflow_status)
        self.catalog_count = QLabel()
        self.catalog_count.setObjectName("catalogCount")
        footer.addWidget(self.catalog_count)
        footer.addStretch()

        # Secondary actions retain their existing handlers/enabling state but live
        # in one contextual menu instead of permanently crowding the action bar.
        self.create_button = QPushButton("Create Calculation", self); self.create_button.setEnabled(False); self.create_button.clicked.connect(self._create_calculation_requested)
        self.compile_button = QPushButton("Compile Workflow", self); self.compile_button.setEnabled(False); self.compile_button.clicked.connect(self._compile_requested)
        self.preview_qe_button = QPushButton("Preview QE Inputs", self); self.preview_qe_button.setEnabled(False); self.preview_qe_button.clicked.connect(self._preview_qe_inputs)
        self.configure_tools_button = QPushButton("Local Tools…", self); self.configure_tools_button.clicked.connect(self._configure_local_tools)
        self.view_results_button = QPushButton("Results…", self); self.view_results_button.clicked.connect(self._view_results)
        for secondary in (self.create_button, self.compile_button, self.preview_qe_button, self.configure_tools_button, self.view_results_button):
            secondary.setVisible(False)
        self.more_button = QToolButton(self); self.more_button.setText("More ▾"); self.more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu=QMenu(self.more_button); self._more_create_action=menu.addAction("Create Calculation",self.create_button.click); menu.addSeparator(); self._more_preview_action=menu.addAction("Preview QE Inputs",self.preview_qe_button.click); menu.addAction("Local Tools…",self.configure_tools_button.click); menu.addAction("Results…",self.view_results_button.click); self.more_button.setMenu(menu); footer.addWidget(self.more_button)

        self.compile_button.setVisible(True)
        self.compile_button.setText("Compile")
        self.compile_button.setObjectName("compileButton")
        footer.addWidget(self.compile_button)
        self.generate_qe_button = QPushButton("Generate", self); self.generate_qe_button.setObjectName("compileButton"); self.generate_qe_button.setEnabled(False); self.generate_qe_button.clicked.connect(self._generate_qe_inputs); footer.addWidget(self.generate_qe_button)
        self.execute_button = QPushButton("Run", self); self.execute_button.setObjectName("executeButton"); self.execute_button.setEnabled(False); self.execute_button.clicked.connect(self._execute_requested); footer.addWidget(self.execute_button)

        root.addLayout(footer)

        self._refresh_structure_summary()

    # ============================================================
    # CATEGORY / CATALOG
    # ============================================================

    def _populate_categories(self):

        categories = sorted(
            {
                descriptor.info.category
                for descriptor in self.catalog_descriptors
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

        for descriptor in self.catalog_descriptors:
            calculation = descriptor.info

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
                    descriptor.status_label,
                ]
            ).lower()

            if query and query not in searchable:
                continue

            filtered.append(descriptor)

        for descriptor in filtered:
            calculation = descriptor.info
            label = calculation.name
            if not descriptor.backend_supported:
                label += f" [{descriptor.status_label}]"
            item = QListWidgetItem(label)

            item.setData(
                Qt.ItemDataRole.UserRole,
                calculation.id,
            )

            dependencies = ", ".join(descriptor.dependencies) or "none"
            item.setToolTip(
                f"{calculation.name}\n"
                f"{calculation.category}\n"
                f"Execution support: {descriptor.status_label}\n"
                f"Backend dependencies: {dependencies}"
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

        # A changed selection invalidates the old reproducible request and plan.
        self.execution_plan = None
        self.calculation_request = None

        self.execute_button.setEnabled(
            False
        )

        self._refresh_selection()

    def _refresh_selection(self):

        self.selected_list.clear()

        descriptor_map = self.catalog_descriptor_map
        calculation_map = {
            calculation_id: descriptor.info
            for calculation_id, descriptor in descriptor_map.items()
        }

        for calculation_id in self.selected_ids:
            descriptor = descriptor_map.get(calculation_id)
            calculation = calculation_map.get(calculation_id)
            if calculation is None or descriptor is None:
                continue

            label = calculation.name
            if not descriptor.backend_supported:
                label += f" [{descriptor.status_label}]"
            item = QListWidgetItem(label)

            item.setData(
                Qt.ItemDataRole.UserRole,
                calculation_id,
            )

            item.setToolTip(
                f"{calculation.category}\n"
                f"Execution support: {descriptor.status_label}"
            )

            self.selected_list.addItem(item)

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

        self._update_compile_availability()

        if count == 0:

            self.execution_preview.setText(
                "Select one or more calculations."
            )

        else:
            names = []
            for calculation_id in self.selected_ids:
                calculation = calculation_map.get(calculation_id)
                if calculation:
                    names.append(calculation.name)
            message = (
                "Selected calculations:\n\n"
                + "\n".join(f"• {name}" for name in names)
            )
            if self.selected_support_error:
                message += "\n\nCannot prepare this selection:\n" + self.selected_support_error
            else:
                message += "\n\nCompile the workflow to resolve dependencies and parameters."
            self.execution_preview.setText(message)

        self.selection_changed.emit(
            list(self.selected_ids)
        )

    def _clear_selection(self):

        self.selected_ids.clear()

        self.execution_plan = None
        self.calculation_request = None

        self.execute_button.setEnabled(
            False
        )

        self._populate_calculations()

        self._refresh_selection()

    # ============================================================
    # CANONICAL PROJECT STRUCTURE
    # ============================================================

    def _refresh_structure_summary(self):
        """Read the current Structure only through Project's public API."""
        summary = self.calculation_service.summarize_structure(self.project)
        self.current_structure_summary = summary
        if not summary.valid:
            self.structure_label.setText("No active structure.\nCreate or import a structure in Builder first.")
        else:
            pbc = ", ".join(axis for axis, enabled in zip(("X", "Y", "Z"), summary.periodic) if enabled) or "None"
            dimensionality = "unknown" if summary.dimensionality is None else f"{summary.dimensionality}D"
            species = ", ".join(summary.species) or "unavailable"
            cell = "valid" if summary.cell_valid else "unavailable"
            self.structure_label.setText(
                f"Current Structure\n{summary.name}\nAtoms: {summary.atom_count}  •  Species: {species}\n"
                f"PBC: {pbc}  •  Cell: {cell}  •  {dimensionality}"
            )
        self._update_compile_availability()
        return summary

    def _update_compile_availability(self):
        self.selected_support_error = ""
        supported = bool(self.selected_ids)
        if supported:
            try:
                self.calculation_service.validate_selected_calculations(self.selected_ids)
            except Exception as error:
                supported = False
                self.selected_support_error = str(error)
        structure_ready = bool(getattr(self.current_structure_summary, "valid", False))
        request_ready = self._selected_configured_request_id() is not None and self.calculation_request is not None
        enabled = supported and structure_ready
        if hasattr(self, "catalog_create_button"):
            self.catalog_create_button.setEnabled(enabled)
        if hasattr(self, "compile_button"):
            compile_ready = request_ready and not self._workflow_compiled
            self.compile_button.setEnabled(compile_ready)
        if hasattr(self, "create_button"):
            self.create_button.setEnabled(enabled)
            self._more_create_action.setEnabled(enabled)
        if hasattr(self, "preview_qe_button"):
            qe_available = bool(self.execution_plan and self.calculation_request)
            if qe_available:
                support = self.calculation_service.qe_input_support(self.execution_plan.resolved_calculations)
                qe_available = self.calculation_service.workflow_input_available(self.execution_plan)
            self.preview_qe_button.setEnabled(qe_available)
            self._more_preview_action.setEnabled(qe_available)
            self.generate_qe_button.setEnabled(qe_available and self.execution_plan is not None and self._workflow_compiled and not self._workflow_generated)
            self.workflow_status.setText("Status: Ready to generate" if qe_available else "Status: Configure and compile the selected calculation")

    def refresh(self):
        """Refresh derived display state; existing request snapshots are intentionally unchanged."""
        self._refresh_resource_bounds()
        self._refresh_structure_summary()
        self._refresh_configured_calculations()

    # ============================================================
    # PERSISTENT CONFIGURED REQUESTS
    # ============================================================

    def _selected_configured_request_id(self):
        item = self.configured_list.currentItem() if hasattr(self, "configured_list") else None
        return None if item is None else item.data(Qt.ItemDataRole.UserRole)

    def _set_configured_action_enabled(self, enabled):
        enabled = bool(enabled)
        for button in (self.save_request_button, self.duplicate_request_button, self.remove_request_button, self.update_structure_button):
            button.setEnabled(enabled)
        for action in (self._request_save_action, self._request_duplicate_action, self._request_remove_action, self._request_update_action):
            action.setEnabled(enabled)

    def _refresh_resource_bounds(self):
        """Reapply machine bounds and clamp remembered runtime-only values."""
        if not hasattr(self, "cpu_cores_spin"):
            return
        available = max(1, int(available_logical_cpus()))
        self.available_cpu_count = available
        remembered = max(1, int(getattr(self.local_tool_configuration, "cpu_cores", 1)))
        cores = min(remembered, available)
        self.cpu_cores_spin.setRange(1, available)
        self.cpu_cores_spin.setValue(cores)
        self.local_tool_configuration.cpu_cores = cores
        omp = min(max(1, int(getattr(self.local_tool_configuration, "omp_threads", 1))), available)
        self.omp_threads_spin.setRange(1, available)
        self.omp_threads_spin.setValue(omp)
        self.local_tool_configuration.omp_threads = omp
        self.available_cpu_label.setText(f"Available: {available}")

    def _refresh_configured_calculations(self, selected_id=None):
        if not hasattr(self, "configured_list"):
            return
        selected_id = self._selected_configured_request_id() if selected_id is None else selected_id
        self.configured_list.blockSignals(True)
        self.configured_list.clear()
        for request in self.project.get_calculations():
            try:
                prepared = self.calculation_service.prepare_persisted_request(request)
                status = "Ready for Plan"
                summary = prepared.summary
            except Exception:
                status = "Compile Error"
                summary = None
            atom_text = f"{summary.atom_count} atoms" if summary is not None else "saved snapshot"
            item = QListWidgetItem(request.name or request.calculation_id)
            item.setData(Qt.ItemDataRole.UserRole, request.id)
            item.setToolTip(f"{status}\nRequest ID: {request.id}")
            self.configured_list.addItem(item)
            if request.id == selected_id:
                self.configured_list.setCurrentItem(item)
        self.configured_list.blockSignals(False)
        self._configured_selection_changed()

    def _configured_context_menu(self, position):
        item = self.configured_list.itemAt(position)
        if item is None:
            return
        self.configured_list.setCurrentItem(item)
        menu = QMenu(self.configured_list)
        modify = menu.addAction("Modify / Configure…", lambda: self._configure_configured_item(item))
        menu.addAction("Duplicate", self._duplicate_selected_request)
        menu.addAction("Update From Current Structure", self._update_selected_request_structure)
        menu.addSeparator()
        delete = menu.addAction("Delete", self._remove_selected_request)
        modify.setEnabled(True); delete.setEnabled(True)
        menu.exec(self.configured_list.mapToGlobal(position))

    def _configure_configured_item(self, item):
        if item is not None:
            self.configured_list.setCurrentItem(item)
        self._configure_parameters()

    def _configured_selection_changed(self):
        request_id = self._selected_configured_request_id()
        request = self.project.get_calculation(request_id) if request_id else None
        self._set_configured_action_enabled(request is not None)
        if request is None:
            return
        self.request_name.setText(request.name)
        self.selected_ids = list(request.selected_calculations)
        self.parameters_input.setText(json.dumps(request.parameters, sort_keys=True))
        self._workflow_generated = False
        self._workflow_compiled = False
        try:
            self.calculation_request = self.calculation_service.prepare_persisted_request(request)
            # Keep the existing prepared-plan preview for compatibility, while exposing
            # Compile as the next explicit lifecycle action.
            self.execution_plan = self.calculation_service.compile_request(self.calculation_request)
            self._display_execution_plan()
            self.workflow_status.setText("Status: Ready to compile")
            self._update_compile_availability()
        except Exception as error:
            self.execution_plan = None
            self.execution_preview.setText(
                f"Configured request: {request.name or request.calculation_id}\n"
                f"Snapshot atoms: {len(request.structure.get('atoms', []))}\n\n"
                f"Compile Error: {error}"
            )

    def create_persistent_calculation(self, parameters=None, name=None):
        prepared = self.calculation_service.create_request(
            self.project, self.selected_ids, parameters=parameters, name=name,
        )
        self.project.add_calculation(prepared.backend_request)
        self.calculation_request = prepared
        self._refresh_configured_calculations(prepared.id)
        return prepared

    def _create_calculation_requested(self):
        try:
            prepared = self.create_persistent_calculation()
            self.configured_list.setCurrentRow(self.configured_list.count() - 1)
            return prepared
        except Exception as error:
            QMessageBox.warning(self, "Create Calculation", str(error))
            return None

    def _configure_parameters(self):
        if not self.selected_ids:
            request = self.project.get_calculation(self._selected_configured_request_id())
            if request is not None:
                self.selected_ids = list(request.selected_calculations)
        if not self.selected_ids:
            QMessageBox.information(self, "Parameters", "Select a generation-ready calculation first."); return
        dialog=QDialog(self); dialog.setWindowTitle("Scientific Parameters"); layout=QVBoxLayout(dialog)
        preset=QComboBox(dialog)
        for mode,label in (("FAST","Fast"),("INTERMEDIATE","Intermediate"),("PRECISE","Precise"),("CUSTOM","Custom")): preset.addItem(label,mode)
        existing=json.loads(self.parameters_input.text() or "{}")
        preset.setCurrentIndex(max(0,preset.findData(existing.get("accuracy_preset","INTERMEDIATE"))))
        layout.addWidget(QLabel("Accuracy preset")); layout.addWidget(preset)
        structure=(self.calculation_request.backend_request.structure if self.calculation_request is not None else self.project.get_structure().to_dict())
        species=tuple(dict.fromkeys(str(atom.get("element", "")) for atom in structure.get("atoms", ()) if atom.get("element")))
        scientific_state={key: existing[key] for key in ("xc_functional", "exx_fraction", "screening_parameter", "exx_q_mesh", "ace", "exxdiv_treatment", "pseudopotentials") if key in existing}
        configure_science=QPushButton("Configure XC & Pseudopotentials…", dialog)
        def edit_science():
            editor=FunctionalPseudoDialog({**existing, **scientific_state}, species, dialog)
            if editor.exec()==QDialog.DialogCode.Accepted: scientific_state.update(editor.values()); refresh()
        configure_science.clicked.connect(edit_science); layout.addWidget(configure_science)
        form=QFormLayout(); fields={}
        for item in descriptors(self.selected_ids):
            key=item["key"]; value=existing.get(key,item["default"])
            if key=="kpath":
                field=QPushButton("Choose Band Path…",dialog); field._band_path=list(value or [])
                def choose_path(_checked=False, button=field):
                    try:
                        editor = BandPathDialog(structure, button._band_path, dialog)
                        if editor.exec() == QDialog.DialogCode.Accepted:
                            button._band_path = editor.value()
                            button.setText("Band Path: " + " — ".join(point["label"] for point in button._band_path))
                            button.setToolTip("Selected band path: " + " — ".join(point["label"] for point in button._band_path))
                    except Exception as error:
                        QMessageBox.warning(dialog, "Band Path", str(error))
                field.clicked.connect(choose_path)
            else: field=make_control(key,value,dialog)
            field.setToolTip(item["key"]); fields[key]=field; form.addRow(item["label"]+(f" ({item['unit']})" if item["unit"] else ""),field)
        layout.addLayout(form)
        resolved=QTableWidget(dialog); resolved.setColumnCount(2); resolved.setHorizontalHeaderLabels(("Parameter", "Value")); resolved.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents); resolved.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch); resolved.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers); resolved.setMaximumHeight(180); layout.addWidget(QLabel("Resolved parameters (read-only)")); layout.addWidget(resolved)
        def values_from_fields():
            values={}
            for key,field in fields.items():
                values[key]=list(field._band_path) if key=="kpath" else control_value(key,field)
            return values
        def refresh():
            values=preset_parameters(self.selected_ids,preset.currentData(),values_from_fields()); values.update(scientific_state)
            resolved.setRowCount(0)
            for key, value in sorted(values.items()):
                row = resolved.rowCount(); resolved.insertRow(row)
                resolved.setItem(row, 0, QTableWidgetItem(str(key)))
                resolved.setItem(row, 1, QTableWidgetItem(json.dumps(value, sort_keys=True) if isinstance(value, (dict, list, tuple)) else str(value)))
        preset.currentIndexChanged.connect(refresh); refresh()
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel,dialog); buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
        dialog.resize(720,620)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            values=values_from_fields(); values.update(scientific_state)
            values["accuracy"]=PRESETS[preset.currentData()] if preset.currentData()!="CUSTOM" else "standard"; values["accuracy_preset"]=preset.currentData(); self.parameters_input.setText(json.dumps(values,sort_keys=True))
            request = self.project.get_calculation(self._selected_configured_request_id())
            if request is not None:
                try:
                    updated = self.calculation_service.update_request_parameters(request, values, name=self.request_name.text())
                    self.project.update_calculation(updated)
                    self._workflow_generated = False
                    self._workflow_compiled = False
                    self._refresh_configured_calculations(updated.id)
                    self.workflow_status.setText("Status: Parameters updated — ready to compile")
                except Exception as error:
                    QMessageBox.warning(self, "Save Calculation Parameters", str(error))

    def _save_selected_request(self):
        request = self.project.get_calculation(self._selected_configured_request_id())
        if request is None:
            return
        try:
            parameters = json.loads(self.parameters_input.text() or "{}")
            if not isinstance(parameters, dict):
                raise ValueError("Parameters must be a JSON object.")
            updated = self.calculation_service.update_request_parameters(request, parameters, name=self.request_name.text())
            self.project.update_calculation(updated)
            self._refresh_configured_calculations(updated.id)
        except Exception as error:
            QMessageBox.warning(self, "Save Calculation Parameters", str(error))

    def _duplicate_selected_request(self):
        request = self.project.get_calculation(self._selected_configured_request_id())
        if request is None:
            return
        try:
            duplicate = self.calculation_service.duplicate_request(request)
            self.project.add_calculation(duplicate)
            self._refresh_configured_calculations(duplicate.id)
        except Exception as error:
            QMessageBox.warning(self, "Duplicate Calculation", str(error))

    def _remove_selected_request(self):
        request_id = self._selected_configured_request_id()
        if request_id is not None:
            request = self.project.get_calculation(request_id)
            name = request.name if request is not None else request_id
            if QMessageBox.question(self, "Delete Calculation", f'Delete calculation "{name}"?\n\nThis removes it from the project.') != QMessageBox.StandardButton.Yes:
                return
            self.project.remove_calculation(request_id)
            self.calculation_request = None
            self.execution_plan = None
            self._workflow_generated = False
            self._workflow_compiled = False
            self._refresh_configured_calculations()
            self.execution_preview.setText("Select one or more calculations.")
            self.workflow_status.setText("Status: Calculation deleted")

    def _update_selected_request_structure(self):
        request = self.project.get_calculation(self._selected_configured_request_id())
        if request is None:
            return
        try:
            updated = self.calculation_service.update_request_from_project(request, self.project)
            self.project.update_calculation(updated)
            self._refresh_configured_calculations(updated.id)
        except Exception as error:
            QMessageBox.warning(self, "Update From Current Structure", str(error))

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


    def create_calculation_request(self, parameters=None, execution_target="local"):
        """Snapshot Project.structure through the service without mutating Project or Builder."""
        prepared = self.calculation_service.create_request(
            self.project, self.selected_ids, parameters=parameters, execution_target=execution_target,
        )
        self.calculation_request = prepared
        return prepared

    def prepare_workflow(self, parameters=None, execution_target="local"):
        prepared = self.create_calculation_request(parameters, execution_target)
        self.execution_plan = self.calculation_service.compile_request(prepared)
        return self.execution_plan

    def _compile_requested(self):
        if not self.selected_ids:
            return
        compiled = False
        try:
            self.compile_button.setEnabled(False)
            self.workflow_status.setText("Status: Compiling workflow…")
            if self.calculation_request is None:
                self.prepare_workflow()
            else:
                self.execution_plan = self.calculation_service.compile_request(self.calculation_request)
            self._display_execution_plan()
            self._workflow_compiled = True
            self._workflow_generated = False
            self.generate_qe_button.setEnabled(True)
            self.execute_button.setEnabled(False)
            compiled = True
        except Exception as error:
            self.execution_plan = None
            self.calculation_request = None
            self.execute_button.setEnabled(False)
            self.workflow_status.setText("Status: Compilation failed")
            QMessageBox.critical(self, "Compilation Failed", str(error))
        finally:
            if compiled:
                self.workflow_status.setText("Status: Workflow compiled")
            self._update_compile_availability()
    def _display_execution_plan(self):
        if self.execution_plan is None or self.calculation_request is None:
            return
        resolved = self.execution_plan.resolved_calculations
        calculation_map = self._get_calculation_map()
        summary = self.calculation_request.summary
        lines = [
            f"Structure snapshot: {summary.name}", f"Atoms: {summary.atom_count}",
            "", "Resolved execution sequence:", "",
        ]
        task_by_id = {task.id: task for task in self.execution_plan.tasks}
        private_labels = {"qe_pw_nscf_btp2": "QE NSCF [BTP2 transport mesh]", "btp2_interpolate": "BTP2 interpolation", "btp2_transport": "BTP2 transport integration"}
        for index, calculation_id in enumerate(resolved, start=1):
            calculation = calculation_map.get(calculation_id)
            task = self.execution_plan.task_for_calculation(calculation_id)
            dependencies = ", ".join(
                task_by_id[task_id].calculation_id for task_id in task.depends_on_task_ids
            ) or "none"
            lines.append(
                f"{index}. {calculation.name if calculation is not None else private_labels.get(calculation_id, calculation_id)}"
                f"   depends on: {dependencies}"
            )
        btp2_tasks = [task for task in self.execution_plan.tasks if task.engine_id == "boltztrap2"]
        if btp2_tasks:
            settings = btp2_tasks[0].parameters.get("btp2")
            if settings is not None:
                values = settings.to_dict()
                lines.extend(["", "BTP2 physical settings:", f"* transport k mesh: {values['transport_k_mesh']}", f"* temperatures (K): {values['temperatures_kelvin']}", f"* chemical potential (eV): {values['chemical_potentials_ev'] or values['chemical_potential_range_ev']}", f"* carrier concentration (cm^-3): {values['carrier_concentrations_cm3'] or values['carrier_concentration_range_cm3']}", f"* relaxation-time mode: {values['relaxation_time_model']}"])
                if values["relaxation_time_seconds"] is not None: lines.append(f"* tau (s): {values['relaxation_time_seconds']}")
                if any(item in btp2_tasks[-1].artifact_outputs for item in ("SIGMA_OVER_TAU", "KAPPA_E_OVER_TAU", "POWER_FACTOR_OVER_TAU")): lines.append(f"* outputs use explicit {chr(0x03c3)}/{chr(0x03c4)}, {chr(0x03ba)}e/{chr(0x03c4)}, and/or PF/{chr(0x03c4)} semantics")
                warning = btp2_tasks[0].metadata.get("normalization_warning")
                if warning: lines.append("* 2D normalization warning: " + warning)
        if self.calculation_service.workflow_input_available(self.execution_plan):
            lines.append("✓ Engine input generation available")
        else:
            support = self.calculation_service.qe_input_support(resolved)
            lines.extend((
                "", "Engine input generation deferred:",
                *[f"• {item['calculation_id']}: {item['reason']}" for item in support if not item["available"]],
            ))
        lines.extend(["", "✓ Workflow compiled", "✓ Dependencies resolved", "✓ Structure snapshot captured", "✓ Ready for QE input generation"])
        self.execution_preview.setText("\n".join(lines))
        self._update_compile_availability()

    def _preview_qe_inputs(self):
        if self.calculation_request is None:
            return
        try:
            generation = self.calculation_service.preview_engine_inputs(self.calculation_request)
            dialog = QDialog(self)
            dialog.setWindowTitle("Quantum ESPRESSO Input Preview")
            layout = QVBoxLayout(dialog)
            preview = QPlainTextEdit(dialog)
            preview.setReadOnly(True)
            preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
            preview.setStyleSheet("font-family: monospace;")
            preview.setPlainText("\n\n".join(
                f"# {task.working_directory}/{task.input_filename} ({task.executable})\n\n{task.input_text}"
                for task in generation
            ))
            layout.addWidget(preview)
            dialog.resize(840, 680)
            dialog.exec()
        except Exception as error:
            QMessageBox.warning(self, "QE Input Preview", str(error))

    def _generate_qe_inputs(self):
        request_id = self._selected_configured_request_id()
        if request_id is None or self.calculation_request is None or not self._workflow_compiled:
            QMessageBox.warning(self, "Generate QE Inputs", "Create and select a saved calculation request first.")
            return
        root = QFileDialog.getExistingDirectory(self, "Choose QE input export directory")
        if not root:
            return
        try:
            location = self.calculation_service.generate_engine_inputs(self.calculation_request, root)
            if hasattr(self.project, "register_execution_root"):
                self.project.register_execution_root(self.calculation_request.id, location)
            self._workflow_generated = True
            self.generate_qe_button.setEnabled(False)
            self.execute_button.setEnabled(True)
            self.workflow_status.setText("Status: Workflow generated — ready to run")
            QMessageBox.information(
                self, "QE Inputs Generated",
                f"QE inputs were generated at:\n{location}\n\nNo calculation was executed.",
            )
        except Exception as error:
            QMessageBox.warning(self, "Generate QE Inputs", str(error))

    # ============================================================
    # EXECUTE
    # ============================================================

    def _view_results(self):
        root=QFileDialog.getExistingDirectory(self, "Choose generated workflow directory")
        if root:
            ResultsDialog(self.result_service,root,self).exec()

    def _sync_resource_configuration(self, *_):
        self.local_tool_configuration.cpu_cores = self.cpu_cores_spin.value()
        self.local_tool_configuration.omp_threads = self.omp_threads_spin.value()
        value = self.mpi_launcher_input.text().strip()
        self.local_tool_configuration.mpi_launcher = value or "auto"

    def _configure_local_tools(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Local Tool Configuration")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Optional absolute executable paths. Blank entries resolve from PATH."))
        form = QFormLayout()
        fields = {}
        for tool_id in ("pw.x", "ph.x", "bands.x", "dos.x", "projwfc.x", "pp.x", "q2r.x", "matdyn.x", "pw2wannier90.x", "wannier90.x", "epw.x"):
            field = QLineEdit(self.local_tool_configuration.tool_paths.get(tool_id, ""), dialog)
            fields[tool_id] = field
            form.addRow(tool_id, field)
        mpi_field = QLineEdit(self.local_tool_configuration.mpi_launcher if self.local_tool_configuration.mpi_launcher != "auto" else "Auto", dialog)
        mpi_field.setPlaceholderText("Auto or absolute launcher path")
        form.addRow("MPI launcher", mpi_field)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, dialog)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.local_tool_configuration.tool_paths = {tool_id: field.text().strip() for tool_id, field in fields.items() if field.text().strip()}
            self.mpi_launcher_input.setText(mpi_field.text())
            self._sync_resource_configuration()

    def _execute_requested(self):
        if self._active_execution is not None and not self._active_execution.done.is_set():
            self._active_execution.cancel()
            self.execution_preview.setPlainText("Cancelling the active local task; dependent tasks will be blocked.")
            return
        if self.execution_plan is None or self.calculation_request is None or not self._workflow_generated:
            QMessageBox.warning(self, "No Generated Workflow", "Compile and generate the selected workflow before local execution.")
            return
        root = QFileDialog.getExistingDirectory(self, "Choose generated workflow directory")
        if not root:
            return
        try:
            workflow = self.calculation_service.execution_workflow(self.calculation_request, root)
            if hasattr(self.project, "register_execution_root"):
                self.project.register_execution_root(self.calculation_request.id, root)
            manager = LocalExecutionManager(self.local_tool_configuration)
            errors = manager.preflight(workflow)
            if errors:
                QMessageBox.warning(self, "Local Execution Preflight", "Cannot run this workflow:\n\n" + "\n".join(errors))
                return
            if QMessageBox.question(self, "Run Local Workflow", "Preflight passed. Run the generated workflow serially using configured tools/PATH?") != QMessageBox.StandardButton.Yes:
                return
            store = ExecutionStore(root)
            assessment = store.assess(workflow, request_id=self.calculation_request.id)
            record = None
            if assessment.state is RecoveryState.RECOVERABLE:
                if QMessageBox.question(self, "Recover Local Execution", "A recoverable execution was found. Resume from completed prerequisites?") == QMessageBox.StandardButton.Yes:
                    record = assessment.record
            elif assessment.state in {RecoveryState.INCOMPATIBLE, RecoveryState.MODIFIED_INPUTS, RecoveryState.CORRUPT_RUNTIME_RECORD}:
                QMessageBox.information(self, "Execution History", assessment.message + " A new execution attempt will be created.")
            record = record or store.create(workflow)
            self._local_execution_service = LocalExecutionService(manager)
            self._active_execution = self._local_execution_service.start(workflow, record=record, store=store)
            self.execute_button.setText("Cancel")
            self.workflow_status.setText(f"Status: Running — {self.local_tool_configuration.cpu_cores} cores")
            self.execution_preview.setPlainText("Local execution started. The request snapshot and generated inputs are locked for this run.")
            QTimer.singleShot(100, self._poll_local_execution)
        except Exception as error:
            QMessageBox.warning(self, "Local Execution", str(error))

    def _poll_local_execution(self):
        handle = self._active_execution
        if handle is None:
            return
        if not handle.done.is_set():
            QTimer.singleShot(150, self._poll_local_execution)
            return
        self.execute_button.setText("Run")
        self.workflow_status.setText("Status: Execution finished")
        self._active_execution = None
        if handle.error is not None:
            QMessageBox.warning(self, "Local Execution", str(handle.error))
            return
        result = handle.result
        lines = ["Local execution finished: " + result.state.value]
        for task in result.tasks.values():
            line = f"{task.task_id}: {task.state.value}"
            if task.return_code is not None:
                line += f" (exit {task.return_code})"
            if task.stdout_path:
                line += f"\n  stdout: {task.stdout_path}"
            if task.stderr_path:
                line += f"\n  stderr: {task.stderr_path}"
            lines.append(line)
        self.execution_preview.setPlainText("\n".join(lines))
