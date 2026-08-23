from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QColor, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QColorDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QToolBar,
    QStackedWidget,
    QTabWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from frontend.core.project import Project
from frontend.builder import Builder
from frontend.calculate import CalculateWorkspace
from frontend.device_builder import DeviceBuilderWorkspace


class VerticalButton(QPushButton):

    def __init__(self, text):
        super().__init__(text)

        self.setCheckable(True)

        self.setCursor(
            Qt.CursorShape.PointingHandCursor
        )


class WorkspacePlaceholder(QWidget):

    def __init__(
        self,
        title,
        description,
    ):

        super().__init__()

        layout = QVBoxLayout(self)

        layout.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        title_label = QLabel(title)

        title_label.setObjectName(
            "workspaceTitle"
        )

        description_label = QLabel(
            description
        )

        description_label.setObjectName(
            "workspaceDescription"
        )

        description_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        layout.addWidget(
            title_label,
            alignment=Qt.AlignmentFlag.AlignCenter,
        )

        layout.addWidget(
            description_label,
            alignment=Qt.AlignmentFlag.AlignCenter,
        )


class ProjectWindow(QMainWindow):

    def __init__(self, project):

        super().__init__()

        self.project = project

        self._allow_close = False

        self.setWindowTitle(
            self._window_title()
        )

        self._build_ui()
        self._build_menu()
        self._apply_style()

    # ============================================================
    # Window title
    # ============================================================

    def _window_title(self):

        marker = (
            " *"
            if self.project.modified
            else ""
        )

        return (
            f"Quantum Studio — "
            f"{self.project.name}"
            f"{marker}"
        )

    # ============================================================
    # UI
    # ============================================================

    def _build_ui(self):

        central = QWidget()

        self.setCentralWidget(
            central
        )

        main_layout = QHBoxLayout(
            central
        )

        main_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        main_layout.setSpacing(0)

        # --------------------------------------------------------
        # Navigation
        # --------------------------------------------------------

        navigation = QFrame()

        navigation.setObjectName(
            "navigation"
        )

        navigation.setFixedWidth(220)

        nav_layout = QVBoxLayout(
            navigation
        )

        nav_layout.setContentsMargins(
            18,
            24,
            18,
            18,
        )

        nav_layout.setSpacing(8)

        logo = QLabel(
            "QUANTUM\nSTUDIO"
        )

        logo.setObjectName(
            "logo"
        )

        nav_layout.addWidget(logo)

        nav_layout.addSpacing(30)

        self.builder_button = (
            VerticalButton("Builder")
        )

        self.device_builder_button = (
            VerticalButton("Device Builder")
        )

        self.calculate_button = (
            VerticalButton("Calculate")
        )

        self.analyze_button = (
            VerticalButton("Analyze")
        )

        nav_layout.addWidget(
            self.builder_button
        )

        nav_layout.addWidget(
            self.device_builder_button
        )

        nav_layout.addWidget(
            self.calculate_button
        )

        nav_layout.addWidget(
            self.analyze_button
        )

        nav_layout.addStretch()

        project_label = QLabel(
            self.project.name
        )

        project_label.setObjectName(
            "projectLabel"
        )

        project_label.setWordWrap(True)

        nav_layout.addWidget(
            project_label
        )

        # --------------------------------------------------------
        # Workspaces
        # --------------------------------------------------------

        self.workspace = QStackedWidget()

        self.workspace.setObjectName(
            "workspace"
        )

        # THIS IS THE IMPORTANT PART:
        # We now instantiate the real Builder.

        self.builder = Builder(
            self.project
        )

        # --------------------------------------------------------
        # Contextual Builder toolbar
        #
        # This belongs to ProjectWindow because ProjectWindow is
        # the QMainWindow. It is shown only while Builder is
        # active.
        # --------------------------------------------------------

        self._build_builder_toolbar()

        self.device_builder = DeviceBuilderWorkspace(
            self.project
        )
        self.device_builder.history_changed.connect(
            self._update_active_history_actions
        )

        self.calculator = CalculateWorkspace(
            self.project
        )

        self.analyzer = (
            WorkspacePlaceholder(
                "Analyze",
                "Result analysis and plotting.",
            )
        )

        self.workspace.addWidget(
            self.builder
        )

        self.workspace.addWidget(
            self.device_builder
        )

        self.workspace.addWidget(
            self.calculator
        )

        self.workspace.addWidget(
            self.analyzer
        )

        # --------------------------------------------------------
        # Navigation
        # --------------------------------------------------------

        self.builder_button.clicked.connect(
            lambda: self._select_vertical(0)
        )

        self.device_builder_button.clicked.connect(
            lambda: self._select_vertical(1)
        )

        self.calculate_button.clicked.connect(
            lambda: self._select_vertical(2)
        )

        self.analyze_button.clicked.connect(
            lambda: self._select_vertical(3)
        )

        self._select_vertical(0)

        main_layout.addWidget(
            navigation
        )

        main_layout.addWidget(
            self.workspace,
            1,
        )

        # --------------------------------------------------------
        # Status
        # --------------------------------------------------------

        status = QStatusBar()

        status.showMessage(
            "Ready"
        )

        self.setStatusBar(status)

    # ============================================================
    # Navigation
    # ============================================================

    def _select_vertical(self, index):

        self.workspace.setCurrentIndex(
            index
        )

        buttons = [
            self.builder_button,
            self.device_builder_button,
            self.calculate_button,
            self.analyze_button,
        ]

        for i, button in enumerate(buttons):

            button.setChecked(
                i == index
            )

        # --------------------------------------------------------
        # Contextual toolbar
        #
        # 0 = Builder
        # 1 = Device Builder
        # 2 = Calculate
        # 3 = Analyze
        # --------------------------------------------------------

        if hasattr(
            self,
            "builder_toolbar",
        ):

            self.builder_toolbar.setVisible(
                index == 0
            )
            self._update_active_history_actions()

    def _undo_active_workspace(self, *_):
        if self.workspace.currentIndex() == 1:
            return self.device_builder.undo()
        if self.workspace.currentIndex() == 0:
            return self.builder._qs_undo()
        return False

    def _redo_active_workspace(self, *_):
        if self.workspace.currentIndex() == 1:
            return self.device_builder.redo()
        if self.workspace.currentIndex() == 0:
            return self.builder._qs_redo()
        return False

    def _update_active_history_actions(self, *_):
        if not hasattr(self, "undo_action"):
            return
        index = self.workspace.currentIndex()
        if index == 1:
            self.undo_action.setEnabled(self.device_builder.can_undo())
            self.redo_action.setEnabled(self.device_builder.can_redo())
        elif index == 0:
            self.builder._update_history_actions()
        else:
            self.undo_action.setEnabled(False)
            self.redo_action.setEnabled(False)

    # ============================================================
    # Contextual Builder toolbar
    # ============================================================

    def _build_builder_toolbar(self):

        self.builder_toolbar = QToolBar("Builder Tools", self)
        self.builder_toolbar.setObjectName("builderToolbar")
        self.builder_toolbar.setMovable(False)
        self.builder_toolbar.setFloatable(False)
        self.builder_toolbar.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextOnly
        )

        def action(text, tooltip, callback=None, checkable=False):
            item = QAction(text, self)
            item.setToolTip(tooltip)
            item.setStatusTip(tooltip)
            item.setCheckable(checkable)
            if callback is not None:
                item.triggered.connect(callback)
            self.builder_toolbar.addAction(item)
            return item

        self.undo_action = action(
            "Undo", "Undo in the active workspace",
            self._undo_active_workspace
        )
        self.undo_action.setShortcut(QKeySequence("Ctrl+Z"))
        self.undo_action.setEnabled(False)

        self.redo_action = action(
            "Redo", "Redo in the active workspace",
            self._redo_active_workspace
        )
        self.redo_action.setShortcuts(
            [QKeySequence("Ctrl+Shift+Z"), QKeySequence("Ctrl+Y")]
        )
        self.redo_action.setEnabled(False)

        self.builder_toolbar.addSeparator()
        action("Reset", "Reset the 3D structure view",
               self.builder.viewport.reset_view)
        for axis in ("X", "Y", "Z"):
            action(
                axis, f"View along Cartesian {axis} axis",
                lambda checked=False, a=axis:
                    self.builder.viewport.set_view(a)
            )

        self.builder_toolbar.addSeparator()
        for name in ("X*", "Y*", "Z*"):
            action(
                name, f"View along reciprocal lattice vector {name}",
                lambda checked=False, n=name:
                    self.builder._set_crystallographic_view(n)
            )

        self.builder_toolbar.addSeparator()
        action("(hkl)", "View along a Miller-plane normal",
               self.builder._view_miller_plane)

        self.builder_toolbar.addSeparator()
        projection_group = QActionGroup(self)
        projection_group.setExclusive(True)
        self.perspective_action = action(
            "Perspective", "Use perspective projection", checkable=True
        )
        self.orthographic_action = action(
            "Orthographic", "Use orthographic projection", checkable=True
        )
        projection_group.addAction(self.perspective_action)
        projection_group.addAction(self.orthographic_action)
        self.orthographic_action.setChecked(
            self.builder.viewport.projection_mode == "orthographic"
        )
        self.perspective_action.setChecked(
            self.builder.viewport.projection_mode == "perspective"
        )
        self.perspective_action.triggered.connect(
            lambda: self.builder._set_projection_mode("Perspective")
        )
        self.orthographic_action.triggered.connect(
            lambda: self.builder._set_projection_mode("Orthographic")
        )

        self.builder_toolbar.addSeparator()
        self.bonds_action = action(
            "Bonds", "Show or hide bonds", checkable=True
        )
        self.bonds_action.setChecked(self.builder.viewport.show_bonds)
        self.bonds_action.triggered.connect(
            lambda checked: self.builder._toggle_bonds(
                Qt.CheckState.Checked.value if checked
                else Qt.CheckState.Unchecked.value
            )
        )
        self.cell_action = action(
            "Cell", "Show or hide the unit cell", checkable=True
        )
        self.cell_action.setChecked(self.builder.viewport.show_cell)
        self.cell_action.triggered.connect(
            lambda checked: self.builder._toggle_cell(
                Qt.CheckState.Checked.value if checked
                else Qt.CheckState.Unchecked.value
            )
        )
        self.builder_toolbar.addAction(self._make_labels_menu().menuAction())
        action(
            "Species...", "Open species visibility controls in Builder View",
            self._focus_species_controls
        )

        self.builder_toolbar.addSeparator()
        select_action = action(
            "Select", "Select atoms with the existing viewport selection behavior",
            checkable=True
        )
        select_action.setChecked(True)
        action("Center", "Center the view on the selected atom",
               self.builder._center_on_selected)
        action("Atom Info", "Show selected atom information",
               self._focus_selected_info)

        self.builder_toolbar.addSeparator()
        action("Measure", "Open measurement tools", self._focus_measure_tab)
        self.builder_toolbar.addAction(self._make_periodic_menu().menuAction())

        self.builder_toolbar.addSeparator()
        self.background_action = self._make_background_menu().menuAction()
        self.background_action.setToolTip("Choose the Builder viewport background")
        self.background_action.setStatusTip("Choose the Builder viewport background")
        self.builder_toolbar.addAction(self.background_action)

        action("Export", "Export the current Builder viewport as a PNG",
               self.builder._export_view)

        self.fullscreen_action = action(
            "F11", "Toggle true fullscreen", self.toggle_fullscreen, checkable=True
        )
        self.fullscreen_action.setShortcut(QKeySequence("F11"))

        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.builder_toolbar)
        self.builder_toolbar.setVisible(True)
        self._update_fullscreen_action()
        self.builder._update_history_actions()

    def _make_labels_menu(self):
        from PySide6.QtWidgets import QMenu
        menu = QMenu("Labels", self)
        group = QActionGroup(menu)
        group.setExclusive(True)
        for title in ("Off", "Element", "Index", "Element + Index"):
            item = QAction(title, menu)
            item.setCheckable(True)
            item.setStatusTip(f"Display atom labels as {title.lower()}")
            item.setChecked(
                (title == "Element" and self.builder.viewport.label_mode == "element")
                or (title == "Off" and self.builder.viewport.label_mode == "off")
                or (title == "Index" and self.builder.viewport.label_mode == "index")
                or (title == "Element + Index" and self.builder.viewport.label_mode == "element_index")
            )
            item.triggered.connect(
                lambda checked=False, value=title:
                    self.builder._set_label_mode(value)
            )
            group.addAction(item)
            menu.addAction(item)
        return menu

    def _make_periodic_menu(self):
        from PySide6.QtWidgets import QMenu
        menu = QMenu("Periodic", self)
        for title, values in (
            ("1 x 1 x 1", (1, 1, 1)),
            ("2 x 2 x 1", (2, 2, 1)),
            ("2 x 2 x 2", (2, 2, 2)),
            ("3 x 3 x 1", (3, 3, 1)),
        ):
            item = QAction(title, menu)
            item.setStatusTip(f"Display periodic images: {title}")
            item.triggered.connect(
                lambda checked=False, v=values:
                    self.builder.viewport.set_periodic_display(*v)
            )
            menu.addAction(item)
        return menu

    def _make_background_menu(self):
        from PySide6.QtWidgets import QMenu
        menu = QMenu("Background", self)
        dark = QAction("Default Dark", menu)
        dark.triggered.connect(
            lambda: self._set_builder_background(QColor("#0D0F13"))
        )
        white = QAction("White", menu)
        white.triggered.connect(
            lambda: self._set_builder_background(QColor("#FFFFFF"))
        )
        custom = QAction("Custom Color...", menu)
        custom.triggered.connect(self._choose_builder_background)
        menu.addActions((dark, white, custom))
        return menu

    def _set_builder_background(self, color):
        self.builder.viewport.set_background_color(color)

    def _choose_builder_background(self):
        color = QColorDialog.getColor(
            self.builder.viewport.background_color,
            self,
            "Choose Viewer Background",
        )
        if color.isValid():
            self._set_builder_background(color)

    def _focus_builder_tab(self, index):
        tabs = self.builder.findChild(QTabWidget)
        if tabs is not None:
            tabs.setCurrentIndex(index)

    def _focus_species_controls(self):
        self._focus_builder_tab(0)
        if hasattr(self.builder, "species_group"):
            self.builder.species_group.setFocus()

    def _focus_selected_info(self):
        self._focus_builder_tab(0)
        if hasattr(self.builder, "selected_info"):
            self.builder.selected_info.setFocus()

    def _focus_measure_tab(self):
        self._focus_builder_tab(2)

    def _update_fullscreen_action(self):
        if hasattr(self, "fullscreen_action"):
            self.fullscreen_action.setChecked(self.isFullScreen())

    def toggle_fullscreen(self):
        if self.isFullScreen():
            prior = getattr(self, "_fullscreen_previous_state", "maximized")
            self.showNormal()
            if prior == "maximized":
                self.showMaximized()
            self._fullscreen_previous_state = None
        else:
            self._fullscreen_previous_state = (
                "maximized" if self.isMaximized() else "normal"
            )
            self.showFullScreen()
        self._update_fullscreen_action()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F11:
            self.toggle_fullscreen()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape and self.isFullScreen():
            self.toggle_fullscreen()
            event.accept()
            return
        super().keyPressEvent(event)

    # ============================================================
    # File menu
    # ============================================================

    def _build_menu(self):

        file_menu = self.menuBar().addMenu(
            "File"
        )

        new_action = QAction(
            "New Project",
            self,
        )

        new_action.setShortcut("Ctrl+N")

        new_action.triggered.connect(
            self._new_project
        )

        open_action = QAction(
            "Open Project...",
            self,
        )

        open_action.setShortcut("Ctrl+O")

        open_action.triggered.connect(
            self._open_project
        )

        save_action = QAction(
            "Save Project",
            self,
        )

        save_action.setShortcut("Ctrl+S")

        save_action.triggered.connect(
            self._save_project
        )

        save_as_action = QAction(
            "Save Project As...",
            self,
        )

        save_as_action.triggered.connect(
            self._save_project_as
        )

        close_action = QAction(
            "Close Project",
            self,
        )

        close_action.triggered.connect(
            self._close_project
        )

        exit_action = QAction(
            "Exit Quantum Studio",
            self,
        )

        exit_action.setShortcut("Ctrl+Q")

        exit_action.triggered.connect(
            self._exit_application
        )

        file_menu.addAction(
            new_action
        )

        file_menu.addAction(
            open_action
        )

        file_menu.addSeparator()

        file_menu.addAction(
            save_action
        )

        file_menu.addAction(
            save_as_action
        )

        file_menu.addSeparator()

        file_menu.addAction(
            close_action
        )

        file_menu.addSeparator()

        file_menu.addAction(
            exit_action
        )

    # ============================================================
    # Save
    # ============================================================

    def _save_project(self):

        if self.project.file_path is None:

            return self._save_project_as()

        try:

            self.project.save()

        except Exception as error:

            QMessageBox.critical(
                self,
                "Save Failed",
                str(error),
            )

            return

        self.setWindowTitle(
            self._window_title()
        )

        self.statusBar().showMessage(
            "Project saved.",
            3000,
        )

    def _save_project_as(self):

        default_path = (
            str(self.project.file_path)
            if self.project.file_path
            else self.project.name
        )

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Quantum Studio Project",
            default_path,
            "Quantum Studio Projects (*.qs)",
        )

        if not file_path:
            return

        if not file_path.endswith(".qs"):
            file_path += ".qs"

        try:

            self.project.save(
                file_path
            )

        except Exception as error:

            QMessageBox.critical(
                self,
                "Save Failed",
                str(error),
            )

            return

        self.setWindowTitle(
            self._window_title()
        )

    # ============================================================
    # Project switching
    # ============================================================

    def _new_project(self):

        if not self._confirm_unsaved():
            return

        from frontend.app.project_hub import (
            NewProjectDialog,
        )

        dialog = NewProjectDialog(self)

        if dialog.exec() != dialog.DialogCode.Accepted:
            return

        project = dialog.get_project()

        if project.file_path.exists():

            QMessageBox.warning(
                self,
                "Project Already Exists",
                f"{project.file_path}",
            )

            return

        project.save()

        new_window = ProjectWindow(
            project
        )

        new_window.showMaximized()

        self._allow_close = True

        self.close()

    def _open_project(self):

        if not self._confirm_unsaved():
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Quantum Studio Project",
            str(Path.home()),
            "Quantum Studio Projects (*.qs)",
        )

        if not file_path:
            return

        try:

            project = Project.load(
                file_path
            )

        except Exception as error:

            QMessageBox.critical(
                self,
                "Unable to Open Project",
                str(error),
            )

            return

        new_window = ProjectWindow(
            project
        )

        new_window.showMaximized()

        self._allow_close = True

        self.close()

    # ============================================================
    # Close
    # ============================================================

    def _close_project(self):

        if not self._confirm_unsaved():
            return

        self._allow_close = True

        self.close()

    def _exit_application(self):

        if not self._confirm_unsaved():
            return

        self._allow_close = True

        QApplication.quit()

    # ============================================================
    # Unsaved changes
    # ============================================================

    def _confirm_unsaved(self):

        if not self.project.modified:
            return True

        result = QMessageBox.question(
            self,
            "Unsaved Changes",
            f"Save changes to '{self.project.name}'?",
            (
                QMessageBox.StandardButton.Save
                |
                QMessageBox.StandardButton.Discard
                |
                QMessageBox.StandardButton.Cancel
            ),
        )

        if result == QMessageBox.StandardButton.Save:

            self._save_project()

            return not self.project.modified

        if result == QMessageBox.StandardButton.Discard:
            return True

        return False

    # ============================================================
    # Close event
    # ============================================================

    def closeEvent(self, event):

        if not self._allow_close:

            if not self._confirm_unsaved():

                event.ignore()
                return

        event.accept()

    # ============================================================
    # Styling
    # ============================================================

    def _apply_style(self):

        self.setStyleSheet(
            """
            QMainWindow {
                background: #111318;
            }

            QWidget {
                color: #E8EAF0;
                font-family:
                    "Inter",
                    "Segoe UI",
                    sans-serif;
            }

            QMenuBar {
                background: #17191F;
                color: #C9CDD5;
                border-bottom:
                    1px solid #292C34;
            }

            QMenuBar::item {
                padding: 7px 12px;
            }

            QMenuBar::item:selected {
                background: #252932;
            }

            QMenu {
                background: #1B1E24;
                border:
                    1px solid #30343D;
                color: #E8EAF0;
            }

            QMenu::item {
                padding: 8px 28px 8px 12px;
            }

            QMenu::item:selected {
                background: #2A2E38;
            }

            #navigation {
                background: #17191F;
                border-right:
                    1px solid #292C34;
            }

            #logo {
                font-size: 20px;
                font-weight: 700;
                letter-spacing: 2px;
                color: #FFFFFF;
            }

            VerticalButton {
                background: transparent;
                border: none;
                border-radius: 8px;
                padding: 14px 16px;
                text-align: left;
                font-size: 14px;
                color: #9EA3B0;
            }

            VerticalButton:hover {
                background: #22252D;
                color: #FFFFFF;
            }

            VerticalButton:checked {
                background: #2A2E38;
                color: #FFFFFF;
                font-weight: 600;
            }

            #workspace {
                background: #111318;
            }

            #projectLabel {
                color: #777D89;
                font-size: 12px;
                padding: 6px;
            }

            QStatusBar {
                background: #17191F;
                border-top:
                    1px solid #292C34;
                color: #777D89;
            }


            #builderToolbar {
                background: #15171C;
                border: none;
                border-bottom:
                    1px solid #292C34;
                spacing: 4px;
                padding: 4px 8px;
            }

            #builderToolbar QToolButton {
                background: transparent;
                color: #B9BEC8;
                border: none;
                border-radius: 5px;
                padding: 6px 10px;
            }

            #builderToolbar QToolButton:hover {
                background: #292D36;
                color: #FFFFFF;
            }

            #builderToolbar QToolButton:pressed {
                background: #343944;
            }

            #builderToolbar QToolButton:disabled {
                color: #555A64;
            }
            """
        )
