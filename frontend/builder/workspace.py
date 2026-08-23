import math
from pathlib import Path

import numpy as np

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QDoubleSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from frontend.core.structure_io import StructureIO
from frontend.builder.view.math import fractional_coordinates, miller_normal, minimum_image_distance, reciprocal_lattice
from frontend.builder.view.panel import BuilderViewMixin
from frontend.builder.build.controller import BuilderBuildMixin
from frontend.builder.measure.controller import BuilderMeasureMixin

from frontend.builder.brillouin_zone.viewer import BrillouinZoneViewer


# =====================================================================
# 3D STRUCTURE VIEWPORT
# =====================================================================


class StructureViewport(QWidget):

    def __init__(self):
        super().__init__()

        self.setMinimumSize(500, 500)

        self.atoms = []
        self.cell = None

        self.show_bonds = True
        self.show_cell = True
        self.show_axes = True

        self.atom_scale = 1.0

        self.rotation_x = -20.0
        self.rotation_y = 30.0

        self.zoom = 1.0

        self.pan_x = 0.0
        self.pan_y = 0.0

        self.last_mouse = QPoint()

        self.rotating = False
        self.panning = False

        self.selected_atom = None
        self.view_basis = None
        self.view_direction = np.array([0.0, 0.0, 1.0])
        self.projection_mode = "orthographic"
        self.label_mode = "element"
        self.visible_species = None
        self.display_repeats = (1, 1, 1)
        self.pbc = (True, True, True)
        self.native_structure = None
        self.on_selection_changed = None

        # Measurement visualization state.
        self.measurement_overlay = None
        self.background_color = QColor('#0D0F13')

    # -----------------------------------------------------------------
    # Structure
    # -----------------------------------------------------------------

    def set_structure(self, structure):

        self.native_structure = structure
        self.atoms = [atom.copy() for atom in structure.atoms]
        self.cell = [list(vector) for vector in structure.cell]
        self.pbc = tuple(bool(value) for value in getattr(
            structure, "periodic", (True, True, True)
        ))
        self.selected_atom = None
        species = {atom.element for atom in self.atoms}
        self.visible_species = species
        self.display_repeats = (1, 1, 1)
        self.reset_view()

    # -----------------------------------------------------------------
    # Rotation
    # -----------------------------------------------------------------

    def _rotate(self, x, y, z):

        vector = np.asarray([x, y, z], dtype=float)
        if self.view_basis is not None:
            vector = self.view_basis @ vector
        x, y, z = vector.tolist()

        rx = math.radians(self.rotation_x)
        ry = math.radians(self.rotation_y)

        y1 = y * math.cos(rx) - z * math.sin(rx)
        z1 = y * math.sin(rx) + z * math.cos(rx)
        x2 = x * math.cos(ry) + z1 * math.sin(ry)
        z2 = -x * math.sin(ry) + z1 * math.cos(ry)
        return x2, y1, z2

    # -----------------------------------------------------------------
    # Projection
    # -----------------------------------------------------------------

    def _project(self, x, y, z):

        x, y, z = self._rotate(x, y, z)

        scale = min(self.width(), self.height()) * 0.11 * self.zoom
        if self.projection_mode == "perspective":
            scale *= 30.0 / max(1.0, 30.0 - z)

        return (
            self.width() / 2 + x * scale + self.pan_x,
            self.height() / 2 - y * scale + self.pan_y,
            z,
        )

    # -----------------------------------------------------------------
    # Geometry points for automatic framing
    # -----------------------------------------------------------------

    def _all_geometry_points(self):

        points = []

        for atom in self.atoms:

            points.append(
                (
                    float(atom.x),
                    float(atom.y),
                    float(atom.z),
                )
            )

        if self.cell:

            a, b, c = self.cell

            points.extend(
                [
                    (0.0, 0.0, 0.0),

                    tuple(a),
                    tuple(b),
                    tuple(c),

                    (
                        a[0] + b[0],
                        a[1] + b[1],
                        a[2] + b[2],
                    ),

                    (
                        a[0] + c[0],
                        a[1] + c[1],
                        a[2] + c[2],
                    ),

                    (
                        b[0] + c[0],
                        b[1] + c[1],
                        b[2] + c[2],
                    ),

                    (
                        a[0] + b[0] + c[0],
                        a[1] + b[1] + c[1],
                        a[2] + b[2] + c[2],
                    ),
                ]
            )

        return points

    # -----------------------------------------------------------------
    # Automatic framing
    # -----------------------------------------------------------------

    def _fit_structure(self):

        points = self._all_geometry_points()

        if not points:
            self.zoom = 1.0
            self.pan_x = 0.0
            self.pan_y = 0.0
            return

        rotated = [
            self._rotate(*point)
            for point in points
        ]

        xs = [point[0] for point in rotated]
        ys = [point[1] for point in rotated]

        x_span = max(xs) - min(xs)
        y_span = max(ys) - min(ys)

        largest_span = max(
            x_span,
            y_span,
            1e-6,
        )

        viewport_size = min(
            self.width(),
            self.height(),
        )

        target_pixels = viewport_size * 0.70

        base = 0.11

        self.zoom = (
            target_pixels
            / (
                viewport_size
                * base
                * largest_span
            )
        )

        self.zoom = max(
            0.08,
            min(self.zoom, 4.0),
        )

        center_x = (min(xs) + max(xs)) / 2
        center_y = (min(ys) + max(ys)) / 2

        scale = (
            viewport_size
            * base
            * self.zoom
        )

        self.pan_x = -center_x * scale
        self.pan_y = center_y * scale

    # -----------------------------------------------------------------
    # Standard and arbitrary views
    # -----------------------------------------------------------------

    def set_view(self, axis):
        axis = axis.lower()
        self.view_basis = None
        if axis == "x":
            self.rotation_x, self.rotation_y = 0.0, 90.0
        elif axis == "y":
            self.rotation_x, self.rotation_y = 90.0, 0.0
        elif axis == "z":
            self.rotation_x, self.rotation_y = 0.0, 0.0
        else:
            return
        self.view_direction = np.eye(3)[{"x": 0, "y": 1, "z": 2}[axis]]
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._fit_structure()
        self.update()

    def set_view_direction(self, direction):
        vector = np.asarray(direction, dtype=float)
        if vector.shape != (3,) or not np.all(np.isfinite(vector)):
            raise ValueError("View direction must be a finite 3-vector.")
        norm = float(np.linalg.norm(vector))
        if norm <= 1e-12:
            raise ValueError("View direction must be nonzero.")
        forward = vector / norm
        preferred_up = np.array([0.0, 0.0, 1.0])
        if abs(float(np.dot(forward, preferred_up))) > 0.98:
            preferred_up = np.array([0.0, 1.0, 0.0])
        right = np.cross(preferred_up, forward)
        right /= np.linalg.norm(right)
        up = np.cross(forward, right)
        up /= np.linalg.norm(up)
        self.view_basis = np.vstack((right, up, forward))
        self.view_direction = forward
        self.rotation_x = 0.0
        self.rotation_y = 0.0
        self._fit_structure()
        self.update()

    def set_background_color(self, color):
        color = QColor(color)
        if not color.isValid():
            raise ValueError("Background color must be valid.")
        self.background_color = color
        self.update()

    def _light_background(self):
        return self.background_color.lightness() > 160

    def set_projection_mode(self, mode):
        mode = str(mode).strip().lower()
        if mode not in {"orthographic", "perspective"}:
            raise ValueError("Projection mode must be orthographic or perspective.")
        self.projection_mode = mode
        self.update()

    def set_label_mode(self, mode):
        mode = str(mode).strip().lower()
        aliases = {"off": "off", "element": "element", "index": "index", "element + index": "element_index", "element_index": "element_index"}
        if mode not in aliases:
            raise ValueError("Unknown atom label mode.")
        self.label_mode = aliases[mode]
        self.update()

    def set_visible_species(self, species):
        self.visible_species = set(species)
        self.update()

    def set_periodic_display(self, nx=1, ny=1, nz=1):
        values = tuple(int(value) for value in (nx, ny, nz))
        if any(value < 1 or value > 3 for value in values):
            raise ValueError("Periodic display ranges must be between 1 and 3.")
        self.display_repeats = values
        self.update()

    def render_atom_count(self):
        return len(self.atoms) * math.prod(self.display_repeats)

    def center_on_selected(self):
        if self.selected_atom is None or not (0 <= self.selected_atom < len(self.atoms)):
            return False
        x, y, _ = self._rotate(*self._atom_position(self.atoms[self.selected_atom]))
        scale = min(self.width(), self.height()) * 0.11 * self.zoom
        self.pan_x = -x * scale
        self.pan_y = y * scale
        self.update()
        return True

    @staticmethod
    def _atom_position(atom):
        return float(atom.x), float(atom.y), float(atom.z)

    def _display_atom_records(self):
        if not self.cell:
            cell = np.zeros((3, 3))
        else:
            cell = np.asarray(self.cell, dtype=float)
        records = []
        for n1 in range(self.display_repeats[0]):
            for n2 in range(self.display_repeats[1]):
                for n3 in range(self.display_repeats[2]):
                    offset = np.array([n1, n2, n3], dtype=float) @ cell
                    for index, atom in enumerate(self.atoms):
                        if self.visible_species is not None and atom.element not in self.visible_species:
                            continue
                        position = np.asarray(self._atom_position(atom)) + offset
                        records.append((index, atom.element, *position.tolist(), (n1, n2, n3)))
        return records

    def reset_view(self):
        self.view_basis = None
        self.view_direction = np.array([0.0, 0.0, 1.0])
        self.rotation_x = -20.0
        self.rotation_y = 30.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.zoom = 1.0
        self._fit_structure()
        self.update()

    # -----------------------------------------------------------------
    # Painting
    # -----------------------------------------------------------------

    def paintEvent(self, event):

        painter = QPainter(self)

        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing
        )

        painter.fillRect(
            self.rect(),
            self.background_color,
        )

        if self.cell and self.show_cell:
            self._draw_cell(painter)

        if self.show_bonds:
            self._draw_bonds(painter)

        self._draw_atoms(painter)

        if self.show_axes:
            self._draw_axes(painter)

        if self.measurement_overlay:
            self._draw_measurement_overlay(
                painter
            )

        painter.setPen(
            QColor("#555C68")
        )

        painter.setFont(
            QFont("Segoe UI", 9)
        )

        painter.drawText(
            18,
            25,
            "3D STRUCTURE VIEW",
        )

    # -----------------------------------------------------------------
    # Unit cell
    # -----------------------------------------------------------------

    def _draw_cell(self, painter):

        a, b, c = self.cell

        corners = [
            (0, 0, 0),
            tuple(a),
            tuple(b),
            tuple(c),

            (
                a[0] + b[0],
                a[1] + b[1],
                a[2] + b[2],
            ),

            (
                a[0] + c[0],
                a[1] + c[1],
                a[2] + c[2],
            ),

            (
                b[0] + c[0],
                b[1] + c[1],
                b[2] + c[2],
            ),

            (
                a[0] + b[0] + c[0],
                a[1] + b[1] + c[1],
                a[2] + b[2] + c[2],
            ),
        ]

        edges = [
            (0, 1),
            (0, 2),
            (0, 3),
            (1, 4),
            (1, 5),
            (2, 4),
            (2, 6),
            (3, 5),
            (3, 6),
            (4, 7),
            (5, 7),
            (6, 7),
        ]

        projected = [
            self._project(*corner)
            for corner in corners
        ]

        painter.setPen(
            QPen(
                QColor("#515864"),
                1,
            )
        )

        for i, j in edges:

            p1 = projected[i]
            p2 = projected[j]

            painter.drawLine(
                int(p1[0]),
                int(p1[1]),
                int(p2[0]),
                int(p2[1]),
            )

    # -----------------------------------------------------------------
    # Bonds
    # -----------------------------------------------------------------

    def _draw_bonds(self, painter):

        records = self._display_atom_records()
        projected = {
            id(record): self._project(record[2], record[3], record[4])
            for record in records
        }
        painter.setPen(QPen(QColor("#707783"), 2))
        for i, first in enumerate(records):
            for second in records[i + 1:]:
                if first[5] != second[5]:
                    continue
                if self.visible_species is not None and (
                    first[1] not in self.visible_species or second[1] not in self.visible_species
                ):
                    continue
                distance = math.sqrt(sum((first[k] - second[k]) ** 2 for k in (2, 3, 4)))
                if distance <= 2.7:
                    p1, p2 = projected[id(first)], projected[id(second)]
                    painter.drawLine(int(p1[0]), int(p1[1]), int(p2[0]), int(p2[1]))

    # -----------------------------------------------------------------
    # Atoms
    # -----------------------------------------------------------------

    def _draw_atoms(self, painter):

        projected = []
        for record in self._display_atom_records():
            index, element, x0, y0, z0, offset = record
            x, y, z = self._project(x0, y0, z0)
            projected.append((z, index, element, x, y, offset))

        projected.sort(key=lambda item: item[0])
        for _, index, element, x, y, offset in projected:
            radius = 14 * self.atom_scale
            if index == self.selected_atom and offset == (0, 0, 0):
                selection_color = QColor("#111318") if self._light_background() else QColor("#FFFFFF")
                painter.setBrush(selection_color)
                painter.setPen(QPen(selection_color, 2))
                painter.drawEllipse(int(x - radius - 5), int(y - radius - 5), int(2 * radius + 10), int(2 * radius + 10))
            painter.setBrush(self._element_color(element))
            painter.setPen(QPen(QColor("#111318"), 1))
            painter.drawEllipse(int(x - radius), int(y - radius), int(2 * radius), int(2 * radius))
            if self.label_mode != "off":
                if self.label_mode == "element":
                    label = element
                elif self.label_mode == "index":
                    label = str(index + 1)
                else:
                    label = f"{element}{index + 1}"
                painter.setPen(
                    QColor("#111318") if self._light_background() else QColor("#FFFFFF")
                )
                painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
                painter.drawText(int(x - 24), int(y - 7), 48, 15, Qt.AlignmentFlag.AlignCenter, label)

    # -----------------------------------------------------------------
    # ROTATING ORIENTATION TRIAD
    # -----------------------------------------------------------------

    def _draw_axes(self, painter):

        origin_x = 65
        origin_y = self.height() - 65

        axis_length = 45

        axes = [
            (
                1.0,
                0.0,
                0.0,
                "x",
                QColor("#B66A6A"),
            ),
            (
                0.0,
                1.0,
                0.0,
                "y",
                QColor("#6E9D78"),
            ),
            (
                0.0,
                0.0,
                1.0,
                "z",
                QColor("#6D80AA"),
            ),
        ]

        # Project each 3D unit vector using the same rotation
        # used by the structure.
        for vx, vy, vz, label, color in axes:

            rx, ry, rz = self._rotate(
                vx,
                vy,
                vz,
            )

            magnitude = math.hypot(
                rx,
                ry,
            )

            if magnitude < 1e-8:
                continue

            dx = rx / magnitude
            dy = ry / magnitude

            end_x = (
                origin_x
                + dx * axis_length
            )

            end_y = (
                origin_y
                - dy * axis_length
            )

            painter.setPen(
                QPen(
                    color,
                    2,
                )
            )

            painter.drawLine(
                origin_x,
                origin_y,
                int(end_x),
                int(end_y),
            )

            painter.setBrush(color)

            painter.drawEllipse(
                int(end_x - 3),
                int(end_y - 3),
                6,
                6,
            )

            painter.setFont(
                QFont(
                    "Segoe UI",
                    9,
                    QFont.Weight.Bold,
                )
            )

            painter.drawText(
                int(end_x + 6),
                int(end_y - 4),
                label,
            )

        painter.setBrush(
            QColor("#E5E7EB")
        )

        painter.setPen(
            Qt.PenStyle.NoPen
        )

        painter.drawEllipse(
            origin_x - 3,
            origin_y - 3,
            6,
            6,
        )

    # -----------------------------------------------------------------
    # Element colours
    # -----------------------------------------------------------------

    @staticmethod
    def _element_color(element):

        colors = {
            "H": "#D8D8D8",
            "C": "#555555",
            "N": "#5275C7",
            "O": "#C95757",
            "F": "#69A45F",
            "P": "#CC7847",
            "S": "#C9A744",
            "Cl": "#56A26A",
            "Si": "#8A8A8A",
            "Ge": "#777777",
            "Se": "#D08A44",
            "Te": "#A56AA5",
            "Sb": "#7777A5",
            "Ta": "#668888",
            "Sn": "#888888",
        }

        return QColor(
            colors.get(
                element,
                "#AAAAAA",
            )
        )

    # -----------------------------------------------------------------
    # Mouse controls
    # -----------------------------------------------------------------

    def mousePressEvent(self, event):

        self.last_mouse = (
            event.position().toPoint()
        )

        if event.button() == Qt.MouseButton.LeftButton:
            self.rotating = True

        elif event.button() == Qt.MouseButton.MiddleButton:
            self.panning = True

        elif event.button() == Qt.MouseButton.RightButton:
            self._select(
                event.position().toPoint()
            )

    def mouseMoveEvent(self, event):

        current = (
            event.position().toPoint()
        )

        dx = (
            current.x()
            - self.last_mouse.x()
        )

        dy = (
            current.y()
            - self.last_mouse.y()
        )

        if self.rotating:

            self.rotation_y += dx * 0.6
            self.rotation_x += dy * 0.6

            self.update()

        elif self.panning:

            self.pan_x += dx
            self.pan_y += dy

            self.update()

        self.last_mouse = current

    def mouseReleaseEvent(self, event):

        if event.button() == Qt.MouseButton.LeftButton:
            self.rotating = False

        elif event.button() == Qt.MouseButton.MiddleButton:
            self.panning = False

    def wheelEvent(self, event):

        if event.angleDelta().y() > 0:
            self.zoom *= 1.12
        else:
            self.zoom /= 1.12

        self.zoom = max(
            0.15,
            min(self.zoom, 8.0),
        )

        self.update()

    def _select(self, position):

        closest = None
        distance_limit = 22

        for index, atom in enumerate(
            self.atoms
        ):

            x, y, _ = self._project(
                atom.x,
                atom.y,
                atom.z,
            )

            distance = math.hypot(
                x - position.x(),
                y - position.y(),
            )

            if distance < distance_limit:

                distance_limit = distance
                closest = index

        self.selected_atom = closest
        if callable(self.on_selection_changed):
            self.on_selection_changed(closest)
        self.update()

    # -----------------------------------------------------------------
    # Measurement visualization
    # -----------------------------------------------------------------

    def set_measurement_overlay(self, overlay):

        self.measurement_overlay = overlay

        self.update()

    def clear_measurement_overlay(self):

        self.measurement_overlay = None

        self.update()

    def _draw_measurement_overlay(
        self,
        painter,
    ):

        overlay = self.measurement_overlay

        if not overlay:
            return

        painter.save()

        # ---------------------------------------------------------
        # Projection helper
        # ---------------------------------------------------------

        def project(point):

            return self._project(
                float(point[0]),
                float(point[1]),
                float(point[2]),
            )

        # ---------------------------------------------------------
        # Styling
        # ---------------------------------------------------------

        measurement_pen = QPen(
            QColor("#E6B85C"),
            3,
        )

        measurement_pen.setCosmetic(
            True
        )

        atom_pen = QPen(
            QColor("#F4D58D"),
            3,
        )

        label_pen = QColor(
            "#F4D58D"
        )

        painter.setPen(
            measurement_pen
        )

        painter.setFont(
            QFont(
                "Segoe UI",
                10,
                QFont.Weight.Bold,
            )
        )

        # ---------------------------------------------------------
        # Highlight atom
        # ---------------------------------------------------------

        def highlight_atom(
            index,
        ):

            if (
                index is None
                or
                index < 0
                or
                index >= len(self.atoms)
            ):

                return None

            atom = self.atoms[index]

            x, y, _ = project(
                (
                    atom.x,
                    atom.y,
                    atom.z,
                )
            )

            painter.setBrush(
                Qt.BrushStyle.NoBrush
            )

            painter.setPen(
                atom_pen
            )

            painter.drawEllipse(
                int(x - 20),
                int(y - 20),
                40,
                40,
            )

            return (
                x,
                y,
            )

        # ---------------------------------------------------------
        # Draw label with dark backing
        # ---------------------------------------------------------

        def label(
            text,
            x,
            y,
        ):

            rect = QRectF(
                x - 5,
                y - 17,
                max(
                    80,
                    len(text) * 7.2 + 10,
                ),
                23,
            )

            painter.setPen(
                Qt.PenStyle.NoPen
            )

            painter.setBrush(
                QColor(
                    "#111318"
                )
            )

            painter.drawRoundedRect(
                rect,
                5,
                5,
            )

            painter.setPen(
                label_pen
            )

            painter.drawText(
                rect,
                Qt.AlignmentFlag.AlignCenter,
                text,
            )

        # ---------------------------------------------------------
        # Distance between atoms
        # ---------------------------------------------------------

        if overlay.get(
            "type"
        ) == "distance":

            indices = overlay[
                "atoms"
            ]

            points = [
                highlight_atom(
                    index
                )
                for index in indices
            ]

            if all(points):

                p1 = points[0]
                p2 = points[1]

                painter.setPen(
                    measurement_pen
                )

                painter.drawLine(
                    int(p1[0]),
                    int(p1[1]),
                    int(p2[0]),
                    int(p2[1]),
                )

                mx = (
                    p1[0] + p2[0]
                ) / 2

                my = (
                    p1[1] + p2[1]
                ) / 2

                label(
                    f"{overlay['value']:.4f} Å",
                    mx,
                    my,
                )

        # ---------------------------------------------------------
        # Bond angle
        # ---------------------------------------------------------

        elif overlay.get(
            "type"
        ) == "angle":

            indices = overlay[
                "atoms"
            ]

            points = [
                highlight_atom(
                    index
                )
                for index in indices
            ]

            if all(points):

                a, b, c = points

                painter.setPen(
                    measurement_pen
                )

                painter.drawLine(
                    int(a[0]),
                    int(a[1]),
                    int(b[0]),
                    int(b[1]),
                )

                painter.drawLine(
                    int(b[0]),
                    int(b[1]),
                    int(c[0]),
                    int(c[1]),
                )

                # Approximate projected angle arc.
                r = 38

                va_x = (
                    a[0] - b[0]
                )

                va_y = (
                    -(a[1] - b[1])
                )

                vc_x = (
                    c[0] - b[0]
                )

                vc_y = (
                    -(c[1] - b[1])
                )

                angle_a = math.degrees(
                    math.atan2(
                        va_y,
                        va_x,
                    )
                )

                angle_c = math.degrees(
                    math.atan2(
                        vc_y,
                        vc_x,
                    )
                )

                start = angle_a
                span = angle_c - angle_a

                while span <= -180:
                    span += 360

                while span > 180:
                    span -= 360

                painter.setPen(
                    measurement_pen
                )

                painter.drawArc(
                    QRectF(
                        b[0] - r,
                        b[1] - r,
                        2 * r,
                        2 * r,
                    ),
                    int(
                        -start * 16
                    ),
                    int(
                        -span * 16
                    ),
                )

                label(
                    f"{overlay['value']:.3f}°",
                    b[0] + 15,
                    b[1] - 35,
                )

        # ---------------------------------------------------------
        # Dihedral
        # ---------------------------------------------------------

        elif overlay.get(
            "type"
        ) == "dihedral":

            indices = overlay[
                "atoms"
            ]

            points = [
                highlight_atom(
                    index
                )
                for index in indices
            ]

            if all(points):

                painter.setPen(
                    measurement_pen
                )

                for first, second in zip(
                    points[:-1],
                    points[1:],
                ):

                    painter.drawLine(
                        int(first[0]),
                        int(first[1]),
                        int(second[0]),
                        int(second[1]),
                    )

                p2 = points[1]
                p3 = points[2]

                label(
                    f"{overlay['value']:.3f}°",
                    (
                        p2[0]
                        + p3[0]
                    ) / 2,
                    (
                        p2[1]
                        + p3[1]
                    ) / 2
                    - 30,
                )

        # ---------------------------------------------------------
        # Arbitrary point distance
        # ---------------------------------------------------------

        elif overlay.get(
            "type"
        ) == "point_distance":

            p1 = project(
                overlay["p1"]
            )

            p2 = project(
                overlay["p2"]
            )

            painter.setPen(
                measurement_pen
            )

            painter.setBrush(
                QColor(
                    "#F4D58D"
                )
            )

            painter.drawEllipse(
                int(p1[0] - 5),
                int(p1[1] - 5),
                10,
                10,
            )

            painter.drawEllipse(
                int(p2[0] - 5),
                int(p2[1] - 5),
                10,
                10,
            )

            painter.drawLine(
                int(p1[0]),
                int(p1[1]),
                int(p2[0]),
                int(p2[1]),
            )

            label(
                f"{overlay['value']:.4f} Å",
                (
                    p1[0] + p2[0]
                ) / 2,
                (
                    p1[1] + p2[1]
                ) / 2,
            )

        painter.restore()

    # -----------------------------------------------------------------
    # Viewport resize
    # -----------------------------------------------------------------

    def resizeEvent(self, event):

        super().resizeEvent(event)

        if self.atoms or self.cell:
            self._fit_structure()


# =====================================================================
# HETEROSTRUCTURE DIALOG
# =====================================================================


class HeterostructureDialog(QDialog):

    def __init__(self, parent=None):

        super().__init__(parent)

        self.setWindowTitle(
            "Create Heterostructure"
        )

        self.resize(500, 300)

        self.path_a = None
        self.path_b = None

        layout = QVBoxLayout(self)

        title = QLabel(
            "HETEROSTRUCTURE BUILDER"
        )

        title.setStyleSheet(
            "font-size: 15px; font-weight: 600;"
        )

        layout.addWidget(title)

        form = QFormLayout()

        self.file_a = QPushButton(
            "Choose Structure A"
        )

        self.file_b = QPushButton(
            "Choose Structure B"
        )

        self.label_a = QLabel(
            "No structure selected"
        )

        self.label_b = QLabel(
            "No structure selected"
        )

        row_a = QHBoxLayout()
        row_a.addWidget(self.file_a)
        row_a.addWidget(self.label_a, 1)

        row_b = QHBoxLayout()
        row_b.addWidget(self.file_b)
        row_b.addWidget(self.label_b, 1)

        form.addRow(
            "Layer A:",
            row_a,
        )

        form.addRow(
            "Layer B:",
            row_b,
        )

        self.direction = QComboBox()
        self.direction.addItems(
            ["Z", "Y", "X"]
        )

        self.spacing = QDoubleSpinBox()
        self.spacing.setRange(0, 100)
        self.spacing.setDecimals(2)
        self.spacing.setValue(3.0)
        self.spacing.setSuffix(" Å")

        self.repetitions_a = QSpinBox()
        self.repetitions_a.setRange(1, 20)
        self.repetitions_a.setValue(1)

        self.repetitions_b = QSpinBox()
        self.repetitions_b.setRange(1, 20)
        self.repetitions_b.setValue(1)

        form.addRow(
            "Stacking direction:",
            self.direction,
        )

        form.addRow(
            "Interface spacing:",
            self.spacing,
        )

        form.addRow(
            "A repetitions:",
            self.repetitions_a,
        )

        form.addRow(
            "B repetitions:",
            self.repetitions_b,
        )

        layout.addLayout(form)

        self.file_a.clicked.connect(
            self._choose_a
        )

        self.file_b.clicked.connect(
            self._choose_b
        )

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            |
            QDialogButtonBox.StandardButton.Cancel
        )

        buttons.accepted.connect(
            self.accept
        )

        buttons.rejected.connect(
            self.reject
        )

        layout.addWidget(buttons)

    def _choose_a(self):

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Structure A",
            str(Path.home()),
            "Structure files (*.cif *.vasp *.xyz *.xsf *.pdb);;All Files (*)",
        )

        if path:

            self.path_a = path

            self.label_a.setText(
                Path(path).name
            )

    def _choose_b(self):

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Structure B",
            str(Path.home()),
            "Structure files (*.cif *.vasp *.xyz *.xsf *.pdb);;All Files (*)",
        )

        if path:

            self.path_b = path

            self.label_b.setText(
                Path(path).name
            )


# =====================================================================
# LAYERED STRUCTURE DIALOG
# =====================================================================


class LayeredStructureDialog(QDialog):

    def __init__(self, parent=None):

        super().__init__(parent)

        self.setWindowTitle(
            "Create Layered Structure"
        )

        self.resize(500, 400)

        self.layers = []

        layout = QVBoxLayout(self)

        title = QLabel(
            "LAYERED STRUCTURE BUILDER"
        )

        title.setStyleSheet(
            "font-size: 15px; font-weight: 600;"
        )

        layout.addWidget(title)

        info = QLabel(
            "Build an arbitrary multilayer stack."
        )

        info.setStyleSheet(
            "color: #777D89;"
        )

        layout.addWidget(info)

        self.layer_list = QListWidget()

        layout.addWidget(
            self.layer_list
        )

        controls = QHBoxLayout()

        add_button = QPushButton(
            "Add Layer"
        )

        remove_button = QPushButton(
            "Remove"
        )

        up_button = QPushButton("↑")
        down_button = QPushButton("↓")

        controls.addWidget(add_button)
        controls.addWidget(remove_button)
        controls.addWidget(up_button)
        controls.addWidget(down_button)

        layout.addLayout(controls)

        form = QFormLayout()

        self.direction = QComboBox()
        self.direction.addItems(
            ["Z", "Y", "X"]
        )

        self.spacing = QDoubleSpinBox()
        self.spacing.setRange(0, 100)
        self.spacing.setDecimals(2)
        self.spacing.setValue(3.0)
        self.spacing.setSuffix(" Å")

        form.addRow(
            "Stacking direction:",
            self.direction,
        )

        form.addRow(
            "Interlayer spacing:",
            self.spacing,
        )

        layout.addLayout(form)

        add_button.clicked.connect(
            self._add_layer
        )

        remove_button.clicked.connect(
            self._remove_layer
        )

        up_button.clicked.connect(
            self._move_up
        )

        down_button.clicked.connect(
            self._move_down
        )

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            |
            QDialogButtonBox.StandardButton.Cancel
        )

        buttons.accepted.connect(
            self.accept
        )

        buttons.rejected.connect(
            self.reject
        )

        layout.addWidget(buttons)

    def _add_layer(self):

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Layer",
            str(Path.home()),
            "Structure files (*.cif *.vasp *.xyz *.xsf *.pdb);;All Files (*)",
        )

        if not path:
            return

        self.layers.append(path)

        self._refresh_list()

    def _remove_layer(self):

        row = self.layer_list.currentRow()

        if row < 0:
            return

        del self.layers[row]

        self._refresh_list()

    def _move_up(self):

        row = self.layer_list.currentRow()

        if row <= 0:
            return

        self.layers[row - 1], self.layers[row] = (
            self.layers[row],
            self.layers[row - 1],
        )

        self._refresh_list()

        self.layer_list.setCurrentRow(
            row - 1
        )

    def _move_down(self):

        row = self.layer_list.currentRow()

        if (
            row < 0
            or row >= len(self.layers) - 1
        ):
            return

        self.layers[row + 1], self.layers[row] = (
            self.layers[row],
            self.layers[row + 1],
        )

        self._refresh_list()

        self.layer_list.setCurrentRow(
            row + 1
        )

    def _refresh_list(self):

        self.layer_list.clear()

        for index, path in enumerate(
            self.layers
        ):

            self.layer_list.addItem(
                f"Layer {index + 1}    "
                f"{Path(path).name}"
            )


# =====================================================================
# BUILDER
# =====================================================================


class Builder(BuilderViewMixin, BuilderBuildMixin, BuilderMeasureMixin, QWidget):



    def _create_builder_toolbar(self):
        """Create the primary structure-editing toolbar."""

        from PySide6.QtWidgets import QFrame, QToolBar
        from PySide6.QtGui import QAction, QKeySequence

        toolbar = QToolBar("Structure Editing", self)

        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setIconSize(
            toolbar.iconSize()
        )

        toolbar.setObjectName(
            "builderToolbar"
        )

        # --------------------------------------------------------
        # Undo
        # --------------------------------------------------------

        self.action_undo = QAction(
            "↶  Undo",
            self,
        )

        self.action_undo.setToolTip(
            "Undo the last structure modification (Ctrl+Z)"
        )

        self.action_undo.setShortcut(
            QKeySequence("Ctrl+Z")
        )

        self.action_undo.setEnabled(
            False
        )

        self.action_undo.triggered.connect(
            self._qs_undo
        )

        toolbar.addAction(
            self.action_undo
        )

        # --------------------------------------------------------
        # Redo
        # --------------------------------------------------------

        self.action_redo = QAction(
            "↷  Redo",
            self,
        )

        self.action_redo.setToolTip(
            "Redo the last undone structure modification "
            "(Ctrl+Shift+Z)"
        )

        self.action_redo.setShortcut(
            QKeySequence("Ctrl+Shift+Z")
        )

        self.action_redo.setEnabled(
            False
        )

        self.action_redo.triggered.connect(
            self._qs_redo
        )

        toolbar.addAction(
            self.action_redo
        )

        toolbar.addSeparator()

        # --------------------------------------------------------
        # Structure operation status
        # --------------------------------------------------------

        self.history_status = QLabel(
            "No structure changes"
        )

        self.history_status.setObjectName(
            "historyStatus"
        )

        toolbar.addWidget(
            self.history_status
        )

        # --------------------------------------------------------
        # Add toolbar to the Builder.
        #
        # If the Builder has a QMainWindow-style layout,
        # use addToolBar(). Otherwise put it above the existing
        # central layout.
        # --------------------------------------------------------

        if hasattr(
            self,
            "addToolBar",
        ):

            self.addToolBar(
                Qt.TopToolBarArea,
                toolbar,
            )

        elif hasattr(
            self,
            "main_layout",
        ):

            self.main_layout.insertWidget(
                0,
                toolbar,
            )

        elif hasattr(
            self,
            "layout",
        ):

            try:

                self.layout().insertWidget(
                    0,
                    toolbar,
                )

            except Exception:

                pass

        else:

            # Store it so the main UI can attach it later.
            self.builder_toolbar = toolbar

        self.builder_toolbar = toolbar

        self._update_history_actions()


    def __init__(self, project):

        super().__init__()

        self.project = project

        self.structure = (
            self.project.get_structure()
        )

        self.viewport = StructureViewport()
        self.viewport.on_selection_changed = self._selection_changed_from_viewport

        # --------------------------------------------------------
        # Structure history must be initialized AFTER the initial
        # structure exists.
        # --------------------------------------------------------

        self._qs_initialize_history()

        if not hasattr(self, "history") or self.history is None:
            self.history = QListWidget()
            self.history.setObjectName(
                "quantumStudioHistory"
            )

        if not hasattr(self, "history_index"):
            self.history_index = -1

        if not hasattr(self, "_history_restoring"):
            self._history_restoring = False

        from copy import deepcopy

        self._qs_last_committed_structure = deepcopy(
            self.structure
        )

        self._build_ui()

        self._refresh_view()

    # -----------------------------------------------------------------

    def _build_ui(self):

        layout = QHBoxLayout(self)

        layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        layout.setSpacing(0)

        panel = QWidget()

        panel.setObjectName(
            "structurePanel"
        )

        panel.setFixedWidth(310)

        panel_layout = QVBoxLayout(panel)

        panel_layout.setContentsMargins(
            16,
            16,
            16,
            16,
        )

        title = QLabel(
            "STRUCTURE STUDIO"
        )

        title.setObjectName(
            "panelTitle"
        )

        panel_layout.addWidget(title)

        tabs = QTabWidget()

        tabs.addTab(
            self._build_view_tab(),
            "View",
        )

        tabs.addTab(
            self._build_build_tab(),
            "Build",
        )

        tabs.addTab(
            self._build_measure_tab(),
            "Measure",
        )

        # --------------------------------------------------------
        # History
        # --------------------------------------------------------

        history_page = QWidget()

        history_layout = QVBoxLayout(
            history_page
        )

        history_layout.setContentsMargins(
            8,
            12,
            8,
            8,
        )

        history_title = QLabel(
            "STRUCTURE HISTORY"
        )

        history_title.setObjectName(
            "sectionTitle"
        )

        history_layout.addWidget(
            history_title
        )

        if (
            not hasattr(self, "history")
            or self.history is None
        ):
            self.history = QListWidget()

            self.history.setObjectName(
                "quantumStudioHistory"
            )

        history_layout.addWidget(
            self.history,
            1,
        )

        tabs.addTab(
            history_page,
            "History",
        )

        panel_layout.addWidget(tabs)

        layout.addWidget(panel)

        layout.addWidget(
            self.viewport,
            1,
        )

        self.setStyleSheet(
            """
            QWidget {
                background: #111318;
                color: #E8EAF0;
                font-family:
                    "Inter",
                    "Segoe UI",
                    sans-serif;
            }

            #structurePanel {
                background: #17191F;
                border-right:
                    1px solid #292C34;
            }

            #panelTitle {
                color: #FFFFFF;
                font-size: 16px;
                font-weight: 600;
            }

            QTabWidget::pane {
                border: none;
            }

            QTabBar::tab {
                background: transparent;
                color: #777D89;
                padding: 9px 12px;
                border: none;
            }

            QTabBar::tab:selected {
                color: #FFFFFF;
                border-bottom:
                    2px solid #8B919D;
            }

            #sectionTitle {
                color: #777D89;
                font-size: 10px;
                font-weight: 600;
                letter-spacing: 1px;
            }

            QListWidget {
                background: #111318;
                border:
                    1px solid #292C34;
                border-radius: 7px;
            }

            QListWidget::item {
                padding: 7px;
                border-radius: 5px;
            }

            QListWidget::item:hover {
                background: #22252D;
            }

            QListWidget::item:selected {
                background: #2A2E38;
                color: #FFFFFF;
            }

            QCheckBox {
                color: #B9BEC8;
                spacing: 7px;
            }

            QPushButton {
                background: #252932;
                border: none;
                border-radius: 6px;
                padding: 8px 10px;
                color: #D9DCE3;
            }

            QPushButton:hover {
                background: #303540;
            }

            QDoubleSpinBox,
            QSpinBox,
            QComboBox {
                background: #111318;
                border:
                    1px solid #30343D;
                border-radius: 5px;
                padding: 5px;
                color: #FFFFFF;
            }

            #viewButton {
                background: #20242C;
                padding: 7px;
            }

            #viewButton:hover {
                background: #303540;
            }

            #infoLabel {
                color: #777D89;
                font-size: 10px;
            }

            #measurementResult {
                color: #FFFFFF;
                font-size: 12px;
                padding: 8px;
            }

            
            #builderToolbar {
                spacing: 6px;
                padding: 5px;
                background: #15171C;
                border-bottom: 1px solid #292C34;
            }

            #builderToolbar QToolButton {
                padding: 5px 10px;
                border-radius: 5px;
            }

            #builderToolbar QToolButton:hover {
                background: #292C34;
            }

            #builderToolbar QToolButton:disabled {
                color: #555A64;
            }

            #historyStatus {
                color: #7E8490;
                padding-left: 8px;
            }

#operationButton {
                text-align: left;
                padding: 10px;
            }
            """
        )

    # -----------------------------------------------------------------
    # View tab
    # -----------------------------------------------------------------


    # -----------------------------------------------------------------
    # Build tab
    # -----------------------------------------------------------------


    # -----------------------------------------------------------------
    # Refresh
    # -----------------------------------------------------------------

    def _refresh_view(self):

        self.viewport.set_structure(
            self.structure
        )

        self.atom_list.clear()

        for index, atom in enumerate(
            self.structure.atoms
        ):

            item = QListWidgetItem(
                f"{index + 1:03d}    "
                f"{atom.element}"
            )

            item.setData(
                Qt.ItemDataRole.UserRole,
                index,
            )

            self.atom_list.addItem(item)

        self.history.clear()

        for operation in (
            self.structure.history
        ):

            self.history.addItem(
                operation
            )

        a, b, c = self.structure.cell

        self.info.setText(
            f"Atoms: {len(self.structure.atoms)}\n\n"
            f"|a| = {self.structure.vector_length(a):.3f} Å\n"
            f"|b| = {self.structure.vector_length(b):.3f} Å\n"
            f"|c| = {self.structure.vector_length(c):.3f} Å"
        )

        self._refresh_measurement_atoms()
        self._rebuild_species_controls()
        self._update_selected_atom_info()

    # -----------------------------------------------------------------
    # Commit
    # -----------------------------------------------------------------

    def _commit(self):

        # A structure modification invalidates an existing
        # measurement overlay because the atom indices/coordinates
        # may have changed.
        if hasattr(
            self,
            "viewport",
        ):

            self.viewport.clear_measurement_overlay()

        self.project.set_structure(
            self.structure
        )

        self._refresh_view()

    # -----------------------------------------------------------------
    # Import
    # -----------------------------------------------------------------

    def _import_structure(self):

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Structure",
            str(Path.home()),
            (
                "All Supported Structures "
                "(*.cif *.xyz *.vasp *.xsf *.pdb *.mol *.sdf "
                "*.res *.gen POSCAR CONTCAR);;"
                "CIF (*.cif);;"
                "VASP (*.vasp POSCAR CONTCAR);;"
                "XYZ (*.xyz);;"
                "XSF (*.xsf);;"
                "PDB (*.pdb);;"
                "MOL/SDF (*.mol *.sdf);;"
                "All Files (*)"
            ),
        )

        if not path:
            return

        try:

            structure = (
                StructureIO.read_structure(path)
            )

            if not hasattr(structure, "atoms"):
                structure = StructureIO.from_ase(
                    structure,
                    name=Path(path).stem,
                )

            self.structure = structure

            self.structure._record(
                f"Imported {Path(path).name}"
            )

            self._commit()

        except Exception as error:

            QMessageBox.critical(
                self,
                "Import Failed",
                str(error),
            )

    # -----------------------------------------------------------------
    # Brillouin zone
    # -----------------------------------------------------------------

    def _open_bz(self):

        try:

            viewer = BrillouinZoneViewer(
                self.structure,
                self,
            )

            viewer.exec()

        except Exception as error:

            QMessageBox.critical(
                self,
                "Brillouin Zone Error",
                str(error),
            )

    # -----------------------------------------------------------------
    # Supercell
    # -----------------------------------------------------------------

    def _supercell(self):

        dialog = SupercellDialog(self)

        if (
            dialog.exec()
            != QDialog.DialogCode.Accepted
        ):
            return

        self.structure.make_supercell(
            dialog.nx.value(),
            dialog.ny.value(),
            dialog.nz.value(),
        )

        self._commit()

    # -----------------------------------------------------------------
    # Slab
    # -----------------------------------------------------------------

    def _slab(self):

        dialog = SlabDialog(self)

        if (
            dialog.exec()
            != QDialog.DialogCode.Accepted
        ):
            return

        self.structure.make_slab(
            dialog.layers.value(),
            dialog.direction.currentText().lower(),
            dialog.vacuum.value(),
        )

        self._commit()

    # -----------------------------------------------------------------
    # Vacuum
    # -----------------------------------------------------------------

    def _vacuum(self):

        dialog = VacuumDialog(self)

        if (
            dialog.exec()
            != QDialog.DialogCode.Accepted
        ):
            return

        self.structure.add_vacuum(
            dialog.amount.value(),
            dialog.direction.currentText().lower(),
        )

        self._commit()

    # -----------------------------------------------------------------
    # Strain
    # -----------------------------------------------------------------

    def _strain(self):

        dialog = StrainDialog(self)

        if (
            dialog.exec()
            != QDialog.DialogCode.Accepted
        ):
            return

        directions = {
            "Biaxial": "biaxial",
            "Uniaxial X": "uniaxial-x",
            "Uniaxial Y": "uniaxial-y",
            "Uniaxial Z": "uniaxial-z",
        }

        self.structure.apply_strain(
            dialog.value.value(),
            directions[
                dialog.direction.currentText()
            ],
        )

        self._commit()

    # -----------------------------------------------------------------
    # Nanotube
    # -----------------------------------------------------------------

    def _nanotube(self):

        dialog = NanotubeDialog(self)

        if (
            dialog.exec()
            != QDialog.DialogCode.Accepted
        ):
            return

        try:

            self.structure.make_nanotube(
                dialog.n.value(),
                dialog.m.value(),
            )

            self._commit()

        except Exception as error:

            QMessageBox.critical(
                self,
                "Nanotube Generation Failed",
                str(error),
            )

    # -----------------------------------------------------------------
    # Heterostructure
    # -----------------------------------------------------------------

    def _heterostructure(self):

        dialog = HeterostructureDialog(self)

        if (
            dialog.exec()
            != QDialog.DialogCode.Accepted
        ):
            return

        if not dialog.path_a:

            QMessageBox.warning(
                self,
                "Missing Structure",
                "Please select Structure A.",
            )

            return

        if not dialog.path_b:

            QMessageBox.warning(
                self,
                "Missing Structure",
                "Please select Structure B.",
            )

            return

        try:

            structure_a = (
                StructureIO.read_structure(
                    dialog.path_a
                )
            )

            structure_b = (
                StructureIO.read_structure(
                    dialog.path_b
                )
            )

            from frontend.builder.build.operations import (
                create_heterostructure,
            )

            result = create_heterostructure(
                structure_a,
                structure_b,
                direction=(
                    dialog.direction
                    .currentText()
                    .lower()
                ),
                spacing=dialog.spacing.value(),
                repetitions_a=(
                    dialog.repetitions_a.value()
                ),
                repetitions_b=(
                    dialog.repetitions_b.value()
                ),
            )

            self.structure = result

            self._commit()

        except Exception as error:

            QMessageBox.critical(
                self,
                "Heterostructure Failed",
                str(error),
            )

    # -----------------------------------------------------------------
    # Layered structure
    # -----------------------------------------------------------------

    def _layered_structure(self):

        dialog = LayeredStructureDialog(self)

        if (
            dialog.exec()
            != QDialog.DialogCode.Accepted
        ):
            return

        if not dialog.layers:

            QMessageBox.warning(
                self,
                "No Layers",
                "Add at least one structure layer.",
            )

            return

        try:

            structures = [
                StructureIO.read_structure(
                    path
                )
                for path in dialog.layers
            ]

            from frontend.builder.build.operations import (
                stack_layers,
            )

            result = stack_layers(
                structures[0],
                structures,
                direction=(
                    dialog.direction
                    .currentText()
                    .lower()
                ),
                spacing=dialog.spacing.value(),
            )

            self.structure = result

            self._commit()

        except Exception as error:

            QMessageBox.critical(
                self,
                "Layered Structure Failed",
                str(error),
            )

    # -----------------------------------------------------------------
    # View controls
    # -----------------------------------------------------------------

    def _select_atom_from_list(self, item):

        self.viewport.selected_atom = item.data(Qt.ItemDataRole.UserRole)
        self._update_selected_atom_info()
        self.viewport.update()

    def _toggle_bonds(self, state):

        self.viewport.show_bonds = (
            state
            == Qt.CheckState.Checked.value
        )

        self.viewport.update()

    def _toggle_cell(self, state):

        self.viewport.show_cell = (
            state
            == Qt.CheckState.Checked.value
        )

        self.viewport.update()

    def _toggle_axes(self, state):

        self.viewport.show_axes = (
            state
            == Qt.CheckState.Checked.value
        )

        self.viewport.update()

    def _selection_changed_from_viewport(self, index):
        if index is not None and hasattr(self, "atom_list"):
            for row in range(self.atom_list.count()):
                item = self.atom_list.item(row)
                if item.data(Qt.ItemDataRole.UserRole) == index:
                    self.atom_list.setCurrentItem(item)
                    break
        self._update_selected_atom_info()

    def _set_label_mode(self, mode):
        self.viewport.set_label_mode(mode)

    def _set_projection_mode(self, mode):
        self.viewport.set_projection_mode(mode)

    def _set_crystallographic_view(self, name):
        try:
            cell = np.asarray(self.structure.cell, dtype=float)
            reciprocal_index = {"x*": 0, "y*": 1, "z*": 2}
            key = str(name).strip().lower()
            if key not in reciprocal_index:
                raise ValueError("Unknown crystallographic view; use X*, Y*, or Z*.")
            direction = reciprocal_lattice(cell)[reciprocal_index[key]]
            self.viewport.set_view_direction(direction)
        except Exception as error:
            QMessageBox.warning(self, "View Unavailable", str(error))

    def _view_miller_plane(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("View Miller Plane")
        form = QFormLayout(dialog)
        boxes = []
        for label in ("h", "k", "l"):
            box = QSpinBox(dialog)
            box.setRange(-999, 999)
            form.addRow(label, box)
            boxes.append(box)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, parent=dialog)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            direction = miller_normal(self.structure.cell, *(box.value() for box in boxes))
            self.viewport.set_view_direction(direction)
        except Exception as error:
            QMessageBox.warning(self, "Miller Plane Unavailable", str(error))

    def _set_periodic_display_preset(self, value):
        presets = {
            "1 × 1 × 1": (1, 1, 1),
            "2 × 2 × 1": (2, 2, 1),
            "2 × 2 × 2": (2, 2, 2),
            "3 × 3 × 1": (3, 3, 1),
        }
        if value in presets:
            self.viewport.set_periodic_display(*presets[value])

    def _rebuild_species_controls(self):
        if not hasattr(self, "species_layout"):
            return
        while self.species_layout.count():
            item = self.species_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for element in sorted({atom.element for atom in self.structure.atoms}):
            checkbox = QCheckBox(element)
            checkbox.setChecked(True)
            checkbox.stateChanged.connect(self._species_visibility_changed)
            self.species_layout.addWidget(checkbox)

    def _species_visibility_changed(self, _state):
        visible = set()
        for index in range(self.species_layout.count()):
            widget = self.species_layout.itemAt(index).widget()
            if widget is not None and widget.isChecked():
                visible.add(widget.text())
        self.viewport.set_visible_species(visible)

    def _selected_atom_details(self):
        index = self.viewport.selected_atom
        if index is None or not (0 <= index < len(self.structure.atoms)):
            return "No atom selected"
        atom = self.structure.atoms[index]
        cart = np.array([atom.x, atom.y, atom.z], dtype=float)
        try:
            frac = fractional_coordinates(cart, self.structure.cell)
            fractional_text = "u,v,w: " + ", ".join(f"{value:.5f}" for value in frac)
        except ValueError:
            fractional_text = "Fractional: unavailable"
        neighbours = []
        for other_index, other in enumerate(self.structure.atoms):
            if other_index == index:
                continue
            distance = minimum_image_distance(
                cart, [other.x, other.y, other.z], self.structure.cell,
                getattr(self.structure, "periodic", (True, True, True)),
            )
            if distance <= 2.7:
                neighbours.append((distance, other_index, other.element))
        neighbours.sort()
        neighbour_text = ", ".join(f"{i + 1}:{element} {distance:.3f} Å" for distance, i, element in neighbours[:8]) or "none"
        return (
            f"Index: {index + 1}    Element: {atom.element}\n"
            f"Cartesian: {cart[0]:.5f}, {cart[1]:.5f}, {cart[2]:.5f} Å\n"
            f"{fractional_text}\n"
            f"Coordination: {len(neighbours)}\n"
            f"Neighbors: {neighbour_text}"
        )

    def _update_selected_atom_info(self):
        if hasattr(self, "selected_info"):
            self.selected_info.setText(self._selected_atom_details())

    def _center_on_selected(self):
        self.viewport.center_on_selected()

    def _export_view(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export View", "builder-view.png", "PNG image (*.png)")
        if path:
            if not path.lower().endswith(".png"):
                path += ".png"
            self.viewport.grab().save(path, "PNG")

    def _change_atom_size(self, value):

        self.viewport.atom_scale = (
            value / 100.0
        )

        self.viewport.update()


# =====================================================================
# BASIC DIALOGS
# =====================================================================


    # ========================================================
    # QUANTUM STUDIO — STRUCTURE HISTORY
    # ========================================================

    def _qs_initialize_history(self):
        """
        Initialize the complete structure undo/redo system.
        """

        if not hasattr(
            self,
            "_qs_undo_stack",
        ):
            self._qs_undo_stack = []

        if not hasattr(
            self,
            "_qs_redo_stack",
        ):
            self._qs_redo_stack = []

        if not hasattr(
            self,
            "_qs_last_committed_structure",
        ):

            from copy import deepcopy

            self._qs_last_committed_structure = deepcopy(
                self.structure
            )

    # --------------------------------------------------------
    # Snapshot
    # --------------------------------------------------------

    def _qs_snapshot(self):
        """
        Store the currently committed structure as the state
        immediately preceding a new modification.
        """

        from copy import deepcopy

        self._qs_initialize_history()

        self._qs_undo_stack.append(
            deepcopy(
                self._qs_last_committed_structure
            )
        )

        self._qs_redo_stack.clear()

        self._update_history_actions()

    # --------------------------------------------------------
    # Undo
    # --------------------------------------------------------

    def _qs_undo(self):
        """
        Restore the previous committed structure.
        """

        from copy import deepcopy

        self._qs_initialize_history()

        if not self._qs_undo_stack:

            self.statusBarMessage(
                "Nothing to undo."
            )

            return

        # Current state goes to redo.
        self._qs_redo_stack.append(
            deepcopy(
                self.structure
            )
        )

        # Restore previous state.
        self.structure = (
            self._qs_undo_stack.pop()
        )

        self._qs_last_committed_structure = (
            deepcopy(
                self.structure
            )
        )

        # Push restored structure into the project.
        self.project.set_structure(
            self.structure
        )

        self._refresh_view()

        self._update_history_actions()

        self.statusBarMessage(
            "Undo complete."
        )

    # --------------------------------------------------------
    # Redo
    # --------------------------------------------------------

    def _qs_redo(self):
        """
        Restore the next structure from the redo stack.
        """

        from copy import deepcopy

        self._qs_initialize_history()

        if not self._qs_redo_stack:

            self.statusBarMessage(
                "Nothing to redo."
            )

            return

        # Current state goes back to undo.
        self._qs_undo_stack.append(
            deepcopy(
                self.structure
            )
        )

        # Restore redo state.
        self.structure = (
            self._qs_redo_stack.pop()
        )

        self._qs_last_committed_structure = (
            deepcopy(
                self.structure
            )
        )

        self.project.set_structure(
            self.structure
        )

        self._refresh_view()

        self._update_history_actions()

        self.statusBarMessage(
            "Redo complete."
        )

    # --------------------------------------------------------
    # Commit
    # --------------------------------------------------------

    def _commit(self):

        from copy import deepcopy

        self._qs_initialize_history()

        # The operation has already modified self.structure.
        #
        # Therefore _qs_last_committed_structure is the state
        # that existed immediately BEFORE the operation.
        self._qs_undo_stack.append(
            deepcopy(
                self._qs_last_committed_structure
            )
        )

        # A new modification invalidates the redo branch.
        self._qs_redo_stack.clear()

        # Commit the new structure.
        self.project.set_structure(
            self.structure
        )

        # This becomes the new baseline for the next operation.
        self._qs_last_committed_structure = (
            deepcopy(
                self.structure
            )
        )

        self._refresh_view()

        self._update_history_actions()

    # --------------------------------------------------------
    # History toolbar state
    # --------------------------------------------------------

    def _update_history_actions(self):

        self._qs_initialize_history()

        can_undo = bool(
            self._qs_undo_stack
        )

        can_redo = bool(
            self._qs_redo_stack
        )

        # The actual toolbar is owned by ProjectWindow.
        #
        # Update it through the parent window.
        window = self.window()

        if window is not None:

            if hasattr(
                window,
                "undo_action",
            ):

                window.undo_action.setEnabled(
                    can_undo
                )

            if hasattr(
                window,
                "redo_action",
            ):

                window.redo_action.setEnabled(
                    can_redo
                )

        # Also support the old Builder toolbar if it still
        # exists during the transition.
        if hasattr(
            self,
            "action_undo",
        ):

            self.action_undo.setEnabled(
                can_undo
            )

        if hasattr(
            self,
            "action_redo",
        ):

            self.action_redo.setEnabled(
                can_redo
            )

        if hasattr(
            self,
            "history_status",
        ):

            if can_undo and can_redo:

                self.history_status.setText(
                    f"{len(self._qs_undo_stack)} undo"
                    f"  •  "
                    f"{len(self._qs_redo_stack)} redo"
                )

            elif can_undo:

                self.history_status.setText(
                    f"{len(self._qs_undo_stack)} undo"
                )

            elif can_redo:

                self.history_status.setText(
                    f"{len(self._qs_redo_stack)} redo"
                )

            else:

                self.history_status.setText(
                    "No structure changes"
                )

    # --------------------------------------------------------
    # Status message helper
    # --------------------------------------------------------

    def statusBarMessage(
        self,
        message,
    ):

        window = self.window()

        if window is not None:

            try:

                window.statusBar().showMessage(
                    message,
                    3000,
                )

            except Exception:
                pass

    # --------------------------------------------------------
    # Compatibility refresh
    # --------------------------------------------------------

    def _qs_refresh_after_structure_change(
        self,
        operation="Structure modified",
    ):

        self._refresh_view()

        self._update_history_actions()

        self.statusBarMessage(
            operation
        )


class SupercellDialog(QDialog):

    def __init__(self, parent=None):

        super().__init__(parent)

        self.setWindowTitle(
            "Create Supercell"
        )

        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)

        form = QFormLayout()

        self.nx = QSpinBox()
        self.ny = QSpinBox()
        self.nz = QSpinBox()

        for box in (
            self.nx,
            self.ny,
            self.nz,
        ):

            box.setRange(
                1,
                50,
            )

            box.setValue(1)


        form.addRow(
            "A scaling:",
            self.nx,
        )

        form.addRow(
            "B scaling:",
            self.ny,
        )

        form.addRow(
            "C scaling:",
            self.nz,
        )


        layout.addLayout(
            form
        )


        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            |
            QDialogButtonBox.StandardButton.Cancel
        )

        buttons.accepted.connect(
            self.accept
        )

        buttons.rejected.connect(
            self.reject
        )

        layout.addWidget(
            buttons
        )


class StrainDialog(QDialog):

    def __init__(self, parent=None):

        super().__init__(parent)

        self.setWindowTitle(
            "Apply Strain"
        )

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.value = QDoubleSpinBox()

        self.value.setRange(
            -50,
            50,
        )

        self.value.setDecimals(3)
        self.value.setSuffix(" %")

        self.direction = QComboBox()

        self.direction.addItems(
            [
                "Biaxial",
                "Uniaxial X",
                "Uniaxial Y",
                "Uniaxial Z",
            ]
        )

        form.addRow(
            "Strain:",
            self.value,
        )

        form.addRow(
            "Direction:",
            self.direction,
        )

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            |
            QDialogButtonBox.StandardButton.Cancel
        )

        buttons.accepted.connect(
            self.accept
        )

        buttons.rejected.connect(
            self.reject
        )

        layout.addWidget(buttons)


class VacuumDialog(QDialog):

    def __init__(self, parent=None):

        super().__init__(parent)

        self.setWindowTitle(
            "Add Vacuum"
        )

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.amount = QDoubleSpinBox()

        self.amount.setRange(
            0,
            200,
        )

        self.amount.setValue(15)
        self.amount.setSuffix(" Å")

        self.direction = QComboBox()

        self.direction.addItems(
            [
                "X",
                "Y",
                "Z",
            ]
        )

        form.addRow(
            "Vacuum:",
            self.amount,
        )

        form.addRow(
            "Direction:",
            self.direction,
        )

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            |
            QDialogButtonBox.StandardButton.Cancel
        )

        buttons.accepted.connect(
            self.accept
        )

        buttons.rejected.connect(
            self.reject
        )

        layout.addWidget(buttons)


class SlabDialog(QDialog):

    def __init__(self, parent=None):

        super().__init__(parent)

        self.setWindowTitle(
            "Create Slab"
        )

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.layers = QSpinBox()

        self.layers.setRange(
            1,
            100,
        )

        self.layers.setValue(1)

        self.vacuum = QDoubleSpinBox()

        self.vacuum.setRange(
            0,
            200,
        )

        self.vacuum.setValue(15)
        self.vacuum.setSuffix(" Å")

        self.direction = QComboBox()

        self.direction.addItems(
            [
                "X",
                "Y",
                "Z",
            ]
        )

        form.addRow(
            "Layers:",
            self.layers,
        )

        form.addRow(
            "Direction:",
            self.direction,
        )

        form.addRow(
            "Vacuum:",
            self.vacuum,
        )

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            |
            QDialogButtonBox.StandardButton.Cancel
        )

        buttons.accepted.connect(
            self.accept
        )

        buttons.rejected.connect(
            self.reject
        )

        layout.addWidget(buttons)


class NanotubeDialog(QDialog):

    def __init__(self, parent=None):

        super().__init__(parent)

        self.setWindowTitle(
            "Create Nanotube"
        )

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.n = QSpinBox()
        self.m = QSpinBox()

        self.n.setRange(0, 30)
        self.m.setRange(0, 30)

        self.n.setValue(5)
        self.m.setValue(5)

        form.addRow(
            "Chiral index n:",
            self.n,
        )

        form.addRow(
            "Chiral index m:",
            self.m,
        )

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            |
            QDialogButtonBox.StandardButton.Cancel
        )

        buttons.accepted.connect(
            self.accept
        )

        buttons.rejected.connect(
            self.reject
        )

        layout.addWidget(buttons)
