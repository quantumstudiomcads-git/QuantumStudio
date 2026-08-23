import os
import unittest

from PySide6.QtWidgets import QApplication

from frontend.core.project import Project
from frontend.core.structure import Atom, Structure
from frontend.device_builder import DeviceBuilderWorkspace
from frontend.device_builder.model import DeviceRegion

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def app():
    return QApplication.instance() or QApplication([])


class DeviceWorkspaceTests(unittest.TestCase):
    def test_workspace_imports_and_updates_preview_without_builder_mutation(self):
        app()
        project = Project("Device Workspace")
        source = Structure([Atom("C", 0.0, 0.0, 0.0)], [[2.0, 0.0, 0.0], [0.0, 2.0, 0.0], [0.0, 0.0, 2.0]])
        source_before = source.to_dict()
        workspace = DeviceBuilderWorkspace(project)
        region = workspace.device.add_region(DeviceRegion(source, name="Region 1"))
        workspace.selected_region_id = region.id
        workspace.refresh_preview()
        self.assertEqual(workspace.region_tree.tree.topLevelItemCount(), 1)
        self.assertEqual(len(workspace.viewport.atoms), 1)
        workspace.update_region({
            "id": region.id, "name": "Channel", "role": region.role,
            "visible": True, "translation": (3.0, 0.0, 0.0), "rotation": (0.0, 0.0, 0.0),
        })
        self.assertEqual(workspace.device.get_region(region.id).name, "Channel")
        self.assertEqual(workspace.viewport.atoms[0].x, 3.0)
        self.assertEqual(source.to_dict(), source_before)
        workspace.remove_selected_region()
        self.assertEqual(workspace.region_tree.tree.topLevelItemCount(), 0)
        self.assertEqual(len(workspace.viewport.atoms), 0)
        workspace.close()

    def test_add_current_builder_structure_uses_project_public_structure_copy(self):
        app()
        project = Project("Current Builder Structure")
        source = Structure([Atom("Si", 1.0, 2.0, 3.0)], [[4.0, 0.0, 0.0], [0.0, 4.0, 0.0], [0.0, 0.0, 4.0]], name="Builder Source")
        project.set_structure(source)
        before = project.get_structure().to_dict()
        workspace = DeviceBuilderWorkspace(project)
        region = workspace.add_current_builder_structure()
        self.assertIsNotNone(region)
        self.assertIsNot(region.source_structure, source)
        workspace.selected_region_id = region.id
        workspace.update_region({
            "id": region.id, "name": region.name, "role": region.role,
            "visible": True, "translation": (9.0, 0.0, 0.0), "rotation": (0.0, 0.0, 0.0),
        })
        self.assertEqual(project.get_structure().to_dict(), before)
        self.assertEqual(workspace.viewport.atoms[0].x, 10.0)
        self.assertTrue(hasattr(workspace, "placement"))
        workspace.close()
