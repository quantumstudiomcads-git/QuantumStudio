"""Small lazy Qt model for Analyze tabular scientific data."""
from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QTableView


class ScientificTableModel(QAbstractTableModel):
    """Keeps source rows as data; it never allocates a QTableWidgetItem per cell."""
    def __init__(self, headers=(), rows=(), parent=None):
        super().__init__(parent)
        self.headers = tuple(headers)
        self.rows = rows

    def set_data(self, headers, rows):
        self.beginResetModel()
        self.headers = tuple(headers)
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.headers)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role not in {Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole}:
            return None
        try:
            value = self.rows[index.row()][index.column()]
        except (IndexError, TypeError):
            return "—"
        if value is None:
            return "—"
        try:
            if value != value:
                return "Unavailable"
        except Exception:
            pass
        return str(value)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal and section < len(self.headers):
            return self.headers[section]
        return super().headerData(section, orientation, role)


class ScientificTableView(QTableView):
    """Read-only table with normal selected-cell clipboard copy."""
    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Copy):
            indexes=self.selectionModel().selectedIndexes() if self.selectionModel() else []
            if indexes:
                rows={}
                for index in indexes: rows.setdefault(index.row(), {})[index.column()]=str(index.data() or "")
                text="\n".join("\t".join(row[column] for column in sorted(row)) for _,row in sorted(rows.items()))
                QApplication.clipboard().setText(text)
                event.accept(); return
        super().keyPressEvent(event)
