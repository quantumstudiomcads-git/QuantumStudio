"""Small shared visual token layer for active Quantum Studio windows."""

SPACE_SMALL = 6
SPACE_MEDIUM = 10
SPACE_LARGE = 16
CONTROL_HEIGHT = 30
ACCENT = "#36B8E8"
GRAPHITE = "#111318"
PANEL = "#171A21"
BORDER = "#30343D"
TEXT = "#E8EAF0"
MUTED = "#858C98"


def application_stylesheet() -> str:
    return f"""
    QWidget {{ color: {TEXT}; font-family: \"Segoe UI\", sans-serif; font-size: 10pt; }}
    QMainWindow, QDialog {{ background: {GRAPHITE}; }}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QListWidget,
    QTableView, QTreeView {{ background: {PANEL}; color: {TEXT}; border: 1px solid {BORDER};
        min-height: {CONTROL_HEIGHT}px; selection-background-color: #263A47; }}
    QPushButton, QToolButton {{ background: #252932; color: {TEXT}; border: 1px solid {BORDER};
        padding: 6px 11px; min-height: 18px; border-radius: 4px; }}
    QPushButton:hover, QToolButton:hover {{ background: #303640; border-color: #4A6070; }}
    QPushButton:pressed, QToolButton:pressed {{ background: #1F2830; }}
    QPushButton:focus, QToolButton:focus, QLineEdit:focus, QComboBox:focus {{ border: 1px solid {ACCENT}; }}
    QPushButton:disabled, QToolButton:disabled {{ color: #626975; background: #1B1E24; border-color: #282C34; }}
    QGroupBox {{ border: 1px solid {BORDER}; margin-top: 10px; padding-top: 10px; }}
    QGroupBox::title {{ color: {MUTED}; subcontrol-origin: margin; left: 8px; padding: 0 4px; }}
    QMenuBar, QMenu {{ background: {PANEL}; color: {TEXT}; }}
    QMenu::item:selected {{ background: #263A47; }}
    QToolTip {{ background: {PANEL}; color: {TEXT}; border: 1px solid #4A6070; }}
    """
