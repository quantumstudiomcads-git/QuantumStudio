"""Small schema-keyed Qt controls that preserve JSON-compatible request values."""
from __future__ import annotations
import json

from PySide6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget


class HubbardTermsControl(QWidget):
    """Compact typed editor for QE 7.6 structured Hubbard terms."""
    def __init__(self, value, parent=None):
        super().__init__(parent)
        layout=QVBoxLayout(self); layout.setContentsMargins(0,0,0,0); layout.setSpacing(4)
        self.table=QTableWidget(0,3,self); self.table.setHorizontalHeaderLabels(("Species","Manifold","U (eV)")); self.table.verticalHeader().setVisible(False); self.table.setMaximumHeight(110); layout.addWidget(self.table)
        actions=QHBoxLayout(); self.add_button=QPushButton("Add term",self); self.remove_button=QPushButton("Remove selected",self); self.add_button.clicked.connect(lambda: self.add_term()); self.remove_button.clicked.connect(self.remove_selected); actions.addWidget(self.add_button); actions.addWidget(self.remove_button); actions.addStretch(); layout.addLayout(actions)
        for term in value if isinstance(value,list) else ():
            if isinstance(term,dict): self.add_term(term)
    def add_term(self, term=None):
        term=term or {"species":"","manifold":"3d","u_eV":0.0}; row=self.table.rowCount(); self.table.insertRow(row)
        self.table.setItem(row,0,QTableWidgetItem(str(term.get("species", ""))))
        self.table.setItem(row,1,QTableWidgetItem(str(term.get("manifold", "3d"))))
        self.table.setItem(row,2,QTableWidgetItem(str(term.get("u_eV", 0.0))))
    def remove_selected(self):
        for row in sorted({item.row() for item in self.table.selectedItems()},reverse=True): self.table.removeRow(row)
    def value(self):
        terms=[]
        for row in range(self.table.rowCount()):
            text=lambda column: self.table.item(row,column).text().strip() if self.table.item(row,column) is not None else ""
            species,manifold,u_eV=text(0),text(1),text(2)
            if not (species or manifold or u_eV): continue
            try: u=float(u_eV)
            except ValueError as error: raise ValueError("Each Hubbard U value must be numeric.") from error
            terms.append({"species":species,"manifold":manifold,"u_eV":u})
        return terms


class SpeciesMagnetizationControl(QWidget):
    """Typed QE starting-magnetization editor for collinear spin only."""
    def __init__(self, value=None, species=(), parent=None):
        super().__init__(parent)
        form=QFormLayout(self); form.setContentsMargins(0,0,0,0); form.setSpacing(4)
        supplied=value if isinstance(value,dict) else {}
        self.boxes={}
        for label in dict.fromkeys(str(item) for item in species if str(item)):
            box=QDoubleSpinBox(self); box.setRange(-1.0,1.0); box.setDecimals(3); box.setSingleStep(0.01); box.setValue(float(supplied.get(label,0.0) or 0.0)); form.addRow(label,box); self.boxes[label]=box
    def value(self):
        return {label:box.value() for label,box in self.boxes.items()}



class OptionalDoubleControl(QWidget):
    """Nullable typed floating-point value for optional scientific constraints."""
    def __init__(self, value=None, parent=None):
        super().__init__(parent)
        layout=QHBoxLayout(self); layout.setContentsMargins(0,0,0,0); layout.setSpacing(4)
        self.enabled=QCheckBox("Enabled",self); self.box=QDoubleSpinBox(self); self.box.setRange(-1e6,1e6); self.box.setDecimals(6); self.box.setSingleStep(0.1)
        self.enabled.setChecked(value is not None and value != "")
        if self.enabled.isChecked(): self.box.setValue(float(value))
        self.box.setEnabled(self.enabled.isChecked()); self.enabled.toggled.connect(self.box.setEnabled); layout.addWidget(self.enabled); layout.addWidget(self.box,1)
    def value(self): return self.box.value() if self.enabled.isChecked() else None


MESH_KEYS = {"kpoints", "dense_kpoints", "qmesh", "mp_grid", "transport_k_mesh", "exx_q_mesh", "coarse_k_mesh", "coarse_q_mesh", "fine_k_mesh", "fine_q_mesh", "dos_mesh"}
JSON_NUMERIC_KEYS = {"temperatures", "chemical_potentials", "carrier_concentrations", "chemical_potential_range", "carrier_concentration_range", "interpolation"}
ENUMS = {
    "occupations": ("fixed", "smearing", "tetrahedra", "tetrahedra_opt"),
    "smearing": ("gaussian", "mp", "mv", "fd"),
    "relaxation_time_model": ("constant", "unspecified"),
    "zasr": ("simple", "crystal", "one-dim", "zero-dim"),
    "spin_treatment": ("SCALAR_NONSPIN", "COLLINEAR_SPIN", "NONCOLLINEAR", "SOC"),
    "hubbard_projector": ("ortho-atomic", "atomic", "norm-atomic", "pseudo"),
}


def _mesh(value):
    if isinstance(value, dict): value=value.get("mesh")
    return list(value) if isinstance(value, (list, tuple)) and len(value)==3 else [1, 1, 1]


def make_control(key, value, parent=None, *, structure=None):
    if key == "hubbard_terms": return HubbardTermsControl(value, parent)
    if key == "tot_magnetization": return OptionalDoubleControl(value, parent)
    if key == "degauss":
        control=QDoubleSpinBox(parent); control.setRange(1e-9, 1e6); control.setDecimals(6); control.setSingleStep(0.01)
        try: numeric=float(value)
        except (TypeError, ValueError): numeric=0.01
        control.setValue(numeric if numeric > 0 else 0.01)
        return control
    if key == "starting_magnetization":
        species=[atom.get("element", "") for atom in (structure or {}).get("atoms", ()) if isinstance(atom, dict)]
        return SpeciesMagnetizationControl(value, species, parent)
    if key in MESH_KEYS:
        root=QWidget(parent); layout=QHBoxLayout(root); layout.setContentsMargins(0,0,0,0); layout.setSpacing(4); boxes=[]
        for index, item in enumerate(_mesh(value)):
            box=QSpinBox(root); box.setRange(1, 10000); box.setValue(int(item)); boxes.append(box); layout.addWidget(box)
            if index<2: layout.addWidget(__import__('PySide6.QtWidgets',fromlist=['QLabel']).QLabel("×",root))
        root._mesh_boxes=boxes
        return root
    if key in ENUMS:
        control=QComboBox(parent); control.addItems(ENUMS[key]); current=str(value or ENUMS[key][0]);
        if key == "relaxation_time_model" and current.startswith("UNSPECIFIED_"): current="unspecified"
        elif key == "relaxation_time_model" and current.startswith("CONSTANT_"): current="constant"
        control.setCurrentText(current); return control
    if key in {"spin", "soc", "lo_to_splitting", "spinors", "bands_plot", "ace"} or isinstance(value,bool):
        control=QCheckBox(parent); control.setChecked(bool(value)); return control
    if isinstance(value,int) and not isinstance(value,bool):
        control=QSpinBox(parent); control.setRange(0, 1000000); control.setValue(value); return control
    if isinstance(value,float):
        control=QDoubleSpinBox(parent); control.setDecimals(12); control.setRange(-1e12,1e12); control.setValue(value); return control
    control=QLineEdit(parent); control.setText("" if value is None else str(value)); return control


def control_value(key, control):
    if key == "hubbard_terms": return control.value()
    if key == "starting_magnetization": return control.value()
    if key == "tot_magnetization": return control.value()
    if key in MESH_KEYS: return [box.value() for box in control._mesh_boxes]
    if isinstance(control,QComboBox):
        value=control.currentText()
        if key == "relaxation_time_model": return "UNSPECIFIED_RELAXATION_TIME" if value == "unspecified" else "CONSTANT_RELAXATION_TIME"
        return value
    if isinstance(control,QCheckBox): return control.isChecked()
    if isinstance(control,QSpinBox): return control.value()
    if isinstance(control,QDoubleSpinBox): return control.value()
    text=control.text().strip()
    if key in JSON_NUMERIC_KEYS:
        if not text: return None
        try: return json.loads(text)
        except json.JSONDecodeError: return text
    return text
