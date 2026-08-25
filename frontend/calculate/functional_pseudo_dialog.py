"""Small Calculate dialog over the C9X/C9Y functional and pseudo domain APIs."""
from __future__ import annotations
from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout
from backend.dft.functionals import FUNCTIONALS, resolve
from backend.pseudopotentials import CompatibilityState, compatibility, inspect_upf, recommended_cutoffs

class FunctionalPseudoDialog(QDialog):
    def __init__(self, parameters, species, parent=None):
        super().__init__(parent); self.setWindowTitle("Exchange–Correlation and Pseudopotentials"); self._parameters=dict(parameters); self._species=tuple(species); self._records={}; self._applied_cutoffs={}
        layout=QVBoxLayout(self); layout.addWidget(QLabel("Exchange–Correlation")); form=QFormLayout(); self.family=QComboBox(self); self.family.addItems(("LDA", "GGA", "Hybrid")); self.functional=QComboBox(self); form.addRow("Family", self.family); form.addRow("Functional", self.functional)
        self.exx=QLineEdit(self); self.screening=QLineEdit(self); self.exx_mesh=QLineEdit(self); self.ace=QComboBox(self); self.ace.addItems(("Enabled", "Disabled")); self.divergence=QLineEdit(self); form.addRow("Exact exchange", self.exx); form.addRow("Screening (bohr⁻¹)", self.screening); form.addRow("EXX q mesh", self.exx_mesh); form.addRow("ACE", self.ace); form.addRow("EXX divergence treatment", self.divergence); layout.addLayout(form)
        layout.addWidget(QLabel("Pseudopotentials — explicit per-element assignments")); self.table=QTableWidget(len(self._species), 6, self); self.table.setHorizontalHeaderLabels(("Element", "File", "XC", "Type", "Relativity", "Status")); layout.addWidget(self.table); actions=QHBoxLayout(); choose=QPushButton("Import UPF…", self); choose.clicked.connect(self._choose_upf); actions.addWidget(choose); recommended=QPushButton("Use Recommended Cutoffs", self); recommended.clicked.connect(self._use_recommended_cutoffs); actions.addWidget(recommended); self.cutoffs=QLabel(self); actions.addWidget(self.cutoffs); layout.addLayout(actions)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel, self); buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
        self.family.currentTextChanged.connect(self._populate_functionals); self.functional.currentIndexChanged.connect(self._refresh); selected=resolve(self._parameters.get("xc_functional", self._parameters.get("functional", "pbe"))); self.family.setCurrentText(selected.family); self._populate_functionals(); self.functional.setCurrentText(selected.id); self._load_existing(); self._refresh(); self.resize(760, 520)
    def _populate_functionals(self):
        family=self.family.currentText(); current=self.functional.currentData() or self.functional.currentText().lower(); self.functional.blockSignals(True); self.functional.clear()
        for functional in FUNCTIONALS.values():
            if functional.family == family: self.functional.addItem(functional.display_name, functional.id)
        index=self.functional.findData(current); self.functional.setCurrentIndex(index if index >= 0 else 0); self.functional.blockSignals(False); self._refresh()
    def _refresh(self):
        functional=resolve(self.functional.currentData()); hybrid=functional.hybrid; self.exx.setVisible(hybrid); self.exx_mesh.setVisible(hybrid); self.ace.setVisible(hybrid); self.divergence.setVisible(hybrid); self.screening.setVisible(hybrid and functional.screening is not None)
        self.exx.setText(str(self._parameters.get("exx_fraction", functional.exx_fraction or ""))); self.screening.setText(str(self._parameters.get("screening_parameter", functional.screening or ""))); self.exx_mesh.setText(" × ".join(map(str, self._parameters.get("exx_q_mesh", self._parameters.get("kpoints", ["Auto"]))))); self.ace.setCurrentIndex(0 if self._parameters.get("ace", True) else 1); self.divergence.setText(str(self._parameters.get("exxdiv_treatment", "gygi-baldereschi"))); self._refresh_rows()
    def _load_existing(self):
        for row, element in enumerate(self._species):
            entry=self._parameters.get("pseudopotentials", {}).get(element, {}); self.table.setItem(row, 0, QTableWidgetItem(element)); self.table.setItem(row, 1, QTableWidgetItem(entry.get("filename", "") if isinstance(entry, dict) else str(entry)))
            for column in range(2, 6): self.table.setItem(row, column, QTableWidgetItem("—"))
    def _refresh_rows(self):
        functional=resolve(self.functional.currentData())
        for row, element in enumerate(self._species):
            record=self._records.get(element)
            if record is None: continue
            state=compatibility(functional.id, record, False); values=(record.filename, record.xc_functional.upper(), record.pseudo_type.value, record.relativity.value.replace("_RELATIVISTIC", "").replace("FULLY", "FR").replace("SCALAR", "SR"), state.reason)
            for column, value in enumerate(values, 1): self.table.setItem(row, column, QTableWidgetItem(str(value)))
    def _choose_upf(self):
        row=self.table.currentRow();
        if row < 0: QMessageBox.information(self, "Pseudopotential", "Select an element row first."); return
        path,_=QFileDialog.getOpenFileName(self, "Import UPF", "", "UPF files (*.UPF *.upf);;All files (*)")
        if not path: return
        try: record=inspect_upf(path)
        except Exception as error: QMessageBox.warning(self, "Pseudopotential", str(error)); return
        element=self._species[row]
        if record.element != element: QMessageBox.warning(self, "Pseudopotential", f"Selected UPF is for {record.element}, not {element}."); return
        self._records[element]=record; self._refresh_rows()
    def _use_recommended_cutoffs(self):
        values=recommended_cutoffs(tuple(self._records.values())) if self._records else {"ecutwfc":None,"ecutrho":None,"complete":False}; self._applied_cutoffs={"ecutwfc":values["ecutwfc"],"ecutrho":values["ecutrho"]}; self.cutoffs.setText("Recommended: %s / %s Ry" % (values["ecutwfc"] or "—", values["ecutrho"] or "—"))
    def values(self):
        functional=resolve(self.functional.currentData()); values={"xc_functional":functional.id}
        if functional.hybrid:
            values.update({"exx_fraction":float(self.exx.text()), "ace":self.ace.currentIndex()==0, "exx_q_mesh":[int(value.strip()) for value in self.exx_mesh.text().replace("×", ",").split(",")], "exxdiv_treatment":self.divergence.text().strip()})
            if functional.screening is not None: values["screening_parameter"]=float(self.screening.text())
            if values["exx_fraction"] != functional.exx_fraction or (functional.screening is not None and values["screening_parameter"] != functional.screening): values["hybrid_status"]="custom_hse_like" if functional.id=="hse06" else "custom_b3lyp_like"
            else: values["hybrid_status"]="standard"
        pseudos=dict(self._parameters.get("pseudopotentials", {}))
        for element, record in self._records.items(): pseudos[element]={"filename":record.filename,"source":record.path,"sha256":record.sha256,"library_id":record.library_id,"library_version":record.library_version,"xc_functional":record.xc_functional,"pseudo_type":record.pseudo_type.value,"relativistic":record.relativity.value,"recommended_ecutwfc_ry":record.recommended_ecutwfc_ry,"recommended_ecutrho_ry":record.recommended_ecutrho_ry}
        if pseudos: values["pseudopotentials"]=pseudos
        values.update({key:value for key,value in self._applied_cutoffs.items() if value is not None})
        return values
