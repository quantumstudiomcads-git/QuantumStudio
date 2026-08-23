import math
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

import numpy as np
from PySide6.QtWidgets import QApplication

from frontend.core import Atom, Project, Structure
from frontend.device_builder import DeviceBuilderWorkspace
from frontend.device_builder.assembly import transformed_region_bounds
from frontend.device_builder.model import DeviceRegion, RegionRole
from frontend.device_builder.templates import DEFAULT_TEMPLATE_REGISTRY

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def app():
    return QApplication.instance() or QApplication([])


def layer(name="Layer", a=3.0, element="C"):
    value = Structure(
        [Atom(element, 0.0, 0.0, 0.0), Atom(element, 1.0, 1.0, 0.5)],
        [[a, 0.0, 0.0], [0.0, a, 0.0], [0.0, 0.0, 12.0]], name=name,
    )
    value.periodic = [True, True, False]
    return value


def bounds_gap(first, second, axis, positive=True):
    a = transformed_region_bounds(first)
    b = transformed_region_bounds(second)
    return b.minimum[axis] - a.maximum[axis] if positive else a.minimum[axis] - b.maximum[axis]


class DeviceTemplateTests(unittest.TestCase):
    def setUp(self):
        self.source = layer()
        self.source_before = self.source.to_dict()

    def test_registry_is_deterministic_unique_and_qt_free_domain_import(self):
        templates = DEFAULT_TEMPLATE_REGISTRY.list_templates()
        self.assertEqual(
            [template.id for template in templates],
            ["vertical_stack", "lateral_two_probe", "tunnel_junction", "surface_adsorbate"],
        )
        self.assertEqual(len({template.id for template in templates}), len(templates))
        for template in templates:
            self.assertTrue(template.name)
            self.assertTrue(template.description)
            self.assertTrue(template.required_inputs)
            self.assertIs(DEFAULT_TEMPLATE_REGISTRY.get(template.id), template)
        # Use a new interpreter because this Qt test module itself imports QApplication.
        result = subprocess.run(
            [sys.executable, "-c", "import sys; import frontend.device_builder.templates; assert 'PySide6.QtWidgets' not in sys.modules"],
            cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_vertical_stack_geometry_roles_fit_and_source_immutability(self):
        result = DEFAULT_TEMPLATE_REGISTRY.get("vertical_stack").build(
            bottom_structure=self.source, top_structure=layer("Top", element="O"), gap=2.75, padding=(1.0, 2.0, 3.0),
        )
        device = result.device
        self.assertEqual([region.role for region in device.regions], [RegionRole.ACTIVE_LAYER, RegionRole.ACTIVE_LAYER])
        bottom, top = device.regions
        self.assertAlmostEqual(bounds_gap(bottom, top, 2), 2.75, places=10)
        np.testing.assert_allclose(transformed_region_bounds(bottom).center[:2], transformed_region_bounds(top).center[:2])
        self.assertIsNotNone(device.cell)
        self.assertEqual(device.metadata["template_id"], "vertical_stack")
        self.assertEqual(self.source.to_dict(), self.source_before)

    def test_vertical_stack_matched_mode_reuses_interface_and_preserves_identity(self):
        result = DEFAULT_TEMPLATE_REGISTRY.get("vertical_stack").build(
            bottom_structure=self.source, top_structure=layer("Top"), gap=3.0, interface_matching=True,
            twist_angle_deg=0.0, max_strain=0.0, max_index=1, strain_mode="balanced", padding=(1.0, 1.0, 1.0),
        )
        device = result.device
        self.assertEqual(len(device.interfaces), 1)
        interface = device.interfaces[0]
        self.assertEqual(interface.diagnostics["determinant_a"], 1)
        self.assertEqual(interface.diagnostics["determinant_b"], 1)
        self.assertEqual({interface.region_a_id, interface.region_b_id}, {region.id for region in device.regions})
        self.assertAlmostEqual(bounds_gap(device.regions[0], device.regions[1], 2), 3.0, places=10)

    def test_vertical_stack_known_moire_case_reuses_stage3_matcher(self):
        angle = math.degrees(math.acos(13.0 / 14.0))
        hexagonal = Structure(
            [Atom("C", 0.0, 0.0, 0.0)],
            [[3.0, 0.0, 0.0], [1.5, 3.0 * math.sqrt(3.0) / 2.0, 0.0], [0.0, 0.0, 20.0]],
            name="Hexagonal",
        )
        hexagonal.periodic = [True, True, False]
        result = DEFAULT_TEMPLATE_REGISTRY.get("vertical_stack").build(
            bottom_structure=hexagonal, top_structure=hexagonal, gap=3.0, interface_matching=True,
            twist_angle_deg=angle, max_strain=1.0e-8, max_index=3, padding=(1.0, 1.0, 1.0),
        )
        interface = result.device.interfaces[0]
        self.assertEqual(interface.mode.value, "twisted")
        self.assertEqual(interface.diagnostics["determinant_a"], 7)
        self.assertEqual(interface.diagnostics["determinant_b"], 7)
        self.assertAlmostEqual(interface.diagnostics["max_principal_strain"], 0.0, places=10)
        self.assertAlmostEqual(interface.requested_twist_deg, angle, places=10)

    def test_two_probe_and_tunnel_junction_use_ordered_roles_and_gaps(self):
        two_probe = DEFAULT_TEMPLATE_REGISTRY.get("lateral_two_probe").build(
            left_structure=layer("Left"), center_structure=layer("Center"), right_structure=layer("Right"),
            left_gap=1.5, right_gap=2.5, padding=(1.0, 1.0, 1.0),
        ).device
        self.assertEqual([region.role for region in two_probe.regions], [RegionRole.ELECTRODE, RegionRole.CHANNEL, RegionRole.ELECTRODE])
        self.assertEqual(two_probe.transport_direction, "X")
        left, center, right = two_probe.regions
        self.assertAlmostEqual(bounds_gap(center, left, 0, positive=False), 1.5, places=10)
        self.assertAlmostEqual(bounds_gap(center, right, 0, positive=True), 2.5, places=10)
        np.testing.assert_allclose(transformed_region_bounds(left).center[1:], transformed_region_bounds(center).center[1:])
        np.testing.assert_allclose(transformed_region_bounds(right).center[1:], transformed_region_bounds(center).center[1:])
        tunnel = DEFAULT_TEMPLATE_REGISTRY.get("tunnel_junction").build(
            left_structure=layer("L"), barrier_structure=layer("Barrier", element="O"), right_structure=layer("R"),
            left_gap=1.0, right_gap=1.0, padding=(1.0, 1.0, 1.0),
        ).device
        self.assertEqual([region.role for region in tunnel.regions], [RegionRole.ELECTRODE, RegionRole.DIELECTRIC, RegionRole.ELECTRODE])
        self.assertEqual(tunnel.transport_direction, "X")
        self.assertEqual(self.source.to_dict(), self.source_before)

    def test_surface_adsorbate_applies_rotation_offset_and_gap_non_destructively(self):
        result = DEFAULT_TEMPLATE_REGISTRY.get("surface_adsorbate").build(
            substrate_structure=self.source, adsorbate_structure=layer("Ads", element="O"), separation=2.0,
            offset_x=0.5, offset_y=-0.25, rotation=(0.0, 0.0, 30.0), padding=(1.0, 1.0, 4.0),
        )
        substrate, adsorbate = result.device.regions
        self.assertEqual([region.role for region in result.device.regions], [RegionRole.SUBSTRATE, RegionRole.ADSORBATE])
        self.assertAlmostEqual(bounds_gap(substrate, adsorbate, 2), 2.0, places=10)
        substrate_center = np.asarray(transformed_region_bounds(substrate).center)
        adsorbate_center = np.asarray(transformed_region_bounds(adsorbate).center)
        np.testing.assert_allclose(adsorbate_center[:2] - substrate_center[:2], (0.5, -0.25), atol=1e-10)
        self.assertEqual(adsorbate.rotation, (0.0, 0.0, 30.0))
        self.assertEqual(self.source.to_dict(), self.source_before)

    def test_template_failure_is_transactional_and_workspace_history_is_one_command(self):
        app()
        project = Project("Template History")
        workspace = DeviceBuilderWorkspace(project)
        old = workspace.add_region_from_structure(self.source, "Existing")
        old_snapshot = workspace.device.to_dict()
        workspace.clear_history()
        with self.assertRaises(ValueError):
            workspace.create_template("vertical_stack", {"bottom_structure": self.source, "top_structure": None}, replace=True)
        self.assertEqual(workspace.device.to_dict(), old_snapshot)
        self.assertFalse(workspace.can_undo())
        result = workspace.create_template(
            "vertical_stack", {"bottom_structure": self.source, "top_structure": layer("Top"), "gap": 2.0}, replace=True,
        )
        created_snapshot = workspace.device.to_dict()
        self.assertTrue(workspace.can_undo())
        self.assertEqual(len(workspace.device.regions), 2)
        self.assertTrue(workspace.undo())
        self.assertEqual(workspace.device.to_dict(), old_snapshot)
        self.assertTrue(workspace.redo())
        self.assertEqual(workspace.device.to_dict(), created_snapshot)
        self.assertIs(project.get_device(), workspace.device)
        workspace.close()

    def test_each_template_persists_via_standard_device_schema(self):
        parameter_sets = {
            "vertical_stack": dict(bottom_structure=self.source, top_structure=layer("Top"), gap=2.0, interface_matching=True, max_index=1, max_strain=0.0),
            "lateral_two_probe": dict(left_structure=self.source, center_structure=layer("Center"), right_structure=layer("Right"), left_gap=2.0, right_gap=2.0),
            "tunnel_junction": dict(left_structure=self.source, barrier_structure=layer("Barrier"), right_structure=layer("Right"), left_gap=2.0, right_gap=2.0),
            "surface_adsorbate": dict(substrate_structure=self.source, adsorbate_structure=layer("Ads"), separation=2.0),
        }
        with TemporaryDirectory() as directory:
            for template_id, parameters in parameter_sets.items():
                device = DEFAULT_TEMPLATE_REGISTRY.get(template_id).build(**parameters).device
                expected = device.to_dict()
                project = Project(template_id)
                project.set_device(device)
                path = Path(directory) / f"{template_id}.qs"
                project.save(path)
                loaded = Project.load(path)
                self.assertEqual(loaded.get_device().to_dict(), expected)
                self.assertEqual(loaded.get_device().assemble().to_dict(), device.assemble().to_dict())
