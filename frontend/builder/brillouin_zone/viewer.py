import math

import numpy as np
from scipy.spatial import Voronoi

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


# =================================================================
# Brillouin Zone Viewport
# =================================================================


class BrillouinZoneViewport(QWidget):

    def __init__(
        self,
        reciprocal,
        parent=None,
    ):

        super().__init__(parent)

        self.reciprocal = np.array(
            reciprocal,
            dtype=float,
        )

        self.vertices = np.empty(
            (0, 3)
        )

        self.edges = []

        self.rotation_x = -20.0
        self.rotation_y = 30.0

        self.zoom = 1.0

        self.pan_x = 0.0
        self.pan_y = 0.0

        self.last_mouse = QPoint()

        self.rotating = False
        self.panning = False

        self._build_bz()

    # ============================================================
    # Brillouin zone construction
    # ============================================================

    def _build_bz(self):

        reciprocal_points = []

        # Reciprocal lattice points surrounding Gamma.
        for h in range(-3, 4):

            for k in range(-3, 4):

                for l in range(-3, 4):

                    point = (
                        h * self.reciprocal[0]
                        + k * self.reciprocal[1]
                        + l * self.reciprocal[2]
                    )

                    reciprocal_points.append(
                        point
                    )

        reciprocal_points = np.array(
            reciprocal_points,
            dtype=float,
        )

        # Locate Gamma.
        gamma_index = None

        for index, point in enumerate(
            reciprocal_points
        ):

            if np.linalg.norm(point) < 1e-10:

                gamma_index = index
                break

        if gamma_index is None:

            raise RuntimeError(
                "Could not locate Γ in reciprocal space."
            )

        try:

            voronoi = Voronoi(
                reciprocal_points
            )

        except Exception as error:

            raise RuntimeError(
                "Could not construct the reciprocal-space "
                "Voronoi tessellation."
            ) from error

        region_index = (
            voronoi.point_region[
                gamma_index
            ]
        )

        region = voronoi.regions[
            region_index
        ]

        # An infinite region means the reciprocal-space
        # sampling was insufficient.
        if not region or -1 in region:

            raise RuntimeError(
                "The first Brillouin zone could not be "
                "closed. Increase reciprocal lattice sampling."
            )

        self.vertices = np.array(
            [
                voronoi.vertices[index]
                for index in region
            ],
            dtype=float,
        )

        # Map Voronoi vertex IDs to local BZ vertex IDs.
        vertex_lookup = {
            original_index: local_index
            for local_index, original_index
            in enumerate(region)
        }

        edge_set = set()

        for ridge_points, ridge_vertices in zip(
            voronoi.ridge_points,
            voronoi.ridge_vertices,
        ):

            if gamma_index not in ridge_points:
                continue

            if -1 in ridge_vertices:
                continue

            local_vertices = [
                vertex
                for vertex in ridge_vertices
                if vertex in vertex_lookup
            ]

            if len(local_vertices) < 2:
                continue

            for i in range(
                len(local_vertices)
            ):

                for j in range(
                    i + 1,
                    len(local_vertices),
                ):

                    a = vertex_lookup[
                        local_vertices[i]
                    ]

                    b = vertex_lookup[
                        local_vertices[j]
                    ]

                    edge_set.add(
                        tuple(
                            sorted(
                                (a, b)
                            )
                        )
                    )

        self.edges = sorted(
            edge_set
        )

    # ============================================================
    # Standard views
    # ============================================================

    def set_view(
        self,
        axis,
    ):

        axis = axis.lower()

        if axis == "x":

            self.rotation_x = 0.0
            self.rotation_y = 90.0

        elif axis == "y":

            self.rotation_x = 90.0
            self.rotation_y = 0.0

        elif axis == "z":

            self.rotation_x = 0.0
            self.rotation_y = 0.0

        self.pan_x = 0.0
        self.pan_y = 0.0

        self.zoom = 1.0

        self._fit_bz()

        self.update()

    def reset_view(self):

        self.rotation_x = -20.0
        self.rotation_y = 30.0

        self.pan_x = 0.0
        self.pan_y = 0.0

        self.zoom = 1.0

        self._fit_bz()

        self.update()

    # ============================================================
    # Automatic fitting
    # ============================================================

    def _fit_bz(self):

        if len(self.vertices) == 0:
            return

        projected = []

        for vertex in self.vertices:

            x, y, _ = self._rotate(
                vertex
            )

            projected.append(
                (
                    x,
                    y,
                )
            )

        projected = np.array(
            projected
        )

        width = (
            projected[:, 0].max()
            - projected[:, 0].min()
        )

        height = (
            projected[:, 1].max()
            - projected[:, 1].min()
        )

        largest = max(
            width,
            height,
            1e-8,
        )

        available = min(
            self.width(),
            self.height(),
        ) * 0.65

        # Base projection scale is approximately
        # 0.20 * viewport size.
        self.zoom = (
            available
            / (
                largest
                * min(
                    self.width(),
                    self.height(),
                )
                * 0.20
            )
        )

        self.zoom = max(
            0.25,
            min(
                self.zoom,
                5.0,
            ),
        )

    # ============================================================
    # Rotation
    # ============================================================

    def _rotate(
        self,
        vector,
    ):

        x, y, z = vector

        rx = math.radians(
            self.rotation_x
        )

        ry = math.radians(
            self.rotation_y
        )

        y1 = (
            y * math.cos(rx)
            - z * math.sin(rx)
        )

        z1 = (
            y * math.sin(rx)
            + z * math.cos(rx)
        )

        x2 = (
            x * math.cos(ry)
            + z1 * math.sin(ry)
        )

        z2 = (
            -x * math.sin(ry)
            + z1 * math.cos(ry)
        )

        return (
            x2,
            y1,
            z2,
        )

    # ============================================================
    # Projection
    # ============================================================

    def _project(
        self,
        vector,
    ):

        x, y, z = self._rotate(
            vector
        )

        base_scale = (
            min(
                self.width(),
                self.height(),
            )
            * 0.20
            * self.zoom
        )

        return (
            self.width() / 2
            + x * base_scale
            + self.pan_x,

            self.height() / 2
            - y * base_scale
            + self.pan_y,

            z,
        )

    # ============================================================
    # Painting
    # ============================================================

    def paintEvent(
        self,
        event,
    ):

        painter = QPainter(
            self
        )

        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing
        )

        painter.fillRect(
            self.rect(),
            QColor("#0D0F13"),
        )

        if len(self.vertices) == 0:
            return

        projected = [
            self._project(
                vertex
            )
            for vertex in self.vertices
        ]

        # --------------------------------------------------------
        # BZ edges
        # --------------------------------------------------------

        painter.setPen(
            QPen(
                QColor("#AEB4C0"),
                2,
            )
        )

        for a, b in self.edges:

            p1 = projected[a]
            p2 = projected[b]

            painter.drawLine(
                int(p1[0]),
                int(p1[1]),
                int(p2[0]),
                int(p2[1]),
            )

        # --------------------------------------------------------
        # BZ vertices
        # --------------------------------------------------------

        painter.setPen(
            Qt.PenStyle.NoPen
        )

        painter.setBrush(
            QColor("#D9DCE2")
        )

        for x, y, z in projected:

            painter.drawEllipse(
                int(x - 3),
                int(y - 3),
                6,
                6,
            )

        # --------------------------------------------------------
        # Gamma
        # --------------------------------------------------------

        gamma = self._project(
            np.zeros(3)
        )

        painter.setBrush(
            QColor("#FFFFFF")
        )

        painter.drawEllipse(
            int(gamma[0] - 5),
            int(gamma[1] - 5),
            10,
            10,
        )

        painter.setPen(
            QColor("#FFFFFF")
        )

        painter.setFont(
            QFont(
                "Segoe UI",
                11,
                QFont.Weight.Bold,
            )
        )

        painter.drawText(
            int(gamma[0] + 9),
            int(gamma[1] - 8),
            "Γ",
        )

        # --------------------------------------------------------
        # Reciprocal axes
        # --------------------------------------------------------

        self._draw_axes(
            painter
        )

        # --------------------------------------------------------
        # Label
        # --------------------------------------------------------

        painter.setPen(
            QColor("#626974")
        )

        painter.setFont(
            QFont(
                "Segoe UI",
                9,
            )
        )

        painter.drawText(
            18,
            25,
            "FIRST BRILLOUIN ZONE",
        )

    # ============================================================
    # Reciprocal axes
    # ============================================================

    def _draw_axes(
        self,
        painter,
    ):

        origin = np.zeros(3)

        axes = [
            (
                self.reciprocal[0],
                "b₁",
                QColor("#B66A6A"),
            ),
            (
                self.reciprocal[1],
                "b₂",
                QColor("#6E9D78"),
            ),
            (
                self.reciprocal[2],
                "b₃",
                QColor("#6D80AA"),
            ),
        ]

        origin_projected = self._project(
            origin
        )

        ox = origin_projected[0]
        oy = origin_projected[1]

        for vector, label, color in axes:

            endpoint = self._project(
                vector
            )

            painter.setPen(
                QPen(
                    color,
                    2,
                )
            )

            painter.drawLine(
                int(ox),
                int(oy),
                int(endpoint[0]),
                int(endpoint[1]),
            )

            painter.drawText(
                int(endpoint[0] + 6),
                int(endpoint[1]),
                label,
            )

    # ============================================================
    # Mouse interaction
    # ============================================================

    def mousePressEvent(
        self,
        event,
    ):

        self.last_mouse = (
            event.position().toPoint()
        )

        if (
            event.button()
            == Qt.MouseButton.LeftButton
        ):

            self.rotating = True

        elif (
            event.button()
            == Qt.MouseButton.MiddleButton
        ):

            self.panning = True

    def mouseMoveEvent(
        self,
        event,
    ):

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

            self.rotation_y += (
                dx * 0.6
            )

            self.rotation_x += (
                dy * 0.6
            )

        elif self.panning:

            self.pan_x += dx
            self.pan_y += dy

        self.last_mouse = current

        self.update()

    def mouseReleaseEvent(
        self,
        event,
    ):

        if (
            event.button()
            == Qt.MouseButton.LeftButton
        ):

            self.rotating = False

        elif (
            event.button()
            == Qt.MouseButton.MiddleButton
        ):

            self.panning = False

    def wheelEvent(
        self,
        event,
    ):

        if event.angleDelta().y() > 0:

            self.zoom *= 1.12

        else:

            self.zoom /= 1.12

        self.zoom = max(
            0.2,
            min(
                self.zoom,
                8.0,
            ),
        )

        self.update()


# =================================================================
# Brillouin Zone Viewer
# =================================================================


class BrillouinZoneViewer(QDialog):

    def __init__(
        self,
        structure,
        parent=None,
    ):

        super().__init__(
            parent
        )

        self.setWindowTitle(
            "Quantum Studio — Brillouin Zone"
        )

        self.resize(
            900,
            650,
        )

        self.setStyleSheet(
            """
            QDialog {
                background: #111318;
                color: #E8EAF0;
            }

            QLabel {
                color: #E8EAF0;
            }

            QPushButton {
                background: #252932;
                border: none;
                border-radius: 6px;
                padding: 7px 11px;
                color: #D9DCE3;
            }

            QPushButton:hover {
                background: #303540;
            }
            """
        )

        reciprocal = (
            self._reciprocal_lattice(
                structure.cell
            )
        )

        # IMPORTANT:
        # Create the viewport BEFORE creating buttons whose
        # callbacks reference it.
        self.viewport = (
            BrillouinZoneViewport(
                reciprocal,
                self,
            )
        )

        self._build_ui(
            reciprocal
        )

    # ============================================================
    # UI
    # ============================================================

    def _build_ui(
        self,
        reciprocal,
    ):

        layout = QVBoxLayout(
            self
        )

        toolbar = QHBoxLayout()

        title = QLabel(
            "Brillouin Zone"
        )

        title.setStyleSheet(
            """
            font-size: 16px;
            font-weight: 600;
            """
        )

        toolbar.addWidget(
            title
        )

        toolbar.addStretch()

        for label in (
            "X",
            "Y",
            "Z",
        ):

            button = QPushButton(
                label
            )

            button.setFixedWidth(
                42
            )

            button.clicked.connect(
                lambda checked=False,
                axis=label.lower():
                self.viewport.set_view(
                    axis
                )
            )

            toolbar.addWidget(
                button
            )

        reset = QPushButton(
            "Reset"
        )

        reset.clicked.connect(
            self.viewport.reset_view
        )

        toolbar.addWidget(
            reset
        )

        layout.addLayout(
            toolbar
        )

        layout.addWidget(
            self.viewport,
            1,
        )

        info = QLabel(
            self._reciprocal_info(
                reciprocal
            )
        )

        info.setStyleSheet(
            """
            color: #777D89;
            padding: 6px;
            font-size: 10px;
            """
        )

        layout.addWidget(
            info
        )

    # ============================================================
    # Reciprocal lattice
    # ============================================================

    @staticmethod
    def _reciprocal_lattice(
        cell,
    ):

        a = np.array(
            cell[0],
            dtype=float,
        )

        b = np.array(
            cell[1],
            dtype=float,
        )

        c = np.array(
            cell[2],
            dtype=float,
        )

        volume = np.dot(
            a,
            np.cross(
                b,
                c,
            ),
        )

        if abs(volume) < 1e-12:

            raise ValueError(
                "The real-space unit cell has zero volume. "
                "A Brillouin zone cannot be constructed."
            )

        factor = (
            2.0
            * math.pi
            / volume
        )

        b1 = factor * np.cross(
            b,
            c,
        )

        b2 = factor * np.cross(
            c,
            a,
        )

        b3 = factor * np.cross(
            a,
            b,
        )

        return np.array(
            [
                b1,
                b2,
                b3,
            ]
        )

    @staticmethod
    def _reciprocal_info(
        reciprocal,
    ):

        lines = []

        labels = [
            "b₁",
            "b₂",
            "b₃",
        ]

        for label, vector in zip(
            labels,
            reciprocal,
        ):

            magnitude = np.linalg.norm(
                vector
            )

            lines.append(
                f"{label} = "
                f"({vector[0]:.4f}, "
                f"{vector[1]:.4f}, "
                f"{vector[2]:.4f}) Å⁻¹    "
                f"|{label}| = {magnitude:.4f} Å⁻¹"
            )

        return "\n".join(
            lines
        )
