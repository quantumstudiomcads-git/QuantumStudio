import os
import unittest

import numpy as np
from PySide6.QtWidgets import QApplication, QPushButton
from ase import Atoms

from frontend.builder import Builder, StructureViewport
from frontend.builder_math import (
    cartesian_coordinates,
    fractional_coordinates,
    miller_normal,
    minimum_image_distance,
    reciprocal_lattice,
)
from frontend.project import Project
from frontend.project_window import ProjectWindow
from frontend.structure import Atom, Structure

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def app():
    return QApplication.instance() or QApplication([])


class BuilderViewTests(unittest.TestCase):

    def test_reciprocal_lattice_and_miller_math(self):
        cell = np.array([[3.0, 0.2, 0.1], [0.4, 4.0, 0.3], [0.2, 0.5, 5.0]])
        reciprocal = reciprocal_lattice(cell)
        for i in range(3):
            for j in range(3):
                expected = 2.0 * np.pi if i == j else 0.0
                self.assertAlmostEqual(float(np.dot(cell[i], reciprocal[j])), expected, places=10)
        for indices, expected in [
            ((0, 0, 1), reciprocal[2]),
            ((1, 0, 0), reciprocal[0]),
            ((1, 1, 0), reciprocal[0] + reciprocal[1]),
            ((1, 1, 1), reciprocal[0] + reciprocal[1] + reciprocal[2]),
        ]:
            np.testing.assert_allclose(miller_normal(cell, *indices), expected)
        with self.assertRaises(ValueError):
            miller_normal(cell, 0, 0, 0)
        self.assertFalse(np.allclose(cell[2] / np.linalg.norm(cell[2]), reciprocal[2] / np.linalg.norm(reciprocal[2])))

    def test_fractional_and_minimum_image_math(self):
        cell = np.diag([10.0, 10.0, 10.0])
        fractional = np.array([0.2, 0.3, 0.4])
        cartesian = cartesian_coordinates(fractional, cell)
        np.testing.assert_allclose(fractional_coordinates(cartesian, cell), fractional)
        self.assertAlmostEqual(minimum_image_distance([0.1, 0.0, 0.0], [9.9, 0.0, 0.0], cell, [True, True, True]), 0.2)
        self.assertAlmostEqual(minimum_image_distance([0.1, 0.0, 0.0], [9.9, 0.0, 0.0], cell, [False, True, True]), 9.8)

    def test_viewport_view_direction_projection_and_display_state(self):
        app()
        structure = Structure(
            atoms=[Atom("C", 0.0, 0.0, 0.0), Atom("O", 1.0, 0.0, 0.0)],
            cell=[[3.0, 0.0, 0.0], [0.2, 3.0, 0.0], [0.1, 0.2, 8.0]],
        )
        viewport = StructureViewport()
        viewport.resize(500, 500)
        viewport.set_structure(structure)
        original = structure.to_dict()
        viewport.set_view_direction([1.0, 2.0, 3.0])
        self.assertAlmostEqual(np.linalg.norm(viewport.view_direction), 1.0)
        viewport.set_projection_mode("perspective")
        viewport.set_projection_mode("orthographic")
        viewport.set_periodic_display(2, 2, 1)
        self.assertEqual(viewport.render_atom_count(), 8)
        viewport.set_visible_species({"C"})
        self.assertEqual(len(viewport.atoms), 2)
        self.assertEqual(structure.to_dict(), original)
        with self.assertRaises(ValueError):
            viewport.set_view_direction([0.0, 0.0, 0.0])

    def test_selected_atom_information_and_viewer_only_state(self):
        app()
        project = Project("selection test")
        project.set_structure(Structure(
            atoms=[Atom("C", 1.0, 2.0, 3.0)],
            cell=[[5.0, 0.0, 0.0], [0.0, 5.0, 0.0], [0.0, 0.0, 5.0]],
        ))
        builder = Builder(project)
        builder.viewport.selected_atom = 0
        builder._update_selected_atom_info()
        self.assertIn("Index: 1", builder.selected_info.text())
        self.assertIn("Cartesian: 1.00000, 2.00000, 3.00000", builder.selected_info.text())
        self.assertIn("u,v,w: 0.20000, 0.40000, 0.60000", builder.selected_info.text())
        structure_before = project.get_structure().to_dict()
        builder.viewport.set_projection_mode("perspective")
        builder.viewport.set_label_mode("Index")
        builder.viewport.set_periodic_display(2, 2, 1)
        self.assertEqual(project.get_structure().to_dict(), structure_before)
        builder.close()

    def test_background_menu_is_active_and_viewer_only(self):
        app()
        project = Project("background toolbar test")
        project.set_structure(Structure(
            atoms=[Atom("C", 0.0, 0.0, 0.0)],
            cell=[[3.0, 0.0, 0.0], [0.0, 3.0, 0.0], [0.0, 0.0, 6.0]],
        ))
        window = ProjectWindow(project)
        actions = window.builder_toolbar.actions()
        labels = [item.text() for item in actions]
        self.assertIn("Background", labels)
        self.assertLess(labels.index("Background"), labels.index("Export"))
        self.assertLess(labels.index("Periodic"), labels.index("Background"))
        menu = window.background_action.menu()
        self.assertEqual(
            [item.text() for item in menu.actions()],
            ["Default Dark", "White", "Custom Color..."],
        )
        structure_before = project.get_structure().to_dict()
        camera_before = window.builder.viewport.view_direction.copy()
        for color, expected in (("#FFFFFF", "#ffffff"), ("#223344", "#223344"), ("#0D0F13", "#0d0f13")):
            window._set_builder_background(color)
            self.assertEqual(window.builder.viewport.background_color.name(), expected)
            self.assertEqual(project.get_structure().to_dict(), structure_before)
            np.testing.assert_allclose(window.builder.viewport.view_direction, camera_before)
        window._allow_close = True
        window.close()

    def test_toolbar_uses_cartesian_and_reciprocal_view_labels(self):
        app()
        project = Project("reciprocal toolbar test")
        project.set_structure(Structure(
            atoms=[Atom("C", 0.0, 0.0, 0.0)],
            cell=[[3.0, 0.2, 0.1], [0.4, 4.0, 0.3], [0.2, 0.5, 5.0]],
        ))
        window = ProjectWindow(project)
        labels = [action.text() for action in window.builder_toolbar.actions()]
        self.assertEqual([label for label in ("X", "Y", "Z", "X*", "Y*", "Z*")
                          if label in labels],
                         ["X", "Y", "Z", "X*", "Y*", "Z*"])
        self.assertFalse(any(label in {"a", "b", "c", "a*", "b*", "c*"}
                             for label in labels))
        reciprocal = reciprocal_lattice(np.asarray(project.get_structure().cell, dtype=float))
        for label, index in (("X*", 0), ("Y*", 1), ("Z*", 2)):
            action = next(item for item in window.builder_toolbar.actions()
                          if item.text() == label)
            action.trigger()
            np.testing.assert_allclose(
                window.builder.viewport.view_direction,
                reciprocal[index] / np.linalg.norm(reciprocal[index]),
            )
        window._allow_close = True
        window.close()

    def test_builder_rename_and_import_locations(self):
        app()
        project = Project("Builder test")
        window = ProjectWindow(project)
        self.assertIsInstance(window.builder, Builder)
        self.assertEqual(window.builder_button.text(), "Builder")
        toolbar_text = [action.text() for action in window.builder_toolbar.actions()]
        self.assertNotIn("Import", toolbar_text)
        import_buttons = [button for button in window.builder.findChildren(QPushButton) if button.text() == "Import Structure"]
        self.assertEqual(len(import_buttons), 1)
        window.close()


if __name__ == "__main__":
    unittest.main()
