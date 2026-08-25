"""Structured Calculate dialog over the C9X/C9Y functional and pseudo APIs."""
from __future__ import annotations
from PySide6.QtWidgets import (QCheckBox,QComboBox,QDialog,QDialogButtonBox,QFileDialog,QFormLayout,QHBoxLayout,QHeaderView,QLabel,QMessageBox,QPushButton,QSpinBox,QTableWidget,QTableWidgetItem,QVBoxLayout)
from backend.dft.functionals import FUNCTIONALS, resolve
from backend.pseudopotentials import compatibility, inspect_upf, recommended_cutoffs


class FunctionalPseudoDialog(QDialog):
    def __init__(self, parameters, species, parent=None):
        super().__init__(parent); self.setWindowTitle("Exchange–Correlation and Pseudopotentials")
        self._parameters=dict(parameters); self._species=tuple(species); self._records={}; self._applied_cutoffs={}
        layout=QVBoxLayout(self); layout.addWidget(QLabel("Exchange–Correlation")); form=QFormLayout()
        self.family=QComboBox(self); self.family.addItems(("LDA", "GGA", "Hybrid")); self.functional=QComboBox(self)
        form.addRow("Family",self.family); form.addRow("Functional",self.functional)
        self.exx=QSpinBox(self); self.exx.setRange(0,100); self.exx.setSuffix(" %")
        self.screening=QSpinBox(self); self.screening.setRange(0,10000); self.screening.setDecimals= None
        # screening uses an integer micro-unit control to avoid free-text scientific input.
        self.screening.setSingleStep(1); self.screening.setSuffix(" ×10⁻³ bohr⁻¹")
        self.auto_mesh=QCheckBox("Auto — same as electronic k mesh",self)
        self.mesh_boxes=[]; mesh=QHBoxLayout();
        for index in range(3):
            box=QSpinBox(self); box.setRange(1,10000); self.mesh_boxes.append(box); mesh.addWidget(box)
            if index<2: mesh.addWidget(QLabel("×",self))
        self.ace=QCheckBox("Enable ACE exact-exchange acceleration",self); self.divergence=QComboBox(self); self.divergence.addItems(("gygi-baldereschi", "none"))
        form.addRow("Exact exchange",self.exx); form.addRow("Screening",self.screening); form.addRow("EXX q mesh",mesh); form.addRow("",self.auto_mesh); form.addRow("",self.ace); form.addRow("EXX divergence treatment",self.divergence); layout.addLayout(form)
        layout.addWidget(QLabel("Pseudopotentials")); provider=QHBoxLayout(); provider.addWidget(QLabel("Library",self)); self.library=QComboBox(self); self.library.addItem("Local/User","local"); self.library.setToolTip("Only locally registered pseudopotential libraries are selectable."); provider.addWidget(self.library,1); layout.addLayout(provider)
        self.table=QTableWidget(len(self._species),6,self); self.table.setHorizontalHeaderLabels(("Element","Pseudopotential","XC","Type","Relativity","Status")); self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents); self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch); self.table.horizontalHeader().setSectionResizeMode(5,QHeaderView.ResizeMode.ResizeToContents); layout.addWidget(self.table,1)
        actions=QHBoxLayout(); choose=QPushButton("Import UPF…",self); choose.clicked.connect(self._choose_upf); actions.addWidget(choose); recommended=QPushButton("Use Recommended Cutoffs",self); recommended.clicked.connect(self._use_recommended_cutoffs); actions.addWidget(recommended); self.cutoffs=QLabel(self); actions.addWidget(self.cutoffs,1); layout.addLayout(actions)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel,self); buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
        self.family.currentTextChanged.connect(self._populate_functionals); self.functional.currentIndexChanged.connect(self._refresh); self.auto_mesh.toggled.connect(self._mesh_enabled)
        selected=resolve(self._parameters.get("xc_functional",self._parameters.get("functional","pbe"))); self.family.setCurrentText(selected.family); self._populate_functionals(); self.functional.setCurrentText(selected.id); self._load_existing(); self._refresh(); self.resize(840,580)

    def _populate_functionals(self):
        family=self.family.currentText(); current=self.functional.currentData() or self.functional.currentText().lower(); self.functional.blockSignals(True); self.functional.clear()
        for functional in FUNCTIONALS.values():
            if functional.family==family: self.functional.addItem(functional.display_name,functional.id)
        index=self.functional.findData(current); self.functional.setCurrentIndex(index if index>=0 else 0); self.functional.blockSignals(False); self._refresh()

    def _load_existing(self):
        for row,element in enumerate(self._species):
            self.table.setItem(row,0,QTableWidgetItem(element)); combo=QComboBox(self); entry=self._parameters.get("pseudopotentials",{}).get(element,{})
            filename=entry.get("filename","") if isinstance(entry,dict) else str(entry)
            combo.addItem(filename or "Choose a UPF…",None); self.table.setCellWidget(row,1,combo)
            for column in range(2,6): self.table.setItem(row,column,QTableWidgetItem("—"))

    def _mesh_enabled(self, auto):
        for box in self.mesh_boxes: box.setEnabled(not auto)

    def _refresh(self):
        functional=resolve(self.functional.currentData()); hybrid=functional.hybrid
        for widget in (self.exx,self.auto_mesh,self.ace,self.divergence): widget.setVisible(hybrid)
        for box in self.mesh_boxes: box.setVisible(hybrid)
        self.screening.setVisible(hybrid and functional.screening is not None)
        self.exx.setValue(round(100*(self._parameters.get("exx_fraction",functional.exx_fraction or 0))))
        self.screening.setValue(round(1000*(self._parameters.get("screening_parameter",functional.screening or 0))))
        requested=self._parameters.get("exx_q_mesh"); kmesh=self._parameters.get("kpoints",[1,1,1]); self.auto_mesh.setChecked(not bool(requested)); mesh=requested or kmesh
        for box,value in zip(self.mesh_boxes,mesh): box.setValue(int(value))
        self.ace.setChecked(self._parameters.get("ace",True)); self.divergence.setCurrentText(str(self._parameters.get("exxdiv_treatment","gygi-baldereschi"))); self._mesh_enabled(self.auto_mesh.isChecked()); self._refresh_rows()

    def _refresh_rows(self):
        functional=resolve(self.functional.currentData())
        for row,element in enumerate(self._species):
            record=self._records.get(element)
            if record is None: continue
            state=compatibility(functional.id,record,False); values=(record.xc_functional.upper(),record.pseudo_type.value,record.relativity.value.replace("_RELATIVISTIC","").replace("FULLY","FR").replace("SCALAR","SR"),state.reason)
            for column,value in enumerate(values,2): self.table.setItem(row,column,QTableWidgetItem(str(value)))

    def _choose_upf(self):
        row=self.table.currentRow()
        if row<0: QMessageBox.information(self,"Pseudopotential","Select an element row first."); return
        source,_=QFileDialog.getOpenFileName(self,"Import UPF","","UPF files (*.UPF *.upf);;All files (*)")
        if not source: return
        try: record=inspect_upf(source)
        except Exception as error: QMessageBox.warning(self,"Pseudopotential",str(error)); return
        element=self._species[row]
        if record.element!=element: QMessageBox.warning(self,"Pseudopotential",f"Selected UPF is for {record.element}, not {element}."); return
        self._records[element]=record; combo=self.table.cellWidget(row,1); combo.addItem(record.filename,record); combo.setCurrentIndex(combo.count()-1); self._refresh_rows()

    def _use_recommended_cutoffs(self):
        values=recommended_cutoffs(tuple(self._records.values())) if self._records else {"ecutwfc":None,"ecutrho":None,"complete":False}
        self._applied_cutoffs={"ecutwfc":values["ecutwfc"],"ecutrho":values["ecutrho"]}; self.cutoffs.setText("Recommended minimum: %s / %s Ry"%(values["ecutwfc"] or "—",values["ecutrho"] or "—"))

    def values(self):
        functional=resolve(self.functional.currentData()); values={"xc_functional":functional.id}
        if functional.hybrid:
            mesh=None if self.auto_mesh.isChecked() else [box.value() for box in self.mesh_boxes]
            values.update({"exx_fraction":self.exx.value()/100.0,"ace":self.ace.isChecked(),"exxdiv_treatment":self.divergence.currentText()})
            if mesh is not None: values["exx_q_mesh"]=mesh
            if functional.screening is not None: values["screening_parameter"]=self.screening.value()/1000.0
            changed=values["exx_fraction"]!=functional.exx_fraction or (functional.screening is not None and values["screening_parameter"]!=functional.screening)
            values["hybrid_status"]=("custom_hse_like" if functional.id=="hse06" else "custom_b3lyp_like") if changed else "standard"
        pseudos=dict(self._parameters.get("pseudopotentials",{}))
        for element,record in self._records.items():
            pseudos[element]={"filename":record.filename,"source":record.path,"sha256":record.sha256,"library_id":record.library_id,"library_version":record.library_version,"xc_functional":record.xc_functional,"pseudo_type":record.pseudo_type.value,"relativistic":record.relativity.value,"recommended_ecutwfc_ry":record.recommended_ecutwfc_ry,"recommended_ecutrho_ry":record.recommended_ecutrho_ry}
        if pseudos: values["pseudopotentials"]=pseudos
        values.update({key:value for key,value in self._applied_cutoffs.items() if value is not None}); return values
