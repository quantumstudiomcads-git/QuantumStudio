from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from frontend.core.project import Project
from backend.runtime import PRODUCT_NAME, VERSION

from frontend.app.recent_projects import (
    add_recent_project,
    load_recent_projects,
    remove_recent_project,
)


# =================================================================
# New Project Dialog
# =================================================================


class NewProjectDialog(QDialog):

    def __init__(
        self,
        parent=None,
    ):

        super().__init__(parent)

        self.setWindowTitle(
            "New Quantum Studio Project"
        )

        self.setMinimumWidth(
            480
        )

        layout = QVBoxLayout(
            self
        )

        title = QLabel(
            "Create New Project"
        )

        title.setStyleSheet(
            """
            font-size: 18px;
            font-weight: 600;
            """
        )

        layout.addWidget(
            title
        )

        form = QFormLayout()

        self.name = QLineEdit()

        self.name.setPlaceholderText(
            "Project name"
        )

        form.addRow(
            "Project name:",
            self.name,
        )

        self.location = QLineEdit(
            str(Path.home())
        )

        form.addRow(
            "Location:",
            self.location,
        )

        browse = QPushButton(
            "Browse..."
        )

        browse.clicked.connect(
            self._browse
        )

        form.addRow(
            "",
            browse,
        )

        layout.addLayout(
            form
        )

        note = QLabel(
            "Quantum Studio will create a .qs project file "
            "in the selected location."
        )

        note.setWordWrap(True)

        note.setStyleSheet(
            "color: #777D89;"
        )

        layout.addWidget(
            note
        )

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            |
            QDialogButtonBox.StandardButton.Cancel
        )

        buttons.accepted.connect(
            self._accept
        )

        buttons.rejected.connect(
            self.reject
        )

        layout.addWidget(
            buttons
        )

    def _browse(self):

        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Project Location",
            self.location.text(),
        )

        if directory:

            self.location.setText(
                directory
            )

    def _accept(self):

        name = self.name.text().strip()

        if not name:

            QMessageBox.warning(
                self,
                "Project Name Required",
                "Please enter a project name.",
            )

            return

        location = Path(
            self.location.text()
        ).expanduser()

        if not location.exists():

            try:

                location.mkdir(
                    parents=True,
                    exist_ok=True,
                )

            except OSError as error:

                QMessageBox.critical(
                    self,
                    "Invalid Location",
                    str(error),
                )

                return

        self.accept()

    def get_project(self):

        name = self.name.text().strip()

        location = Path(
            self.location.text()
        ).expanduser()

        file_path = (
            location
            / f"{name}.qs"
        )

        return Project(
            name,
            file_path,
        )


# =================================================================
# Project Hub
# =================================================================


class ProjectHub(QMainWindow):

    def __init__(
        self,
    ):

        super().__init__()

        self.setWindowTitle(
            "Quantum Studio"
        )

        self.resize(
            1050,
            700,
        )

        self._build_ui()

        self._load_recent_projects()

        self._apply_style()

    # ============================================================
    # UI
    # ============================================================

    def _build_ui(self):

        central = QWidget()

        self.setCentralWidget(
            central
        )

        layout = QVBoxLayout(
            central
        )

        layout.setContentsMargins(
            80,
            55,
            80,
            45,
        )

        layout.setSpacing(
            20
        )

        # --------------------------------------------------------
        # Header
        # --------------------------------------------------------

        logo = QLabel(
            "QUANTUM STUDIO"
        )

        logo.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        logo.setObjectName(
            "hubLogo"
        )

        layout.addWidget(
            logo
        )

        subtitle = QLabel(
            "Project Hub"
        )

        subtitle.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        subtitle.setObjectName(
            "hubSubtitle"
        )

        layout.addWidget(
            subtitle
        )

        layout.addSpacing(
            20
        )

        # --------------------------------------------------------
        # Main actions
        # --------------------------------------------------------

        actions = QHBoxLayout()

        actions.setSpacing(
            18
        )

        self.new_button = QPushButton(
            "New Project"
        )

        self.open_button = QPushButton(
            "Open Project"
        )

        for button in (
            self.new_button,
            self.open_button,
        ):

            button.setObjectName(
                "hubAction"
            )

            button.setMinimumHeight(
                115
            )

            button.setCursor(
                Qt.CursorShape.PointingHandCursor
            )

        self.new_button.clicked.connect(
            self._new_project
        )

        self.open_button.clicked.connect(
            self._open_project
        )

        actions.addWidget(
            self.new_button
        )

        actions.addWidget(
            self.open_button
        )

        layout.addLayout(
            actions
        )

        layout.addSpacing(
            18
        )

        # --------------------------------------------------------
        # Recent Projects
        # --------------------------------------------------------

        recent_header = QHBoxLayout()

        recent_title = QLabel(
            "RECENT PROJECTS"
        )

        recent_title.setObjectName(
            "sectionTitle"
        )

        recent_header.addWidget(
            recent_title
        )

        recent_header.addStretch()

        self.clear_button = QPushButton(
            "Clear"
        )

        self.clear_button.setObjectName(
            "smallButton"
        )

        self.clear_button.clicked.connect(
            self._clear_recent
        )

        recent_header.addWidget(
            self.clear_button
        )

        layout.addLayout(
            recent_header
        )

        self.recent_list = QListWidget()

        self.recent_list.setObjectName(
            "recentList"
        )

        self.recent_list.setSpacing(
            4
        )

        self.recent_list.itemDoubleClicked.connect(
            self._open_recent
        )

        layout.addWidget(
            self.recent_list,
            1,
        )

        # --------------------------------------------------------
        # Footer
        # --------------------------------------------------------

        self.product_identity_label = QLabel(
            f"{PRODUCT_NAME} · v{VERSION}"
        )

        self.product_identity_label.setObjectName(
            "footer"
        )

        self.product_identity_label.setAlignment(
            Qt.AlignmentFlag.AlignRight
        )

        layout.addWidget(
            self.product_identity_label
        )

    # ============================================================
    # Recent projects
    # ============================================================

    def _load_recent_projects(self):

        self.recent_list.clear()

        projects = load_recent_projects()

        if not projects:

            empty = QListWidgetItem(
                "No recent projects"
            )

            empty.setFlags(
                Qt.ItemFlag.NoItemFlags
            )

            empty.setTextAlignment(
                Qt.AlignmentFlag.AlignCenter
            )

            self.recent_list.addItem(
                empty
            )

            return

        for project_path in projects:

            path = Path(
                project_path
            )

            try:

                project = Project.load(
                    path
                )

                name = project.name

            except Exception:

                name = path.stem

            item = QListWidgetItem()

            item.setText(
                name
            )

            item.setData(
                Qt.ItemDataRole.UserRole,
                str(path),
            )

            item.setToolTip(
                str(path)
            )

            self.recent_list.addItem(
                item
            )

    # ============================================================
    # New Project
    # ============================================================

    def _new_project(self):

        dialog = NewProjectDialog(
            self
        )

        if (
            dialog.exec()
            != QDialog.DialogCode.Accepted
        ):

            return

        project = dialog.get_project()

        if project.file_path.exists():

            QMessageBox.warning(
                self,
                "Project Already Exists",
                (
                    f"A project already exists at:\n\n"
                    f"{project.file_path}"
                ),
            )

            return

        try:

            project.save()

        except Exception as error:

            QMessageBox.critical(
                self,
                "Project Creation Failed",
                str(error),
            )

            return

        add_recent_project(
            project.file_path
        )

        self._open_workspace(
            project
        )

    # ============================================================
    # Open Project
    # ============================================================

    def _open_project(self):

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Quantum Studio Project",
            str(Path.home()),
            "Quantum Studio Projects (*.qs)",
        )

        if not path:
            return

        self._open_project_path(
            path
        )

    # ============================================================
    # Open Recent
    # ============================================================

    def _open_recent(
        self,
        item,
    ):

        path = item.data(
            Qt.ItemDataRole.UserRole
        )

        if not path:
            return

        self._open_project_path(
            path
        )

    def _open_project_path(
        self,
        path,
    ):

        path = Path(
            path
        )

        if not path.exists():

            remove_recent_project(
                path
            )

            self._load_recent_projects()

            QMessageBox.warning(
                self,
                "Project Not Found",
                (
                    "The project file no longer exists:\n\n"
                    f"{path}"
                ),
            )

            return

        try:

            project = Project.load(
                path
            )

        except Exception as error:

            QMessageBox.critical(
                self,
                "Unable to Open Project",
                str(error),
            )

            return

        add_recent_project(
            path
        )

        self._open_workspace(
            project
        )

    # ============================================================
    # Workspace
    # ============================================================

    def _open_workspace(
        self,
        project,
    ):

        # Import here deliberately to avoid circular imports.
        from frontend.app.project_window import (
            ProjectWindow
        )

        self.workspace = ProjectWindow(
            project
        )

        self.workspace.showMaximized()

        self.close()

    # ============================================================
    # Clear
    # ============================================================

    def _clear_recent(self):

        from frontend.app.recent_projects import (
            clear_recent_projects
        )

        clear_recent_projects()

        self._load_recent_projects()

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

            #hubLogo {
                font-size: 28px;
                font-weight: 700;
                letter-spacing: 4px;
                color: #F2F3F5;
            }

            #hubSubtitle {
                color: #777D89;
                font-size: 13px;
            }

            #hubAction {
                background: #171A21;
                border:
                    1px solid #292D36;
                border-radius: 10px;
                color: #E6E8EC;
                font-size: 15px;
                font-weight: 500;
            }

            #hubAction:hover {
                background: #20242C;
                border-color: #3A3F4A;
            }

            #hubAction:pressed {
                background: #272B34;
            }

            #sectionTitle {
                color: #6F7580;
                font-size: 10px;
                font-weight: 600;
                letter-spacing: 1.4px;
            }

            #recentList {
                background: #171A21;
                border:
                    1px solid #292D36;
                border-radius: 10px;
                padding: 8px;
                outline: none;
            }

            #recentList::item {
                background: transparent;
                border-radius: 7px;
                padding: 14px 16px;
                color: #C8CCD4;
                font-size: 13px;
            }

            #recentList::item:hover {
                background: #22262F;
                color: #FFFFFF;
            }

            #recentList::item:selected {
                background: #292E38;
                color: #FFFFFF;
            }

            #smallButton {
                background: transparent;
                border: none;
                color: #686E79;
                padding: 3px 8px;
            }

            #smallButton:hover {
                color: #C8CCD4;
            }

            #footer {
                color: #555B66;
                font-size: 10px;
            }
            """
        )
