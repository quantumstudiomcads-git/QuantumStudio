from pathlib import Path
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QMessageBox, QVBoxLayout, QWidget
from frontend.builder import StructureViewport
from frontend.core.structure_io import StructureIO
from frontend.device_builder.assembly import assemble_device
from frontend.device_builder.model import Device, DeviceRegion, RegionRole
from frontend.device_builder.ui import RegionProperties, RegionTree

class DeviceBuilderWorkspace(QWidget):
    """In-memory Device Region editor using the existing StructureViewport."""

    def __init__(self, project=None, parent=None):
        super().__init__(parent)
        self.project = project
        self.device = Device(name=f"{getattr(project, 'name', 'Untitled')} Device")
        self.selected_region_id = None
        layout = QHBoxLayout(self)
        panel = QWidget()
        panel.setFixedWidth(340)
        panel_layout = QVBoxLayout(panel)
        title = QLabel("DEVICE / REGIONS")
        title.setObjectName("panelTitle")
        panel_layout.addWidget(title)
        self.region_tree = RegionTree()
        self.properties = RegionProperties()
        panel_layout.addWidget(self.region_tree, 1)
        panel_layout.addWidget(self.properties)
        self.viewport = StructureViewport()
        layout.addWidget(panel)
        layout.addWidget(self.viewport, 1)
        self.region_tree.add_requested.connect(self.add_region_from_file)
        self.region_tree.remove_requested.connect(self.remove_selected_region)
        self.region_tree.duplicate_requested.connect(self.duplicate_selected_region)
        self.region_tree.selection_changed.connect(self.select_region)
        self.properties.region_changed.connect(self.update_region)
        self.refresh_preview()

    def add_region_from_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Add Device Region", str(Path.home()),
            "Structures (*.cif *.xyz *.vasp *.xsf *.pdb *.mol *.sdf *.res *.gen POSCAR CONTCAR);;All Files (*)",
        )
        if not path:
            return
        try:
            structure = StructureIO.read_structure(path)
            region = DeviceRegion(source_structure=structure.copy(), name=structure.name or Path(path).stem, role=RegionRole.OTHER)
            self.device.add_region(region)
            self.selected_region_id = region.id
            self.refresh_preview()
        except Exception as error:
            QMessageBox.critical(self, "Add Device Region Failed", str(error))

    def remove_selected_region(self):
        if self.selected_region_id is None:
            return
        self.device.remove_region(self.selected_region_id)
        self.selected_region_id = None
        self.refresh_preview()

    def duplicate_selected_region(self):
        if self.selected_region_id is None:
            return
        duplicate = self.device.duplicate_region(self.selected_region_id)
        self.selected_region_id = duplicate.id
        self.refresh_preview()

    def select_region(self, region_id):
        self.selected_region_id = region_id
        self.properties.set_region(self.device.get_region(region_id))

    def update_region(self, values):
        region = self.device.get_region(values["id"])
        if region is None:
            return
        region.name = values["name"]
        region.role = RegionRole(values["role"])
        region.visible = bool(values["visible"])
        region.translation = tuple(float(value) for value in values["translation"])
        region.rotation = tuple(float(value) for value in values["rotation"])
        self.refresh_preview()

    def refresh_preview(self):
        assembly = assemble_device(self.device)
        self.viewport.set_structure(assembly.structure)
        self.region_tree.set_device(self.device, self.selected_region_id)
        self.properties.set_region(self.device.get_region(self.selected_region_id))
