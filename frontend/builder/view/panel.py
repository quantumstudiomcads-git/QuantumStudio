"""
Quantum Studio — Builder View Tab

Contains the UI for:
    - atom list
    - display controls
    - standard X/Y/Z views
    - Brillouin-zone access
    - atom size
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)


class BuilderViewMixin:

    def _build_view_tab(self):

        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 10, 0, 0)

        title = QLabel("ATOMS")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        self.atom_list = QListWidget()
        self.atom_list.itemClicked.connect(self._select_atom_from_list)
        layout.addWidget(self.atom_list)

        axes_title = QLabel("DETAILED DISPLAY")
        axes_title.setObjectName("sectionTitle")
        layout.addWidget(axes_title)

        self.axes = QCheckBox("Show orientation axes")
        self.axes.setChecked(True)
        self.axes.stateChanged.connect(self._toggle_axes)
        layout.addWidget(self.axes)

        self.species_group = QGroupBox("SPECIES VISIBILITY")
        self.species_layout = QVBoxLayout(self.species_group)
        layout.addWidget(self.species_group)

        selected = QLabel("SELECTED ATOM")
        selected.setObjectName("sectionTitle")
        layout.addWidget(selected)

        self.selected_info = QLabel("No atom selected")
        self.selected_info.setWordWrap(True)
        self.selected_info.setObjectName("infoLabel")
        layout.addWidget(self.selected_info)

        bz = QPushButton("Open Brillouin Zone")
        bz.setObjectName("operationButton")
        bz.clicked.connect(self._open_bz)
        layout.addWidget(bz)

        atom_size_label = QLabel("Atom Size")
        layout.addWidget(atom_size_label)
        self.atom_size = QSlider(Qt.Orientation.Horizontal)
        self.atom_size.setRange(50, 180)
        self.atom_size.setValue(100)
        self.atom_size.valueChanged.connect(self._change_atom_size)
        layout.addWidget(self.atom_size)

        layout.addStretch()
        self.info = QLabel()
        self.info.setObjectName("infoLabel")
        layout.addWidget(self.info)
        return tab
