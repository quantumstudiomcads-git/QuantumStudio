"""Small schema-keyed Qt controls that preserve JSON-compatible request values."""
from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QHBoxLayout, QLineEdit, QSpinBox, QWidget


MESH_KEYS = {"kpoints", "dense_kpoints", "qmesh", "mp_grid", "transport_k_mesh", "exx_q_mesh", "coarse_k_mesh", "coarse_q_mesh", "fine_k_mesh", "fine_q_mesh"}
ENUMS = {
    "occupations": ("fixed", "smearing", "tetrahedra", "tetrahedra_opt"),
    "smearing": ("gaussian", "mp", "mv", "fd"),
    "relaxation_time_model": ("constant", "unspecified"),
    "zasr": ("simple", "crystal", "one-dim", "zero-dim"),
}


def _mesh(value):
    if isinstance(value, dict): value=value.get("mesh")
    return list(value) if isinstance(value, (list, tuple)) and len(value)==3 else [1, 1, 1]


def make_control(key, value, parent=None):
    if key in MESH_KEYS:
        root=QWidget(parent); layout=QHBoxLayout(root); layout.setContentsMargins(0,0,0,0); layout.setSpacing(4); boxes=[]
        for index, item in enumerate(_mesh(value)):
            box=QSpinBox(root); box.setRange(1, 10000); box.setValue(int(item)); boxes.append(box); layout.addWidget(box)
            if index<2: layout.addWidget(__import__('PySide6.QtWidgets',fromlist=['QLabel']).QLabel("×",root))
        root._mesh_boxes=boxes
        return root
    if key in ENUMS:
        control=QComboBox(parent); control.addItems(ENUMS[key]); control.setCurrentText(str(value or ENUMS[key][0])); return control
    if key in {"spin", "soc", "lo_to_splitting", "spinors", "bands_plot", "ace"} or isinstance(value,bool):
        control=QCheckBox(parent); control.setChecked(bool(value)); return control
    if isinstance(value,int) and not isinstance(value,bool):
        control=QSpinBox(parent); control.setRange(0, 1000000); control.setValue(value); return control
    if isinstance(value,float):
        control=QDoubleSpinBox(parent); control.setDecimals(12); control.setRange(-1e12,1e12); control.setValue(value); return control
    control=QLineEdit(parent); control.setText("" if value is None else str(value)); return control


def control_value(key, control):
    if key in MESH_KEYS: return [box.value() for box in control._mesh_boxes]
    if isinstance(control,QComboBox): return control.currentText()
    if isinstance(control,QCheckBox): return control.isChecked()
    if isinstance(control,QSpinBox): return control.value()
    if isinstance(control,QDoubleSpinBox): return control.value()
    return control.text().strip()
