from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from frontend.builder import StructureViewport
from frontend.core.structure_io import StructureIO
from frontend.device_builder.assembly import (
    align_region_centers, align_region_surface, assemble_device,
    detect_inter_region_collisions, fit_device_cell, place_region, repeat_region, set_device_padding,
)
from frontend.device_builder.model import Device, DeviceHistory, DeviceRegion, RegionRole
from frontend.device_builder.ui import PlacementControls, RegionProperties, RegionTree


class DeviceBuilderWorkspace(QWidget):
    """Project-owned Device editor with independent, non-persistent Device history."""

    history_changed = Signal(bool, bool)

    def __init__(self, project=None, parent=None):
        super().__init__(parent)
        self.project = project
        self.device = self._project_device_or_empty()
        self.history = DeviceHistory()
        self.selected_region_id = None

        layout = QHBoxLayout(self)
        panel_scroll = QScrollArea()
        panel_scroll.setWidgetResizable(True)
        panel_scroll.setFixedWidth(390)
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        title = QLabel("DEVICE / REGIONS")
        title.setObjectName("panelTitle")
        panel_layout.addWidget(title)
        self.load_status = QLabel()
        self.load_status.setWordWrap(True)
        self.load_status.setVisible(False)
        if self.project is not None and getattr(self.project, "device_load_error", None):
            self.load_status.setText(self.project.device_load_error)
            self.load_status.setVisible(True)
        panel_layout.addWidget(self.load_status)
        self.history_controls = QWidget()
        history_layout = QHBoxLayout(self.history_controls)
        history_layout.setContentsMargins(0, 0, 0, 0)
        self.undo_button = QPushButton("Undo")
        self.redo_button = QPushButton("Redo")
        history_layout.addWidget(self.undo_button)
        history_layout.addWidget(self.redo_button)
        panel_layout.addWidget(self.history_controls)
        self.region_tree = RegionTree()
        self.properties = RegionProperties()
        self.placement = PlacementControls()
        panel_layout.addWidget(self.region_tree)
        panel_layout.addWidget(self.properties)
        panel_layout.addWidget(self.placement)
        panel_layout.addStretch()
        panel_scroll.setWidget(panel)

        self.viewport = StructureViewport()
        layout.addWidget(panel_scroll)
        layout.addWidget(self.viewport, 1)

        self.region_tree.add_requested.connect(self.add_region_from_file)
        self.region_tree.add_current_requested.connect(self.add_current_builder_structure)
        self.region_tree.remove_requested.connect(self.remove_selected_region)
        self.region_tree.duplicate_requested.connect(self.duplicate_selected_region)
        self.region_tree.selection_changed.connect(self.select_region)
        self.properties.region_changed.connect(self.update_region)
        self.undo_button.clicked.connect(self.undo)
        self.redo_button.clicked.connect(self.redo)
        self._wire_geometry_controls()
        self._update_history_controls()
        self.refresh_preview()

    def _project_device_or_empty(self):
        if self.project is not None:
            device = self.project.get_device()
            if device is not None:
                return device
        return Device(name=f"{getattr(self.project, 'name', 'Untitled')} Device")

    def _attach_device_to_project(self):
        if self.project is not None:
            # Project is the sole persistent owner; calling its public setter
            # also marks every committed Device edit (including undo/redo) dirty.
            self.project.set_device(self.device)

    def _commit_device_edit(self, label, operation):
        before = self.device.to_dict()
        result = operation()
        after = self.device.to_dict()
        if self.history.record(label, before, after):
            self._attach_device_to_project()
            self._update_history_controls()
        self.refresh_preview()
        return result

    def _restore_device_snapshot(self, snapshot):
        self.device = Device.from_dict(snapshot)
        self._attach_device_to_project()
        if self.device.get_region(self.selected_region_id) is None:
            self.selected_region_id = None
        self.refresh_preview()
        self._update_history_controls()

    def _update_history_controls(self):
        can_undo = self.history.can_undo()
        can_redo = self.history.can_redo()
        if hasattr(self, "undo_button"):
            self.undo_button.setEnabled(can_undo)
            self.redo_button.setEnabled(can_redo)
        self.history_changed.emit(can_undo, can_redo)

    def can_undo(self):
        return self.history.can_undo()

    def can_redo(self):
        return self.history.can_redo()

    def undo(self):
        snapshot = self.history.undo()
        if snapshot is None:
            return False
        self._restore_device_snapshot(snapshot)
        return True

    def redo(self):
        snapshot = self.history.redo()
        if snapshot is None:
            return False
        self._restore_device_snapshot(snapshot)
        return True

    def clear_history(self):
        self.history.clear()
        self._update_history_controls()

    def _wire_geometry_controls(self):
        for direction, button in (
            ("above", self.placement.above_button), ("below", self.placement.below_button),
            ("left", self.placement.left_button), ("right", self.placement.right_button),
        ):
            button.clicked.connect(lambda checked=False, value=direction: self._run_geometry(lambda: self.place_selected(value)))
        for axes, button in (
            ("X", self.placement.align_x_button), ("Y", self.placement.align_y_button),
            ("Z", self.placement.align_z_button), ("XY", self.placement.align_xy_button),
            ("XYZ", self.placement.align_xyz_button),
        ):
            button.clicked.connect(lambda checked=False, value=axes: self._run_geometry(lambda: self.align_selected_centers(value)))
        for surface, button in (
            ("top", self.placement.align_top_button), ("bottom", self.placement.align_bottom_button),
            ("left", self.placement.align_left_button), ("right", self.placement.align_right_button),
        ):
            button.clicked.connect(lambda checked=False, value=surface: self._run_geometry(lambda: self.align_selected_surface(value)))
        self.placement.repeat_button.clicked.connect(lambda: self._run_geometry(self.repeat_selected_region))
        for editor in self.placement.padding:
            editor.editingFinished.connect(lambda: self._run_geometry(self.set_device_padding_from_controls))
        self.placement.fit_cell_button.clicked.connect(lambda: self._run_geometry(self.fit_cell_to_device))
        self.placement.check_overlaps_button.clicked.connect(self.check_overlaps)

    def add_region_from_structure(self, structure, name=None):
        """Add an independent source copy through the Device history boundary."""
        added = []

        def operation():
            region = DeviceRegion(
                source_structure=structure.copy(),
                name=name or structure.name or "Region",
                role=RegionRole.OTHER,
            )
            self.device.add_region(region)
            added.append(region)
            return region

        region = self._commit_device_edit("Add Region", operation)
        self.selected_region_id = region.id
        self.refresh_preview()
        return region

    def add_region_from_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Add Device Region", str(Path.home()),
            "Structures (*.cif *.xyz *.vasp *.xsf *.pdb *.mol *.sdf *.res *.gen POSCAR CONTCAR);;All Files (*)",
        )
        if not path:
            return None
        try:
            structure = StructureIO.read_structure(path)
            return self.add_region_from_structure(structure, structure.name or Path(path).stem)
        except Exception as error:
            QMessageBox.critical(self, "Add Device Region Failed", str(error))
            return None

    def add_current_builder_structure(self):
        """Copy Project's canonical structure through its public Project API."""
        if self.project is None or not getattr(self.project, "structure", None):
            QMessageBox.information(self, "No Builder Structure", "There is no active Builder structure to add.")
            return None
        try:
            structure = self.project.get_structure()
            if not structure.atoms:
                raise ValueError("The active Builder structure contains no atoms.")
            return self.add_region_from_structure(structure, structure.name or "Current Builder Structure")
        except Exception as error:
            QMessageBox.critical(self, "Add Current Builder Structure Failed", str(error))
            return None

    def remove_selected_region(self):
        if self.selected_region_id is None:
            return False
        region_id = self.selected_region_id

        def operation():
            return self.device.remove_region(region_id)

        removed = self._commit_device_edit("Remove Region", operation)
        if removed:
            self.selected_region_id = None
            self.refresh_preview()
        return removed

    def duplicate_selected_region(self):
        if self.selected_region_id is None:
            return None
        duplicate = self._commit_device_edit(
            "Duplicate Region", lambda: self.device.duplicate_region(self.selected_region_id)
        )
        self.selected_region_id = duplicate.id
        self.refresh_preview()
        return duplicate

    def select_region(self, region_id):
        self.selected_region_id = region_id
        self.properties.set_region(self.device.get_region(region_id))
        self.placement.set_device(self.device, region_id)

    def update_region(self, values):
        region = self.device.get_region(values["id"])
        if region is None:
            return

        def operation():
            region.name = values["name"]
            region.role = RegionRole(values["role"])
            region.visible = bool(values["visible"])
            region.translation = tuple(float(value) for value in values["translation"])
            region.rotation = tuple(float(value) for value in values["rotation"])

        self._commit_device_edit("Edit Region Properties", operation)

    def _moving_and_reference(self, reference_id=None):
        if self.selected_region_id is None:
            raise ValueError("Select a moving region first.")
        moving = self.device.get_region(self.selected_region_id)
        reference_id = self.placement.reference_region_id() if reference_id is None else reference_id
        reference = self.device.get_region(reference_id)
        if moving is None or reference is None:
            raise ValueError("Select a valid reference region.")
        if moving.id == reference.id:
            raise ValueError("The moving and reference regions must be different.")
        return moving, reference

    def place_selected(self, direction, reference_id=None, gap=None):
        moving, reference = self._moving_and_reference(reference_id)
        return self._commit_device_edit(
            f"Place Region {str(direction).title()}",
            lambda: place_region(moving, reference, direction, self.placement.gap.value() if gap is None else gap),
        )

    def align_selected_centers(self, axes, reference_id=None):
        moving, reference = self._moving_and_reference(reference_id)
        return self._commit_device_edit(
            f"Align Centers {str(axes).upper()}", lambda: align_region_centers(moving, reference, axes)
        )

    def align_selected_surface(self, surface, reference_id=None):
        moving, reference = self._moving_and_reference(reference_id)
        return self._commit_device_edit(
            f"Align Surface {str(surface).title()}", lambda: align_region_surface(moving, reference, surface)
        )

    def repeat_selected_region(self, counts=None):
        if self.selected_region_id is None:
            raise ValueError("Select a region to repeat.")
        nx, ny, nz = self.placement.repeat_values() if counts is None else counts
        return self._commit_device_edit(
            "Repeat Region", lambda: repeat_region(self.device, self.selected_region_id, nx, ny, nz)
        )

    def set_device_padding(self, padding):
        return self._commit_device_edit(
            "Change Device Padding", lambda: set_device_padding(self.device, padding)
        )

    def set_device_padding_from_controls(self):
        return self.set_device_padding(self.placement.padding_values())

    def fit_cell_to_device(self, padding=None):
        return self._commit_device_edit(
            "Fit Device Cell", lambda: fit_device_cell(
                self.device, self.placement.padding_values() if padding is None else padding
            )
        )

    def check_overlaps(self, show_dialog=True):
        collisions = detect_inter_region_collisions(self.device)
        if show_dialog:
            if collisions:
                names = {region.id: region.name for region in self.device.regions}
                involved = sorted({names.get(item.region_a_id, item.region_a_id) for item in collisions} |
                                  {names.get(item.region_b_id, item.region_b_id) for item in collisions})
                minimum = min(item.distance for item in collisions)
                QMessageBox.warning(
                    self, "Possible Inter-region Overlaps",
                    f"{len(collisions)} possible inter-region atomic overlap(s) detected.\n"
                    f"Regions: {', '.join(involved)}\nMinimum distance: {minimum:.3f} Å",
                )
            else:
                QMessageBox.information(self, "Overlap Check", "No inter-region atomic overlaps detected.")
        return collisions

    def _run_geometry(self, operation):
        try:
            return operation()
        except Exception as error:
            QMessageBox.warning(self, "Device Geometry", str(error))
            return None

    def refresh_preview(self):
        assembly = assemble_device(self.device)
        self.viewport.set_structure(assembly.structure)
        self.region_tree.set_device(self.device, self.selected_region_id)
        self.properties.set_region(self.device.get_region(self.selected_region_id))
        self.placement.set_device(self.device, self.selected_region_id)
