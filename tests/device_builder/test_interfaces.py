import math
import os
import time
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np
from PySide6.QtWidgets import QApplication

from frontend.core import Atom, Project, Structure
from frontend.device_builder import DeviceBuilderWorkspace
from frontend.device_builder.assembly import validate_device
from frontend.device_builder.interface import apply_interface_match, prepare_interface_match
from frontend.device_builder.model import Device, DeviceInterface, DeviceRegion, InterfaceMode, RegionRole

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def app():
    return QApplication.instance() or QApplication([])


def square_layer(a=3.0, name="Square"):
    structure = Structure([Atom("C", 0.0, 0.0, 0.0)], [[a, 0.0, 0.0], [0.0, a, 0.0], [0.0, 0.0, 20.0]], name=name)
    structure.periodic = [True, True, False]
    return structure


def hexagonal_layer(a=3.0, name="Hexagonal"):
    structure = Structure(
        [Atom("C", 0.0, 0.0, 0.0)],
        [[a, 0.0, 0.0], [0.5 * a, np.sqrt(3.0) * a / 2.0, 0.0], [0.0, 0.0, 20.0]],
        name=name,
    )
    structure.periodic = [True, True, False]
    return structure


def device_pair(a, b):
    device = Device(name="Interface Device")
    region_a = device.add_region(DeviceRegion(a, name="A", role=RegionRole.ELECTRODE, translation=(1.0, 2.0, 3.0)))
    region_b = device.add_region(DeviceRegion(b, name="B", role=RegionRole.CHANNEL, translation=(-3.0, 0.0, 4.0)))
    return device, region_a, region_b


class InterfaceIntegrationTests(unittest.TestCase):
    KNOWN_TWIST = math.degrees(math.acos(13.0 / 14.0))

    def test_aligned_square_and_hexagonal_interfaces_preserve_region_ids_and_gap(self):
        for first, second in ((square_layer(), square_layer()), (hexagonal_layer(), hexagonal_layer())):
            device, region_a, region_b = device_pair(first, second)
            original_a = region_a.source_structure.to_dict()
            original_b = region_b.source_structure.to_dict()
            result = prepare_interface_match(region_a, region_b, max_index=1, max_strain=0.0, gap=3.0)
            self.assertEqual(region_a.source_structure.to_dict(), original_a)
            self.assertEqual(region_b.source_structure.to_dict(), original_b)
            interface = apply_interface_match(device, result)
            self.assertEqual(interface.mode, InterfaceMode.ALIGNED)
            self.assertEqual(interface.diagnostics["determinant_a"], 1)
            self.assertEqual(interface.diagnostics["determinant_b"], 1)
            self.assertEqual({region_a.id, region_b.id}, {interface.region_a_id, interface.region_b_id})
            z_a = np.asarray([atom.z for atom in region_a.source_structure.atoms])
            z_b = np.asarray([atom.z for atom in region_b.source_structure.atoms])
            self.assertAlmostEqual(z_b.min() - z_a.max(), 3.0, places=10)
            self.assertEqual(region_a.translation, (0.0, 0.0, 0.0))
            self.assertEqual(region_b.rotation, (0.0, 0.0, 0.0))

    def test_slight_mismatch_and_all_existing_strain_modes(self):
        expected_balanced = math.sqrt(1.01) - 1.0
        expected_modes = {"balanced": expected_balanced, "bottom": 0.01, "top": 0.0}
        for mode, expected_a in expected_modes.items():
            _, region_a, region_b = device_pair(square_layer(3.0), square_layer(3.03))
            result = prepare_interface_match(
                region_a, region_b, max_index=1, max_strain=0.01, strain_mode=mode, gap=2.0,
            )
            diagnostics = result.interface.diagnostics
            self.assertEqual(diagnostics["strain_mode"], mode)
            self.assertAlmostEqual(max(abs(value) for value in diagnostics["principal_strains_a"]), expected_a, places=10)
            if mode == "bottom":
                self.assertAlmostEqual(max(abs(value) for value in diagnostics["principal_strains_b"]), 0.0, places=10)
            if mode == "top":
                self.assertAlmostEqual(max(abs(value) for value in diagnostics["principal_strains_b"]), 0.01 / 1.01, places=10)

    def test_zero_and_known_twisted_moire_interfaces(self):
        device, region_a, region_b = device_pair(hexagonal_layer(), hexagonal_layer())
        zero = prepare_interface_match(
            region_a, region_b, mode=InterfaceMode.TWISTED, requested_twist_deg=0.0,
            max_index=1, max_strain=0.0, gap=3.0,
        )
        self.assertEqual(zero.interface.diagnostics["determinant_a"], 1)
        self.assertAlmostEqual(zero.interface.diagnostics["max_principal_strain"], 0.0, places=12)
        known = prepare_interface_match(
            region_a, region_b, mode=InterfaceMode.TWISTED, requested_twist_deg=self.KNOWN_TWIST,
            max_index=3, max_strain=1e-8, gap=3.0,
        )
        diagnostics = known.interface.diagnostics
        self.assertEqual(diagnostics["determinant_a"], 7)
        self.assertEqual(diagnostics["determinant_b"], 7)
        self.assertAlmostEqual(diagnostics["max_principal_strain"], 0.0, places=10)
        self.assertAlmostEqual(diagnostics["residual_rotation_deg"], 0.0, places=10)
        self.assertAlmostEqual(known.interface.requested_twist_deg, self.KNOWN_TWIST, places=10)
        self.assertEqual(len(known.source_structure_a.atoms) + len(known.source_structure_b.atoms), 14)

    def test_failures_do_not_mutate_device_or_create_history(self):
        app()
        project = Project("Interface Failure")
        workspace = DeviceBuilderWorkspace(project)
        first = workspace.add_region_from_structure(square_layer(), "A")
        second = workspace.add_region_from_structure(square_layer(3.03), "B")
        workspace.clear_history()
        before = workspace.device.to_dict()
        with self.assertRaisesRegex(ValueError, "different"):
            workspace.match_interface(first.id, first.id)
        with self.assertRaisesRegex(RuntimeError, "No commensurate"):
            workspace.match_interface(first.id, second.id, max_index=1, max_strain=0.004)
        with self.assertRaisesRegex(ValueError, "safety limit"):
            prepare_interface_match(first, second, atom_count_limit=1)
        with self.assertRaisesRegex(ValueError, "finite"):
            prepare_interface_match(first, second, mode=InterfaceMode.TWISTED, requested_twist_deg=float("nan"))
        self.assertEqual(workspace.device.to_dict(), before)
        self.assertFalse(workspace.can_undo())
        workspace.close()

    def test_async_interface_worker_commits_only_after_background_result(self):
        app()
        workspace = DeviceBuilderWorkspace(Project("Async Interface"))
        first = workspace.add_region_from_structure(square_layer(), "A")
        second = workspace.add_region_from_structure(square_layer(), "B")
        controls = workspace.interface_controls
        controls.region_a.setCurrentIndex(controls.region_a.findData(first.id))
        controls.region_b.setCurrentIndex(controls.region_b.findData(second.id))
        controls.max_index.setValue(1)
        controls.max_strain.setValue(0.0)
        workspace.start_interface_match()
        deadline = time.monotonic() + 5.0
        application = QApplication.instance()
        while workspace._interface_thread is not None and time.monotonic() < deadline:
            application.processEvents()
            time.sleep(0.01)
        self.assertIsNone(workspace._interface_thread)
        self.assertEqual(len(workspace.device.interfaces), 1)
        workspace.close()

    def test_interface_validation_and_region_integrity_cleanup(self):
        device, region_a, region_b = device_pair(square_layer(), square_layer())
        bad = DeviceInterface(region_a.id, "missing", id="bad")
        device.add_interface(bad)
        self.assertFalse(validate_device(device).valid)
        device.remove_interface(bad.id)
        result = prepare_interface_match(region_a, region_b, max_index=1, max_strain=0.0)
        interface = apply_interface_match(device, result)
        duplicate = device.duplicate_region(region_a.id)
        self.assertEqual(len(device.interfaces), 1)
        self.assertNotIn(duplicate.id, (interface.region_a_id, interface.region_b_id))
        device.remove_region(region_a.id)
        self.assertEqual(device.interfaces, [])

    def test_match_undo_redo_restores_exact_sources_transforms_and_interfaces(self):
        app()
        workspace = DeviceBuilderWorkspace(Project("Interface History"))
        first = workspace.add_region_from_structure(square_layer(), "A")
        second = workspace.add_region_from_structure(square_layer(), "B")
        original = workspace.device.to_dict()
        workspace.clear_history()
        interface = workspace.match_interface(first.id, second.id, max_index=1, max_strain=0.0, gap=2.5)
        matched = workspace.device.to_dict()
        self.assertEqual(len(workspace.device.interfaces), 1)
        self.assertTrue(workspace.undo())
        self.assertEqual(workspace.device.to_dict(), original)
        self.assertTrue(workspace.redo())
        self.assertEqual(workspace.device.to_dict(), matched)
        self.assertEqual(workspace.device.interfaces[0].id, interface.id)
        workspace.close()

    def test_matched_interface_persists_and_loaded_history_is_empty(self):
        app()
        project = Project("Persistent Interface")
        workspace = DeviceBuilderWorkspace(project)
        first = workspace.add_region_from_structure(hexagonal_layer(), "A")
        second = workspace.add_region_from_structure(hexagonal_layer(), "B")
        workspace.match_interface(
            first.id, second.id, mode=InterfaceMode.TWISTED, requested_twist_deg=self.KNOWN_TWIST,
            max_index=3, max_strain=1e-8, gap=3.0, fit_cell_after_match=True,
        )
        expected = workspace.device.to_dict()
        expected_assembly = workspace.device.assemble().to_dict()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "interface.qs"
            project.save(path)
            loaded = Project.load(path)
        self.assertEqual(loaded.get_device().to_dict(), expected)
        self.assertEqual(loaded.get_device().assemble().to_dict(), expected_assembly)
        restored_workspace = DeviceBuilderWorkspace(loaded)
        self.assertEqual(restored_workspace.region_tree.tree.topLevelItemCount(), 2)
        self.assertFalse(restored_workspace.can_undo())
        restored_workspace.close()
        workspace.close()
