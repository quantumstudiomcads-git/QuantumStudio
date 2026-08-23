from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget
from frontend.device_builder.model.roles import role_label

class RegionTree(QWidget):
    selection_changed = Signal(str)
    add_requested = Signal()
    remove_requested = Signal()
    duplicate_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Region", "Role", "Visible"])
        self.tree.itemSelectionChanged.connect(self._emit_selection)
        layout.addWidget(self.tree)
        actions = QHBoxLayout()
        self.add_button = QPushButton("+ Add Region")
        self.remove_button = QPushButton("- Remove")
        self.duplicate_button = QPushButton("Duplicate")
        self.add_button.clicked.connect(self.add_requested)
        self.remove_button.clicked.connect(self.remove_requested)
        self.duplicate_button.clicked.connect(self.duplicate_requested)
        actions.addWidget(self.add_button)
        actions.addWidget(self.remove_button)
        actions.addWidget(self.duplicate_button)
        layout.addLayout(actions)

    def set_device(self, device, selected_id=None):
        self.tree.blockSignals(True)
        self.tree.clear()
        for region in device.regions:
            item = QTreeWidgetItem((region.name, role_label(region.role), "Shown" if region.visible else "Hidden"))
            item.setData(0, 32, region.id)
            self.tree.addTopLevelItem(item)
            if region.id == selected_id:
                self.tree.setCurrentItem(item)
        self.tree.blockSignals(False)

    def selected_region_id(self):
        item = self.tree.currentItem()
        return item.data(0, 32) if item is not None else None

    def _emit_selection(self):
        region_id = self.selected_region_id()
        if region_id is not None:
            self.selection_changed.emit(region_id)
