import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np
from PySide6.QtWidgets import QApplication

from frontend.app.project_window import ProjectWindow
from frontend.core import Atom, Project, Structure
from frontend.device_builder import DeviceBuilderWorkspace
from frontend.device_builder.model import Device, DeviceRegion, RegionRole

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def app():
    return QApplication.instance() or QApplication([])


def source(name="Source", element="C", offset=(0.0, 0.0, 0.0)):
    x, y, z = offset
    result = Structure(
        [Atom(element, x, y, z), Atom(element, x + 1.0, y + 0.5, z + 0.25)],
        [[4.0, 0.0, 0.0], [0.0, 5.0, 0.0], [0.0, 0.0, 6.0]],
        name=name,
    )
    result.periodic = [True, False, True]
    result.history = ["Imported"]
    return result


class DevicePersistenceTests(unittest.TestCase):
    def test_old_project_without_device_loads_unchanged(self):
        original = source("Legacy", "Si")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.qs"
            path.write_text(json.dumps({
                "format": "qstudio", "version": "0.2", "project": {"name": "Legacy"},
                "structure": original.to_dict(), "calculator": {}, "workflows": {}, "results": {}, "analysis": {},
            }))
            loaded = Project.load(path)
        self.assertIsNone(loaded.get_device())
        self.assertIsNone(loaded.device_load_error)
        self.assertEqual(loaded.get_structure().to_dict(), original.to_dict())
        loaded.set_structure(loaded.get_structure().copy())
        self.assertTrue(loaded.modified)

    def test_device_round_trip_preserves_ids_sources_transforms_and_assembly(self):
        first_source = source("First", "C")
        second_source = source("Second", "O", (2.0, 1.0, 0.0))
        device = Device(
            id="device-identity", name="Persistent Device",
            cell=[[20.0, 0.0, 0.0], [0.0, 21.0, 0.0], [0.0, 0.0, 22.0]],
            periodic=(True, False, True), transport_direction="X",
            padding=(1.5, 2.5, 3.5), origin_offset=(4.0, 5.0, 6.0), metadata={"kind": "test"},
        )
        first = device.add_region(DeviceRegion(
            id="region-first", source_structure=first_source, name="Electrode", role=RegionRole.ELECTRODE,
            translation=(1.0, 2.0, 3.0), rotation=(0.0, 0.0, 15.0), visible=True, metadata={"side": "left"},
        ))
        second = device.add_region(DeviceRegion(
            id="region-second", source_structure=second_source, name="Channel", role=RegionRole.CHANNEL,
            translation=(-2.0, 0.5, 4.0), rotation=(5.0, 10.0, 0.0), visible=False, metadata={"side": "center"},
        ))
        before_payload = device.to_dict()
        before_assembly = device.assemble().to_dict()
        project = Project("Persistent Project")
        project.set_structure(source("Builder", "Si"))
        project.set_device(device)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "device.qs"
            project.save(path)
            loaded = Project.load(path)
        restored = loaded.get_device()
        self.assertIsNotNone(restored)
        self.assertIsNone(loaded.device_load_error)
        self.assertEqual(restored.to_dict(), before_payload)
        self.assertEqual(restored.id, device.id)
        self.assertEqual([region.id for region in restored.regions], [first.id, second.id])
        self.assertEqual(restored.regions[0].source_structure.to_dict(), first_source.to_dict())
        self.assertEqual(restored.regions[1].source_structure.to_dict(), second_source.to_dict())
        self.assertEqual(restored.assemble().to_dict(), before_assembly)

    def test_malformed_optional_device_does_not_block_project_load(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "malformed.qs"
            path.write_text(json.dumps({
                "format": "qstudio", "version": "0.3", "project": {"name": "Malformed"},
                "structure": source().to_dict(), "device": {"id": "bad", "regions": "not-a-list"},
                "calculator": {}, "workflows": {}, "results": {}, "analysis": {},
            }))
            loaded = Project.load(path)
        self.assertIsNone(loaded.get_device())
        self.assertIn("Device data was not loaded", loaded.device_load_error)
        self.assertEqual(loaded.get_structure().name, "Source")

    def test_loaded_device_history_is_empty_and_source_content_is_unchanged(self):
        app()
        project = Project("History Load")
        device = Device(name="Device")
        source_structure = source()
        device.add_region(DeviceRegion(id="region", source_structure=source_structure, translation=(1.0, 2.0, 3.0)))
        project.set_device(device)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "history.qs"
            project.save(path)
            loaded = Project.load(path)
        workspace = DeviceBuilderWorkspace(loaded)
        self.assertFalse(workspace.can_undo())
        self.assertFalse(workspace.can_redo())
        self.assertEqual(workspace.region_tree.tree.topLevelItemCount(), 1)
        self.assertEqual(len(workspace.viewport.atoms), len(source_structure.atoms))
        self.assertEqual(workspace.device.regions[0].source_structure.to_dict(), source_structure.to_dict())
        workspace.close()


class DeviceHistoryWorkspaceTests(unittest.TestCase):
    def setUp(self):
        app()
        self.project = Project("Device History")
        self.workspace = DeviceBuilderWorkspace(self.project)
        self.source = source()
        self.source_before = self.source.to_dict()

    def tearDown(self):
        self.workspace.close()

    def _add_pair(self):
        reference = self.workspace.add_region_from_structure(self.source, "Reference")
        moving = self.workspace.add_region_from_structure(source("Moving", "O", (8.0, 2.0, 1.0)), "Moving")
        return reference, moving

    def _edit_values(self, region, **changes):
        return {
            "id": region.id,
            "name": changes.get("name", region.name),
            "role": changes.get("role", region.role),
            "visible": changes.get("visible", region.visible),
            "translation": changes.get("translation", region.translation),
            "rotation": changes.get("rotation", region.rotation),
        }

    def test_add_remove_and_duplicate_undo_redo_preserve_region_ids(self):
        added = self.workspace.add_region_from_structure(self.source, "Added")
        self.assertIs(self.project.get_device(), self.workspace.device)
        self.assertTrue(self.workspace.can_undo())
        self.assertTrue(self.workspace.undo())
        self.assertEqual(self.workspace.device.regions, [])
        self.assertTrue(self.workspace.redo())
        self.assertEqual(self.workspace.device.regions[0].id, added.id)
        self.workspace.clear_history()
        self.workspace.selected_region_id = added.id
        self.workspace.duplicate_selected_region()
        duplicate_id = self.workspace.selected_region_id
        self.workspace.undo()
        self.assertEqual([region.id for region in self.workspace.device.regions], [added.id])
        self.workspace.redo()
        self.assertEqual({region.id for region in self.workspace.device.regions}, {added.id, duplicate_id})
        self.workspace.selected_region_id = added.id
        self.workspace.remove_selected_region()
        self.workspace.undo()
        self.assertIsNotNone(self.workspace.device.get_region(added.id))

    def test_property_translation_rotation_and_source_immutability_undo_redo(self):
        region = self.workspace.add_region_from_structure(self.source, "Editable")
        self.workspace.clear_history()
        self.workspace.update_region(self._edit_values(
            region, name="Renamed", role=RegionRole.GATE, visible=False,
            translation=(1.0, 2.0, 3.0), rotation=(4.0, 5.0, 6.0),
        ))
        changed = self.workspace.device.get_region(region.id)
        self.assertEqual((changed.name, changed.role, changed.visible), ("Renamed", RegionRole.GATE, False))
        self.assertEqual(changed.translation, (1.0, 2.0, 3.0))
        self.assertEqual(changed.rotation, (4.0, 5.0, 6.0))
        self.workspace.undo()
        restored = self.workspace.device.get_region(region.id)
        self.assertEqual(restored.name, "Editable")
        self.assertEqual(restored.translation, (0.0, 0.0, 0.0))
        self.workspace.redo()
        redone = self.workspace.device.get_region(region.id)
        self.assertEqual(redone.rotation, (4.0, 5.0, 6.0))
        self.assertEqual(self.source.to_dict(), self.source_before)
        self.assertEqual(redone.source_structure.to_dict(), self.source_before)

    def test_placement_and_alignment_undo_redo_restore_exact_transforms(self):
        reference, moving = self._add_pair()
        self.workspace.clear_history()
        self.workspace.selected_region_id = moving.id
        before = moving.translation
        self.workspace.place_selected("above", reference.id, gap=3.0)
        placed = self.workspace.device.get_region(moving.id).translation
        self.assertNotEqual(placed, before)
        self.workspace.undo()
        self.assertEqual(self.workspace.device.get_region(moving.id).translation, before)
        self.workspace.redo()
        self.assertEqual(self.workspace.device.get_region(moving.id).translation, placed)
        self.workspace.clear_history()
        before_align = self.workspace.device.get_region(moving.id).translation
        self.workspace.align_selected_centers("XY", reference.id)
        aligned = self.workspace.device.get_region(moving.id).translation
        self.workspace.undo()
        self.assertEqual(self.workspace.device.get_region(moving.id).translation, before_align)
        self.workspace.redo()
        self.assertEqual(self.workspace.device.get_region(moving.id).translation, aligned)

    def test_repeat_padding_and_fit_cell_undo_redo(self):
        region = self.workspace.add_region_from_structure(self.source, "Repeat")
        self.workspace.clear_history()
        self.workspace.selected_region_id = region.id
        self.workspace.repeat_selected_region((2, 1, 1))
        generated_ids = [item.id for item in self.workspace.device.regions]
        self.assertEqual(len(generated_ids), 2)
        self.workspace.undo()
        self.assertEqual([item.id for item in self.workspace.device.regions], [region.id])
        self.workspace.redo()
        self.assertEqual([item.id for item in self.workspace.device.regions], generated_ids)
        self.workspace.clear_history()
        self.workspace.set_device_padding((1.0, 2.0, 3.0))
        self.workspace.undo()
        self.assertEqual(self.workspace.device.padding, (5.0, 5.0, 5.0))
        self.workspace.redo()
        self.assertEqual(self.workspace.device.padding, (1.0, 2.0, 3.0))
        self.workspace.clear_history()
        self.workspace.fit_cell_to_device((2.0, 2.0, 2.0))
        cell = self.workspace.device.cell
        origin = self.workspace.device.origin_offset
        self.workspace.undo()
        self.assertIsNone(self.workspace.device.cell)
        self.assertEqual(self.workspace.device.origin_offset, (0.0, 0.0, 0.0))
        self.workspace.redo()
        np.testing.assert_allclose(self.workspace.device.cell, cell)
        np.testing.assert_allclose(self.workspace.device.origin_offset, origin)

    def test_project_window_routes_device_and_builder_history_independently(self):
        window = ProjectWindow(self.project)
        workspace = window.device_builder
        added = workspace.add_region_from_structure(self.source, "Device")
        window._select_vertical(1)
        self.assertTrue(window.undo_action.isEnabled())
        window.undo_action.trigger()
        self.assertIsNone(workspace.device.get_region(added.id))
        window.redo_action.trigger()
        self.assertIsNotNone(workspace.device.get_region(added.id))
        builder = window.builder
        builder.structure.make_supercell(1, 1, 1)
        builder._commit()
        builder_undo_count = len(builder._qs_undo_stack)
        window._select_vertical(0)
        window._undo_active_workspace()
        self.assertEqual(len(builder._qs_undo_stack), builder_undo_count - 1)
        window._select_vertical(1)
        self.assertTrue(workspace.can_undo())
        window._allow_close = True
        window.close()
