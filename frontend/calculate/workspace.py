"""
Quantum Studio — Calculate Workspace

The Calculate workspace reads the active structure from the shared
Project object, allows calculation selection from the frontend catalog,
and communicates with the Quantum Studio backend through the API.

The workspace does not modify the structure.
"""

import json
import logging
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from backend.runtime import runtime_paths
from PySide6.QtGui import QGuiApplication
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
    QStackedWidget,
)

from frontend.calculations.catalog import CALCULATIONS
from frontend.services.calculation_service import CalculationService
from frontend.services.result_service import ResultService
from frontend.calculate.parameter_session import PRESETS, descriptors, parse_value, preset_parameters
from frontend.calculate.functional_pseudo_dialog import FunctionalPseudoDialog
from frontend.calculate.preparation import CalculationPreparationWorker
from frontend.calculate.result_parsing import ResultParsingWorker
from frontend.calculate.qe_discovery import QuantumEspressoDiscoveryWorker
from frontend.calculate.band_path_dialog import BandPathDialog
from frontend.builder.brillouin_zone.path_api import band_path_summary, normalize_band_path, recommended_band_path, materialize_path
from frontend.calculate.results_dialog import ResultsDialog
from frontend.calculate.typed_parameter_controls import control_value, make_control
from backend.execution import ExecutionStore, LocalExecutionManager, LocalExecutionService, LocalToolConfiguration, RecoveryState, available_logical_cpus

LOGGER = logging.getLogger(__name__)


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
        self._configured_selection_ids = []
        self._request_status = {}

        self.execution_plan = None
        self.calculation_request = None
        # These are read while the UI constructs its initial availability state.
        self._workflow_compiled = False
        self._workflow_generated = False
        self._generated_root_path = None
        self.current_structure_summary = None
        self._local_execution_service = None
        self._active_execution = None
        self._last_execution_output_paths = ()
        self._preparation_worker = None
        self._result_parsing_worker = None
        self._preparation_for_run = False
        self._pseudo_provisioner = None
        self.local_tool_configuration = LocalToolConfiguration.load_machine_configuration()
        self._qe_discovery_worker = None
        self._qe_discovery_resume_run = False
        self._qe_discovery_started = False
        self.result_service = ResultService()

        self._build_ui()
        self._apply_style()
        self._populate_categories()
        self._populate_calculations()
        self._refresh_configured_calculations()

    def showEvent(self, event):
        super().showEvent(event)
        if not self._qe_discovery_started:
            self._qe_discovery_started = True
            QTimer.singleShot(0, self._start_qe_discovery)

    def closeEvent(self, event):
        for worker in (self._preparation_worker, self._qe_discovery_worker, self._result_parsing_worker):
            if worker is not None and worker.isRunning(): worker.wait()
        super().closeEvent(event)

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
            QAbstractItemView.SelectionMode.ExtendedSelection
        )

        self.calculation_list.itemChanged.connect(
            self._calculation_item_changed
        )
        self.calculation_list.itemSelectionChanged.connect(
            self._catalog_selection_changed
        )

        catalog_layout.addWidget(
            self.calculation_list,
            1,
        )

        self.catalog_create_button = QPushButton("Add Selected Calculations", catalog_panel)
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

        configured_header = QLabel("My Calculations")
        configured_header.setObjectName("panelTitle")
        selection_layout.addWidget(configured_header)
        self.configured_list = QListWidget()
        self.configured_list.setMaximumHeight(140)
        self.configured_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
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
        self.edit_parameters_button = QPushButton("Configure")
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
        self.create_button = QPushButton("Add Calculation", self); self.create_button.setEnabled(False); self.create_button.clicked.connect(self._create_calculation_requested)
        self.compile_button = QPushButton("Compile Workflow", self); self.compile_button.setEnabled(False); self.compile_button.clicked.connect(self._compile_requested)
        self.preview_qe_button = QPushButton("View QE Inputs", self); self.preview_qe_button.setEnabled(False); self.preview_qe_button.clicked.connect(self._preview_qe_inputs)
        self.configure_tools_button = QPushButton("Local Tools…", self); self.configure_tools_button.clicked.connect(self._configure_local_tools)
        self.view_results_button = QPushButton("Results…", self); self.view_results_button.clicked.connect(self._view_results)
        for secondary in (self.create_button, self.compile_button, self.preview_qe_button, self.configure_tools_button, self.view_results_button):
            secondary.setVisible(False)
        self.more_button = QToolButton(self); self.more_button.setText("More ▾"); self.more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu=QMenu(self.more_button); self._more_create_action=menu.addAction("Add Calculation",self.create_button.click); menu.addSeparator(); self._more_preview_action=menu.addAction("View QE Inputs",self.preview_qe_button.click); menu.addAction("Local Tools…",self.configure_tools_button.click); menu.addAction("View Last Output…",self._view_last_execution_output); menu.addAction("Results…",self.view_results_button.click); self.more_button.setMenu(menu); footer.addWidget(self.more_button)

        self.compile_button.setVisible(False)
        self.compile_button.setText("Compile")
        self.compile_button.setObjectName("compileButton")
        footer.addWidget(self.compile_button)
        self.generate_qe_button = QPushButton("Generate QE Inputs", self); self.generate_qe_button.setObjectName("compileButton"); self.generate_qe_button.setEnabled(False); self.generate_qe_button.clicked.connect(self._generate_qe_inputs); footer.addWidget(self.generate_qe_button)
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

    def _catalog_selection_changed(self):
        """Make ordinary extended-list highlighting addable as catalog selection."""
        highlighted = [
            item.data(Qt.ItemDataRole.UserRole)
            for item in self.calculation_list.selectedItems()
        ]
        if highlighted:
            self.selected_ids = list(dict.fromkeys([*self.selected_ids, *highlighted]))
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

        self.selected_count.setText(f"{count} {label}")
        self.catalog_create_button.setText("Add Selected Calculations" if count == 0 else f"Add Selected Calculations ({count})")

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
        configured_count = len(self._selected_configured_request_ids()) if hasattr(self, "configured_list") else 0
        request_ready = configured_count > 1 or (self._selected_configured_request_id() is not None and self.calculation_request is not None)
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
            self.generate_qe_button.setEnabled(request_ready and not self._workflow_generated)
            self.execute_button.setEnabled(request_ready)
            self.execute_button.setText(f"Run Selected ({configured_count})" if configured_count > 1 else "Run")
            self.generate_qe_button.setText(f"Generate QE Inputs ({configured_count})" if configured_count > 1 else "Generate QE Inputs")
            current_status = self.workflow_status.text()
            protected_status = current_status.startswith("Status: Failed") or current_status.startswith("Status: Calculation completed") or current_status.startswith("Status: Results ready") or self._preparation_worker is not None or self._active_execution is not None
            if not protected_status:
                self.workflow_status.setText("Status: QE inputs ready" if self._workflow_generated else ("Status: Ready to generate QE inputs" if request_ready else "Status: Select a calculation and add it to your project"))

    def refresh(self):
        """Refresh derived display state; existing request snapshots are intentionally unchanged."""
        self._refresh_resource_bounds()
        self._refresh_structure_summary()
        self._refresh_configured_calculations()

    # ============================================================
    # PERSISTENT CONFIGURED REQUESTS
    # ============================================================

    def _selected_configured_request_ids(self):
        if not hasattr(self, "configured_list"):
            return []
        return [item.data(Qt.ItemDataRole.UserRole) for item in self.configured_list.selectedItems()]

    def _selected_configured_request_id(self):
        selected = self._selected_configured_request_ids()
        return selected[0] if selected else None

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
        selected_ids = list(self._configured_selection_ids)
        if selected_id is not None:
            selected_ids = [selected_id]
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
            display_status = self._request_status.get(request.id, "READY" if summary is not None else "FAILED")
            item = QListWidgetItem(request.name or request.calculation_id)
            item.setData(Qt.ItemDataRole.UserRole + 1, display_status)
            item.setData(Qt.ItemDataRole.UserRole, request.id)
            item.setToolTip(f"{display_status}\nRequest ID: {request.id}")
            self.configured_list.addItem(item)
            if request.id in selected_ids:
                item.setSelected(True)
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
        request_ids = self._selected_configured_request_ids()
        self._configured_selection_ids = request_ids
        request_id = request_ids[0] if request_ids else None
        request = self.project.get_calculation(request_id) if request_id else None
        self._set_configured_action_enabled(bool(request_ids))
        if request is None:
            self._update_compile_availability()
            return
        if len(request_ids) > 1:
            self.request_name.clear()
            self.execution_plan = None
            self.calculation_request = None
            self.execution_preview.setText(f"{len(request_ids)} calculations selected. Configure or run the selected jobs together.")
            self.workflow_status.setText(f"Status: {len(request_ids)} calculations selected")
            self._update_compile_availability()
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
        parameters = dict(parameters or {})
        if "bands" in self.selected_ids:
            existing_path = parameters.get("kpath")
            if existing_path:
                parameters["kpath"] = normalize_band_path(existing_path)
            else:
                recommendation = recommended_band_path(self.project.get_structure().to_dict())
                parameters["kpath"] = normalize_band_path(materialize_path(recommendation.segments, (True,) * len(recommendation.segments), 40))
            parameters["postprocessing"] = True
        elif "phonon_band_structure" in self.selected_ids:
            existing_path = parameters.get("phonon_path")
            if existing_path:
                parameters["phonon_path"] = normalize_band_path(existing_path)
            else:
                recommendation = recommended_band_path(self.project.get_structure().to_dict())
                if recommendation.segments:
                    parameters["phonon_path"] = normalize_band_path(materialize_path(recommendation.segments, (True,) * len(recommendation.segments), 24))
                    parameters["phonon_path_convention"] = "Quantum Studio " + recommendation.bravais_label + " recommendation"
            parameters["postprocessing"] = True
        elif "phonon_dos" in self.selected_ids:
            parameters["postprocessing"] = True
        elif set(self.selected_ids) & {"dos", "pdos", "charge_density", "spin_density", "electron_localization", "electrostatic_potential", "work_function"}:
            # These public intents expand into private QE terminal tasks only
            # when this workflow flag is present; never silently run SCF-only.
            parameters["postprocessing"] = True
        prepared = self.calculation_service.create_request(
            self.project, self.selected_ids, parameters=parameters, name=name,
        )
        self.project.add_calculation(prepared.backend_request)
        self.calculation_request = prepared
        self._refresh_configured_calculations(prepared.id)
        return prepared

    def _create_calculation_requested(self):
        try:
            prepared_requests = []
            checked_ids = list(self.selected_ids)
            for calculation_id in checked_ids:
                self.selected_ids = [calculation_id]
                prepared_requests.append(self.create_persistent_calculation())
            self.selected_ids = checked_ids
            if prepared_requests:
                self._refresh_configured_calculations(prepared_requests[-1].id)
                return prepared_requests[-1]
            return None
        except Exception as error:
            QMessageBox.warning(self, "Create Calculation", str(error))
            return None

    def _configure_parameters(self):
        configured_ids = self._selected_configured_request_ids()
        if len(configured_ids) > 1:
            return self._configure_batch_parameters(configured_ids)
        if not self.selected_ids:
            request = self.project.get_calculation(self._selected_configured_request_id())
            if request is not None:
                self.selected_ids = list(request.selected_calculations)
        if not self.selected_ids:
            QMessageBox.information(self, "Parameters", "Select a generation-ready calculation first."); return
        dialog=QDialog(self); dialog.setWindowTitle("Scientific Parameters"); layout=QVBoxLayout(dialog)
        preset=QComboBox(dialog)
        for mode,label in (("FAST","Fast"),("INTERMEDIATE","Intermediate"),("PRECISE","Precise"),("CUSTOM","Custom")): preset.addItem(label,mode)
        configured_request = self.project.get_calculation(self._selected_configured_request_id())
        # A newly selected catalog calculation must start from its own defaults;
        # never carry scientific method state from the previously selected request.
        same_request = configured_request is not None and list(configured_request.selected_calculations) == list(self.selected_ids)
        existing = json.loads(self.parameters_input.text() or "{}") if same_request else {}
        if not isinstance(existing, dict):
            existing = {}
        preset.setCurrentIndex(max(0,preset.findData(existing.get("accuracy_preset","INTERMEDIATE"))))
        layout.addWidget(QLabel("Accuracy preset")); layout.addWidget(preset)
        structure=(self.calculation_request.backend_request.structure if same_request and self.calculation_request is not None else self.project.get_structure().to_dict())
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
            if key in {"kpath", "phonon_path"}:
                field=QPushButton("Choose Band Path…  [" + band_path_summary(value) + "]",dialog); field.band_path=normalize_band_path(value)
                def choose_path(_checked=False, button=field):
                    try:
                        editor = BandPathDialog(structure, button.band_path, dialog)
                        if editor.exec() == QDialog.DialogCode.Accepted:
                            button.band_path = normalize_band_path(editor.value())
                            button.setText("Choose Band Path…  [" + band_path_summary(button.band_path) + "]")
                            button.setToolTip("Selected band path: " + band_path_summary(button.band_path))
                    except Exception as error:
                        QMessageBox.warning(dialog, "Band Path", str(error))
                field.clicked.connect(choose_path)
            else: field=make_control(key,value,dialog,structure=structure)
            field.setToolTip(item["key"]); fields[key]=field; form.addRow(item["label"]+(f" ({item['unit']})" if item["unit"] else ""),field)
        magnet_label = next((form.labelForField(fields["starting_magnetization"]) for _ in (0,) if "starting_magnetization" in fields), None)
        total_label = next((form.labelForField(fields["tot_magnetization"]) for _ in (0,) if "tot_magnetization" in fields), None)
        def collinear_selected():
            if "spin_treatment" in fields:
                return control_value("spin_treatment", fields["spin_treatment"]) == "COLLINEAR_SPIN"
            return bool(control_value("spin", fields["spin"])) if "spin" in fields else False
        def update_magnetization_visibility(*_):
            visible=collinear_selected()
            for key,label_widget in (("starting_magnetization",magnet_label),("tot_magnetization",total_label)):
                if key in fields:
                    fields[key].setVisible(visible)
                    if label_widget is not None: label_widget.setVisible(visible)
        def update_occupation_visibility(*_):
            occupation = control_value("occupations", fields["occupations"]).strip().lower() if "occupations" in fields else ""
            visible = occupation == "smearing"
            for key in ("smearing", "degauss"):
                if key in fields:
                    fields[key].setVisible(visible)
                    label_widget = form.labelForField(fields[key])
                    if label_widget is not None: label_widget.setVisible(visible)
        if "spin_treatment" in fields: fields["spin_treatment"].currentTextChanged.connect(update_magnetization_visibility)
        elif "spin" in fields: fields["spin"].toggled.connect(update_magnetization_visibility)
        if "occupations" in fields: fields["occupations"].currentTextChanged.connect(update_occupation_visibility)
        update_magnetization_visibility(); update_occupation_visibility()
        form_container = QWidget(dialog); form_container.setLayout(form)
        resolved=QTableWidget(dialog); resolved.setColumnCount(2); resolved.setHorizontalHeaderLabels(("Parameter", "Value")); resolved.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents); resolved.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch); resolved.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers); resolved.setMaximumHeight(180)
        scroll_content = QWidget(dialog); scroll_layout = QVBoxLayout(scroll_content); scroll_layout.setContentsMargins(0, 0, 0, 0); scroll_layout.addWidget(form_container); scroll_layout.addWidget(QLabel("Resolved parameters (read-only)")); scroll_layout.addWidget(resolved)
        scroll = QScrollArea(dialog); scroll.setWidgetResizable(True); scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff); scroll.setWidget(scroll_content); layout.addWidget(scroll, 1)
        def values_from_fields():
            values={}
            occupation = control_value("occupations", fields["occupations"]).strip().lower() if "occupations" in fields else ""
            for key,field in fields.items():
                if key == "starting_magnetization" and not collinear_selected():
                    continue
                if key in {"smearing", "degauss"} and occupation != "smearing":
                    continue
                values[key]=normalize_band_path(field.band_path) if key in {"kpath", "phonon_path"} else control_value(key,field)
            return values
        def refresh():
            values=preset_parameters(self.selected_ids,preset.currentData(),values_from_fields()); values.update(scientific_state)
            resolved.setRowCount(0)
            for key, value in sorted(values.items()):
                row = resolved.rowCount(); resolved.insertRow(row)
                resolved.setItem(row, 0, QTableWidgetItem(str(key)))
                resolved.setItem(row, 1, QTableWidgetItem(json.dumps(value, sort_keys=True) if isinstance(value, (dict, list, tuple)) else str(value)))
        preset.currentIndexChanged.connect(refresh); refresh()
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel,dialog); buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons, 0)
        CalculateWorkspace._fit_configuration_dialog(dialog, 720, 620)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            values=values_from_fields(); values.update(scientific_state)
            if set(self.selected_ids) & {"bands", "dos", "pdos", "charge_density", "spin_density", "electron_localization", "electrostatic_potential", "work_function", "phonon_dos", "phonon_band_structure"}:
                values["postprocessing"] = True
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


    def _batch_root(self):
        base = Path(self.project.file_path).parent if getattr(self.project, "file_path", None) else runtime_paths().workflows
        return base / ".quantum_studio_workflows" / "batch"

    def _fit_configuration_dialog(dialog, width=720, height=620):
        parent = dialog.parentWidget()
        screen = QGuiApplication.screenAt(parent.mapToGlobal(parent.rect().center())) if parent else QGuiApplication.primaryScreen()
        available = screen.availableGeometry() if screen is not None else None
        if available is None:
            available = dialog.screen().availableGeometry() if dialog.screen() else None
        if available is None:
            dialog.resize(width, height)
            return
        max_height = max(240, int(available.height() * 0.78))
        max_width = max(520, int(available.width() * 0.82))
        initial_width = min(width, max_width)
        initial_height = min(height, max_height)
        dialog.setMinimumSize(min(initial_width, max_width), min(240, max_height))
        dialog.resize(initial_width, initial_height)
        frame = dialog.frameGeometry()
        frame.moveCenter(available.center())
        if frame.left() < available.left(): frame.moveLeft(available.left())
        if frame.top() < available.top(): frame.moveTop(available.top())
        if frame.right() > available.right(): frame.moveRight(available.right())
        if frame.bottom() > available.bottom(): frame.moveBottom(available.bottom())
        dialog.move(frame.topLeft())

    def _configure_batch_parameters(self, request_ids):
        """Edit selected requests one at a time without sharing dictionaries."""
        requests = [self.project.get_calculation(item) for item in request_ids]
        requests = [item for item in requests if item is not None]
        if not requests:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Batch Configuration ({len(requests)} calculations)")
        layout = QVBoxLayout(dialog)
        heading = QLabel(dialog)
        layout.addWidget(heading)
        stack = QStackedWidget(dialog)
        pages = []
        for request in requests:
            page = QWidget(stack)
            form = QFormLayout(page)
            fields = {}
            for item in descriptors(request.selected_calculations):
                key = item["key"]
                field = make_control(key, request.parameters.get(key, item["default"]), page, structure=request.structure)
                fields[key] = field
                form.addRow(item["label"] + (f" ({item['unit']})" if item["unit"] else ""), field)
                if key in {"starting_magnetization", "tot_magnetization"}:
                    method = request.parameters.get("spin_treatment", "COLLINEAR_SPIN" if request.parameters.get("spin") else "SCALAR_NONSPIN")
                    visible = method == "COLLINEAR_SPIN"
                    field.setVisible(visible)
                    label_widget = form.labelForField(field)
                    if label_widget is not None: label_widget.setVisible(visible)
            stack.addWidget(page)
            pages.append((request, fields))
        layout.addWidget(stack, 1)
        navigation = QHBoxLayout()
        back = QPushButton("Back", dialog); next_button = QPushButton("Next", dialog)
        cancel = QPushButton("Cancel", dialog); apply_button = QPushButton("Apply", dialog)
        for button in (back, next_button): navigation.addWidget(button)
        navigation.addStretch(); navigation.addWidget(cancel); navigation.addWidget(apply_button)
        layout.addLayout(navigation)

        def save_page(index):
            request, fields = pages[index]
            values = dict(request.parameters)
            values.update({key: control_value(key, field) for key, field in fields.items()})
            method = values.get("spin_treatment", "COLLINEAR_SPIN" if values.get("spin") else "SCALAR_NONSPIN")
            if method != "COLLINEAR_SPIN": values.pop("starting_magnetization", None)
            pages[index] = (request, fields)
            return request, values

        staged = {}
        def stage_page(index):
            request, values = save_page(index); staged[request.id] = values

        def refresh_navigation():
            index = stack.currentIndex()
            heading.setText(f"Calculation {index + 1} of {len(pages)}: {pages[index][0].name or pages[index][0].calculation_id}")
            back.setEnabled(index > 0); next_button.setVisible(index < len(pages) - 1); apply_button.setVisible(index == len(pages) - 1)

        def previous():
            stage_page(stack.currentIndex()); stack.setCurrentIndex(stack.currentIndex() - 1); refresh_navigation()
        def following():
            stage_page(stack.currentIndex()); stack.setCurrentIndex(stack.currentIndex() + 1); refresh_navigation()
        back.clicked.connect(previous); next_button.clicked.connect(following); cancel.clicked.connect(dialog.reject); apply_button.clicked.connect(dialog.accept)
        refresh_navigation(); CalculateWorkspace._fit_configuration_dialog(dialog, 680, 620)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        stage_page(stack.currentIndex())
        for request, _fields in pages:
            values = staged.get(request.id, dict(request.parameters))
            self.project.update_calculation(self.calculation_service.update_request_parameters(request, values, name=request.name))
        self._refresh_configured_calculations(request_ids[0])

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
    def _result_parsing_completed(self, worker):
        if self._result_parsing_worker is worker:
            self._result_parsing_worker = None
        worker.deleteLater()
        if worker.error is not None:
            LOGGER.debug("Automatic result parsing failed:\n%s", worker.error[1])
            self.workflow_status.setText("Status: Calculation completed. Results processing failed")
            return
        outcome = worker.outcome or {}
        errors = outcome.get("errors", ())
        if errors:
            detail = "; ".join(str(error) for error in errors)
            prefix = "DOS calculation completed, but Quantum Studio could not parse the DOS result: " if any(str(error).startswith("qe_dos:") for error in errors) else "PDOS calculation completed, but Quantum Studio could not parse the PDOS result: " if any(str(error).startswith("qe_projwfc:") for error in errors) else "Calculation completed, but Quantum Studio could not parse one or more results: "
            self.workflow_status.setText("Status: " + prefix + detail)
            if hasattr(self.execution_preview, "appendPlainText"):
                self.execution_preview.appendPlainText("\nResult parsing failed: " + detail)
            else:
                self.execution_preview.setText(self.execution_preview.text() + "\nResult parsing failed: " + detail)
        else:
            self.workflow_status.setText("Status: Results ready")
        self._update_compile_availability()

    def _generated_root(self):
        existing = self.project.execution_roots().get(str(self.calculation_request.id)) if hasattr(self.project, "execution_roots") and self.calculation_request else None
        if existing: return existing
        base = Path(self.project.file_path).parent if getattr(self.project, "file_path", None) else runtime_paths().workflows
        return str(base / ".quantum_studio_workflows")

    def _preview_qe_inputs(self):
        root = getattr(self, "_generated_root_path", None)
        if not root or not Path(root).exists():
            QMessageBox.information(self, "View QE Inputs", "Generate QE inputs first.")
            return
        files=sorted(path for path in Path(root).rglob("*") if path.is_file() and path.suffix in {".in", ".win", ".epwin"})
        if not files:
            QMessageBox.information(self, "View QE Inputs", "No generated text input files were found.")
            return
        dialog=QDialog(self); dialog.setWindowTitle("Quantum ESPRESSO Inputs"); layout=QVBoxLayout(dialog); preview=QPlainTextEdit(dialog); preview.setReadOnly(True); preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap); preview.setStyleSheet("font-family: monospace;")
        preview.setPlainText("\n\n".join(f"# {path.relative_to(root)}\n\n{path.read_text(encoding='utf-8', errors='replace')}" for path in files)); layout.addWidget(preview); dialog.resize(840,680); dialog.exec()

    def _set_preparation_active(self, active):
        self.generate_qe_button.setEnabled(not active and self.calculation_request is not None and not self._workflow_generated)
        self.execute_button.setEnabled(not active and self.calculation_request is not None)
        self.edit_parameters_button.setEnabled(not active and self.calculation_request is not None)
        if active:
            self.execute_button.setText("Preparing…")
            self.workflow_status.setText("Status: Preparing calculation…")
        elif self._active_execution is None:
            self.execute_button.setText("Run")

    def _start_preparation(self, for_run=False, repair_workflow_root=None):
        request_id = self._selected_configured_request_id()
        if request_id is None or self.calculation_request is None:
            QMessageBox.warning(self, "Run" if for_run else "Generate QE Inputs", "Add and configure a calculation first.")
            return
        if self._preparation_worker is not None:
            QMessageBox.information(self, "Preparing Calculation", "Calculation preparation is already in progress.")
            return
        self._preparation_for_run=bool(for_run)
        self._set_preparation_active(True)
        worker=CalculationPreparationWorker(self.calculation_service,self.calculation_request,self._generated_root(),self._pseudo_provisioner,self,repair_workflow_root=repair_workflow_root,execution_profile=getattr(self.local_tool_configuration,"qe_execution_profile","STANDARD"))
        self._preparation_worker=worker
        worker.progress.connect(self._preparation_progress)
        worker.finished.connect(self._preparation_completed)
        worker.start()

    def _preparation_completed(self):
        worker=self._preparation_worker
        if worker is None: return
        result=worker.result; error=worker.error
        self._finish_preparation_worker()
        if error is not None: self._preparation_failed(*error)
        elif result is not None: self._preparation_ready(*result)

    def _preparation_progress(self, message):
        self.workflow_status.setText("Status: "+str(message))

    def _finish_preparation_worker(self):
        worker=self._preparation_worker
        if worker is not None:
            worker.wait()
            worker.deleteLater()
            self._preparation_worker=None

    def _preparation_ready(self, prepared, plan, location):
        run_after=self._preparation_for_run
        self._preparation_for_run=False
        self._finish_preparation_worker()
        self.project.update_calculation(prepared.backend_request)
        self.calculation_request=prepared
        self.execution_plan=plan
        self.parameters_input.setText(json.dumps(prepared.backend_request.parameters,sort_keys=True))
        if hasattr(self.project,"register_execution_root"):
            self.project.register_execution_root(prepared.id,location)
        self._workflow_compiled=True
        self._workflow_generated=True
        self._generated_root_path=str(location)
        self.workflow_status.setText("Status: QE inputs ready")
        self._set_preparation_active(False)
        self._update_compile_availability()
        if run_after:
            self.workflow_status.setText("Status: Starting calculation…")
            self._start_prepared_execution()
        else:
            QMessageBox.information(self,"QE Inputs Generated",f"QE inputs were generated at:\n{location}\n\nNo calculation was executed.")

    def _preparation_failed(self, message, technical):
        self._preparation_for_run=False
        self._finish_preparation_worker()
        LOGGER.debug("Calculate preparation failed:\n%s",technical)
        self.workflow_status.setText("Status: Preparation failed")
        self._set_preparation_active(False)
        self._update_compile_availability()
        QMessageBox.warning(self,"Calculation Preparation",str(message))

    def _generate_qe_inputs(self, _checked=False):
        request_ids = self._selected_configured_request_ids()
        if len(request_ids) > 1:
            try:
                requests = [item for item in (self.project.get_calculation(item) for item in request_ids) if item is not None]
                self.batch_execution_plans = self.calculation_service.compile_batch_requests(requests)
                self._batch_generated_roots = self.calculation_service.generate_batch_inputs(requests, self._batch_root())
                self._request_status.update({item.id: "READY" for item in requests})
                self.workflow_status.setText(f"Status: {len(request_ids)} workflows ready")
                self.execution_preview.setText("Batch inputs generated in separate workflow directories; each request remains independent.")
            except Exception as error:
                self.workflow_status.setText("Status: Batch preparation failed")
                QMessageBox.warning(self, "Generate QE Inputs", str(error))
            return
        self._start_preparation(False)

    # ============================================================
    # EXECUTE
    # ============================================================

    def _view_last_execution_output(self):
        paths = tuple(Path(path) for path in self._last_execution_output_paths if Path(path).is_file())
        if not paths:
            QMessageBox.information(self, "View Output", "No execution output is available yet.")
            return
        dialog = QDialog(self); dialog.setWindowTitle("Execution Output"); layout = QVBoxLayout(dialog)
        viewer = QPlainTextEdit(dialog); viewer.setReadOnly(True); viewer.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap); viewer.setStyleSheet("font-family: monospace;")
        blocks = []
        for path in paths:
            data = path.read_bytes()[-131072:].decode("utf-8", errors="replace")
            blocks.append(f"# {path}\n\n{data}")
        viewer.setPlainText("\n\n".join(blocks)); layout.addWidget(viewer); dialog.resize(900, 680); dialog.exec()

    def _view_results(self):
        root=QFileDialog.getExistingDirectory(self, "Choose generated workflow directory")
        if root:
            ResultsDialog(self.result_service,root,self).exec()

    def _sync_resource_configuration(self, *_):
        self.local_tool_configuration.cpu_cores = self.cpu_cores_spin.value()
        self.local_tool_configuration.omp_threads = self.omp_threads_spin.value()
        value = self.mpi_launcher_input.text().strip()
        self.local_tool_configuration.mpi_launcher = value or "auto"

    def _start_qe_discovery(self, resume_run=False, deep=False):
        self._qe_discovery_resume_run = self._qe_discovery_resume_run or bool(resume_run)
        if self._qe_discovery_worker is not None: return
        worker=QuantumEspressoDiscoveryWorker(self.local_tool_configuration,deep=deep,parent=self)
        self._qe_discovery_worker=worker
        worker.progress.connect(self._qe_discovery_progress)
        worker.finished.connect(self._qe_discovery_completed)
        worker.start()

    def _qe_discovery_progress(self, message):
        if self._workflow_generated and self._active_execution is None and self._preparation_worker is None: self.workflow_status.setText("Status: QE inputs ready — "+str(message))

    def _qe_discovery_completed(self):
        worker=self._qe_discovery_worker
        if worker is None: return
        result,error=worker.result,worker.error
        worker.wait(); worker.deleteLater(); self._qe_discovery_worker=None
        resume=self._qe_discovery_resume_run; self._qe_discovery_resume_run=False
        if error is not None:
            LOGGER.debug("QE discovery failed:\n%s",error[1])
        installation=result.preferred if result is not None else None
        if installation is None:
            if self._workflow_generated:
                self.workflow_status.setText("Status: Failed — Quantum ESPRESSO executable not found")
            if resume:
                QMessageBox.warning(self,"Quantum ESPRESSO", "Quantum ESPRESSO could not be found automatically.\n\nChoose an installation folder or install Quantum ESPRESSO and try again.")
            return
        self.local_tool_configuration.apply_quantum_espresso(installation)
        try: self.local_tool_configuration.save_machine_configuration()
        except OSError as save_error: LOGGER.debug("Could not persist local QE configuration: %s",save_error)
        if self._workflow_generated and self._active_execution is None and self._preparation_worker is None: self.workflow_status.setText(f"Status: QE inputs ready — Quantum ESPRESSO {installation.version} detected")
        if resume: self._start_prepared_execution()

    def _choose_qe_installation_folder(self):
        folder=QFileDialog.getExistingDirectory(self,"Choose Quantum ESPRESSO installation or bin folder")
        if not folder: return
        self.local_tool_configuration.qe_bin_directory=folder
        self._start_qe_discovery()

    def _configure_local_tools(self):
        self._start_qe_discovery()
        dialog=QDialog(self); dialog.setWindowTitle("Local Tools"); layout=QVBoxLayout(dialog)
        layout.addWidget(QLabel("Quantum ESPRESSO"))
        status=QLabel(dialog); location=QLabel(dialog); tools=QLabel(dialog)
        def refresh():
            version=self.local_tool_configuration.qe_version
            directory=self.local_tool_configuration.qe_bin_directory
            status.setText(("✓ Quantum ESPRESSO "+version+" detected") if version else "Searching for Quantum ESPRESSO…")
            location.setText("Installation: "+(directory or "Not detected"))
            found=sorted(name for name in ("pw.x","ph.x","bands.x","dos.x","projwfc.x","pp.x","q2r.x","matdyn.x","pw2wannier90.x","wannier90.x","epw.x") if name in self.local_tool_configuration.tool_paths)
            tools.setText("Detected tools: "+(", ".join(found) if found else "—"))
        refresh(); layout.addWidget(status); layout.addWidget(location); layout.addWidget(tools)
        actions=QHBoxLayout(); rescan=QPushButton("Rescan",dialog); choose=QPushButton("Choose Installation Folder",dialog); actions.addWidget(rescan); actions.addWidget(choose); layout.addLayout(actions)
        advanced_toggle=QToolButton(dialog); advanced_toggle.setText("Advanced ▸"); advanced_toggle.setCheckable(True); layout.addWidget(advanced_toggle)
        advanced=QWidget(dialog); advanced_layout=QFormLayout(advanced); fields={}
        for tool_id in ("pw.x","ph.x","bands.x","dos.x","projwfc.x","pp.x","q2r.x","matdyn.x","pw2wannier90.x","wannier90.x","epw.x"):
            field=QLineEdit(self.local_tool_configuration.tool_paths.get(tool_id,""),advanced); fields[tool_id]=field; advanced_layout.addRow(tool_id,field)
        advanced.setVisible(False); advanced_toggle.toggled.connect(lambda checked: (advanced.setVisible(checked),advanced_toggle.setText("Advanced ▾" if checked else "Advanced ▸"))); layout.addWidget(advanced)
        def rescan_clicked(): self._start_qe_discovery(); status.setText("Searching for Quantum ESPRESSO…")
        def choose_clicked():
            folder=QFileDialog.getExistingDirectory(dialog,"Choose Quantum ESPRESSO installation or bin folder")
            if folder: self.local_tool_configuration.qe_bin_directory=folder; self._start_qe_discovery(); location.setText("Installation: "+folder); status.setText("Searching for Quantum ESPRESSO…")
        rescan.clicked.connect(rescan_clicked); choose.clicked.connect(choose_clicked)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel,dialog); buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
        dialog.resize(620,480)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            for tool_id,field in fields.items():
                value=field.text().strip()
                if tool_id=="pw.x" and value and Path(value).is_dir(): self.local_tool_configuration.qe_bin_directory=value
                elif value: self.local_tool_configuration.tool_paths[tool_id]=value
            self._sync_resource_configuration(); self.local_tool_configuration.save_machine_configuration()
            if self.local_tool_configuration.qe_bin_directory: self._start_qe_discovery()

    def _execute_requested(self, _checked=False):
        request_ids = self._selected_configured_request_ids()
        if not request_ids:
            self.workflow_status.setText("Status: Select a configured calculation to run")
            QMessageBox.warning(self, "Run", "Select a configured calculation first.")
            return
        if len(request_ids) > 1 and self._active_execution is None:
            try:
                requests = [item for item in (self.project.get_calculation(item) for item in request_ids) if item is not None]
                self.batch_execution_plans = self.calculation_service.compile_batch_requests(requests)
                self._batch_requests = tuple(requests)
                self._request_status.update({item.id: "READY" for item in requests})
                self.workflow_status.setText(f"Status: Run Selected ({len(request_ids)}) compiled")
                self.execution_preview.setText("Selected public workflows compiled with compatible prerequisites shared by the existing DAG compiler.")
                self._start_batch_execution(requests)
            except Exception as error:
                self.workflow_status.setText("Status: Batch compilation failed")
                QMessageBox.warning(self, "Run Selected", str(error))
            return
        if self._active_execution is not None and not self._active_execution.done.is_set():
            self._active_execution.cancel()
            self.execution_preview.setText("Cancelling the active local task; dependent tasks will be blocked.")
            return
        if self.calculation_request is None:
            QMessageBox.warning(self,"Run","Add and configure a calculation first.")
            return
        if self._preparation_worker is not None:
            QMessageBox.information(self,"Preparing Calculation","Calculation preparation is already in progress.")
            return
        if not self._workflow_generated:
            self._start_preparation(True)
            return
        self._start_prepared_execution()

    def _start_batch_execution(self, requests):
        try:
            bundles = self.calculation_service.generate_batch_workflows(requests, self._batch_root())
            queue = []
            manager = LocalExecutionManager(self.local_tool_configuration)
            for prepared, root, request_ids in bundles:
                workflow = self.calculation_service.execution_workflow(prepared, root)
                errors = manager.preflight(workflow)
                if errors:
                    raise RuntimeError(f"Batch workflow preflight failed for {', '.join(request_ids)}:\n" + "\n".join(errors))
                queue.append((prepared, workflow, root, request_ids))
            if not queue:
                raise RuntimeError("Workflow contains no executable tasks.")
            if QMessageBox.question(self, "Run Selected", f"Preflight passed for {len(requests)} selected calculations. Run the batch?") != QMessageBox.StandardButton.Yes:
                return
            self._batch_queue = queue
            self._batch_current = None
            self._batch_failed = False
            self._run_next_batch_workflow()
        except Exception as error:
            self.workflow_status.setText("Status: Batch execution failed")
            QMessageBox.warning(self, "Run Selected", str(error))

    def _run_next_batch_workflow(self):
        if not getattr(self, "_batch_queue", None):
            self.execute_button.setText("Run")
            self._active_execution = None
            if getattr(self, "_batch_failed", False):
                self.workflow_status.setText("Status: One or more selected calculations failed")
            else:
                self.workflow_status.setText("Status: Selected calculations completed")
            return
        prepared, workflow, root, request_ids = self._batch_queue.pop(0)
        self._batch_current = (prepared, workflow, root, request_ids)
        self._request_status.update({request_id: "RUNNING" for request_id in request_ids})
        store = ExecutionStore(root)
        record = store.create(workflow)
        self._local_execution_service = LocalExecutionService(LocalExecutionManager(self.local_tool_configuration))
        self._active_execution = self._local_execution_service.start(workflow, record=record, store=store)
        self.execute_button.setText("Cancel")
        self.workflow_status.setText(f"Status: Running selected batch ({len(request_ids)} grouped request(s))")
        QTimer.singleShot(100, self._poll_local_execution)

    def _start_prepared_execution(self):
        root = self._generated_root_path or self._generated_root()
        try:
            workflow = self.calculation_service.execution_workflow(self.calculation_request, root)
            if hasattr(self.project, "register_execution_root"):
                self.project.register_execution_root(self.calculation_request.id, root)
            manager = LocalExecutionManager(self.local_tool_configuration)
            errors = manager.preflight(workflow)
            if errors:
                if any("Generated pseudopotential" in error for error in errors):
                    self.workflow_status.setText("Status: Repairing workflow pseudopotentials…")
                    self._start_preparation(True, repair_workflow_root=root)
                    return
                if any("pw.x" in error and "not configured or executable" in error for error in errors):
                    self.workflow_status.setText("Status: QE inputs ready — searching for Quantum ESPRESSO…")
                    self._start_qe_discovery(resume_run=True)
                    return
                detail = "Cannot run this workflow:\n\n" + "\n".join(errors)
                self.workflow_status.setText("Status: Failed — " + errors[0])
                QMessageBox.warning(self,"Local Execution Preflight", detail)
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
            self.execution_preview.setText("Local execution started. Generated inputs are locked for this run.")
            QTimer.singleShot(100, self._poll_local_execution)
        except Exception as error:
            self.workflow_status.setText("Status: Failed — " + str(error).splitlines()[0])
            QMessageBox.warning(self, "Local Execution Failed", str(error))

    def _poll_local_execution(self):
        handle = self._active_execution
        if handle is None:
            return
        if not handle.done.is_set():
            QTimer.singleShot(150, self._poll_local_execution)
            return
        if getattr(self, "_batch_current", None) is not None:
            _prepared, _workflow, _root, request_ids = self._batch_current
            state = "FAILED" if handle.error is not None or handle.result is None or handle.result.state.value != "COMPLETED" else "COMPLETED"
            self._request_status.update({request_id: state for request_id in request_ids})
            self._active_execution = None
            self._batch_current = None
            if state == "FAILED":
                self._batch_failed = True
                self._request_status.update({request_id: "FAILED" for request_id in request_ids})
                detail = str(handle.error) if handle.error is not None else next((task.error_message for task in handle.result.tasks.values() if task.error_message), "Workflow execution failed.") if handle.result is not None else "Workflow execution failed."
                self.workflow_status.setText("Status: Failed — " + detail.splitlines()[0])
            self._run_next_batch_workflow()
            return
        self.execute_button.setText("Run")
        self._active_execution = None
        if handle.error is not None:
            detail = str(handle.error)
            self.workflow_status.setText("Status: Failed — " + detail.splitlines()[0])
            self.execution_preview.setText("Local execution failed:\n" + detail)
            QMessageBox.warning(self, "Local Execution Failed", detail)
            return
        result = handle.result
        if result is None:
            detail = "Execution returned no result."
            self.workflow_status.setText("Status: Failed — " + detail)
            self.execution_preview.setText(detail)
            QMessageBox.warning(self, "Local Execution Failed", detail)
            return
        lines = ["Local execution result: " + result.state.value]
        for task in result.tasks.values():
            line = f"{task.task_id}: {task.state.value}"
            if task.return_code is not None:
                line += f" (exit {task.return_code})"
            if task.stdout_path:
                line += f"\n  stdout: {task.stdout_path}"
            if task.stderr_path:
                line += f"\n  stderr: {task.stderr_path}"
            if task.error_message:
                line += f"\n  error: {task.error_message}"
            lines.append(line)
        self._last_execution_output_paths = tuple(task.stdout_path for task in result.tasks.values() if task.stdout_path)
        self.execution_preview.setText("\n".join(lines))
        if result.state.value == "COMPLETED":
            self.workflow_status.setText("Status: Calculation completed. Processing results…")
            worker = ResultParsingWorker(self.result_service, self._generated_root_path, result.execution_id, self)
            self._result_parsing_worker = worker
            worker.finished_result.connect(self._result_parsing_completed)
            worker.start()
        else:
            detail = next((task.error_message for task in result.tasks.values() if task.error_message), None)
            detail = detail or f"Workflow ended in state {result.state.value}."
            self.workflow_status.setText("Status: Failed — " + detail.splitlines()[0])
            QMessageBox.warning(self, "Local Execution Failed", detail)
