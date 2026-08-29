"""Structured functional/pseudo UI consuming Qt-free C9Y/C9Q services."""
from __future__ import annotations
from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import (QCheckBox,QComboBox,QDialog,QDialogButtonBox,QFileDialog,QFormLayout,QHBoxLayout,QHeaderView,QLabel,QMessageBox,QPushButton,QSpinBox,QTableWidget,QTableWidgetItem,QVBoxLayout)
from backend.dft.functionals import FUNCTIONALS, resolve
from backend.pseudopotentials import PseudoProvisioner, ProvisionError, import_local_pseudopotential
from backend.pseudopotentials.compatibility import compatibility, recommended_cutoffs


class _ProvisionThread(QThread):
    ready = Signal(object)
    failed = Signal(str)
    def __init__(self, provisioner, species, functional, soc, policy, parent=None):
        super().__init__(parent); self.provisioner=provisioner; self.species=species; self.functional=functional; self.soc=soc; self.policy=policy
    def run(self):
        try: self.ready.emit(self.provisioner.provision_set(self.species,self.functional,self.soc,self.policy))
        except ProvisionError as error: self.failed.emit(str(error))
        except Exception as error: self.failed.emit("Pseudopotential provisioning failed: "+str(error))


class FunctionalPseudoDialog(QDialog):
    def __init__(self, parameters, species, parent=None, provisioner=None):
        super().__init__(parent); self.setWindowTitle("Exchange–Correlation and Pseudopotentials")
        self._parameters=dict(parameters); self._species=tuple(species); self._records={}; self._applied_cutoffs={}; self._provisioner=provisioner or PseudoProvisioner(); self._thread=None
        layout=QVBoxLayout(self); layout.addWidget(QLabel("Exchange–Correlation")); form=QFormLayout()
        self.family=QComboBox(self); self.family.addItems(("LDA", "GGA", "Hybrid")); self.functional=QComboBox(self); form.addRow("Family",self.family); form.addRow("Functional",self.functional)
        self.exx=QSpinBox(self); self.exx.setRange(0,100); self.exx.setSuffix(" %")
        self.screening=QSpinBox(self); self.screening.setRange(0,10000); self.screening.setSingleStep(1); self.screening.setSuffix(" ×10⁻³ bohr⁻¹")
        self.auto_mesh=QCheckBox("Auto — same as electronic k mesh",self); self.mesh_boxes=[]; mesh=QHBoxLayout()
        for index in range(3):
            box=QSpinBox(self); box.setRange(1,10000); self.mesh_boxes.append(box); mesh.addWidget(box)
            if index<2: mesh.addWidget(QLabel("×",self))
        self.ace=QCheckBox("Enable ACE exact-exchange acceleration",self); self.divergence=QComboBox(self); self.divergence.addItems(("gygi-baldereschi", "none"))
        form.addRow("Exact exchange",self.exx); form.addRow("Screening",self.screening); form.addRow("EXX q mesh",mesh); form.addRow("",self.auto_mesh); form.addRow("",self.ace); form.addRow("EXX divergence treatment",self.divergence); layout.addLayout(form)
        layout.addWidget(QLabel("Pseudopotentials")); provider=QHBoxLayout(); provider.addWidget(QLabel("Mode",self)); self.mode=QComboBox(self); self.mode.addItem("Auto (Recommended)","auto"); self.mode.addItem("SSSP Efficiency","sssp_efficiency"); self.mode.addItem("SSSP Precision","sssp_precision"); self.mode.addItem("Manual","manual"); provider.addWidget(self.mode); provider.addWidget(QLabel("Library",self)); self.library=QComboBox(self); self.library.addItem("Managed cache / Local/User","local"); self.library.setEnabled(False); provider.addWidget(self.library,1); layout.addLayout(provider)
        self.provision_status=QLabel("Pseudopotentials awaiting resolution.",self); layout.addWidget(self.provision_status)
        self.table=QTableWidget(len(self._species),7,self); self.table.setHorizontalHeaderLabels(("Element","Pseudopotential","Provider","XC","Type","Relativity","Status")); header=self.table.horizontalHeader(); header.setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents); header.setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch); header.setSectionResizeMode(2,QHeaderView.ResizeMode.ResizeToContents); header.setSectionResizeMode(6,QHeaderView.ResizeMode.ResizeToContents); layout.addWidget(self.table,1)
        actions=QHBoxLayout(); choose=QPushButton("Import UPF…",self); choose.clicked.connect(self._choose_upf); actions.addWidget(choose); retry=QPushButton("Retry",self); retry.clicked.connect(self._auto_if_needed); actions.addWidget(retry); recommended=QPushButton("Use Recommended Cutoffs",self); recommended.clicked.connect(self._use_recommended_cutoffs); actions.addWidget(recommended); self.cutoffs=QLabel(self); actions.addWidget(self.cutoffs,1); layout.addLayout(actions)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel,self); buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
        self.family.currentTextChanged.connect(self._populate_functionals); self.functional.currentIndexChanged.connect(self._refresh); self.auto_mesh.toggled.connect(self._mesh_enabled); self.mode.currentIndexChanged.connect(self._auto_if_needed)
        selected=resolve(self._parameters.get("xc_functional",self._parameters.get("functional","pbe"))); self.family.setCurrentText(selected.family); self._populate_functionals(); self.functional.setCurrentText(selected.id)
        explicit=bool(self._parameters.get("pseudopotentials")); self.mode.setCurrentIndex(max(0,self.mode.findData(self._parameters.get("pseudopotential_mode","manual" if explicit else "auto"))))
        self._load_existing(); self._refresh(); self.resize(900,600)

    def showEvent(self,event):
        super().showEvent(event); QTimer.singleShot(0,self._auto_if_needed)

    def _populate_functionals(self):
        family=self.family.currentText(); current=self.functional.currentData() or self.functional.currentText().lower(); self.functional.blockSignals(True); self.functional.clear()
        for functional in FUNCTIONALS.values():
            if functional.family==family: self.functional.addItem(functional.display_name,functional.id)
        index=self.functional.findData(current); self.functional.setCurrentIndex(index if index>=0 else 0); self.functional.blockSignals(False); self._refresh()

    def _load_existing(self):
        for row,element in enumerate(self._species):
            self.table.setItem(row,0,QTableWidgetItem(element)); combo=QComboBox(self); entry=self._parameters.get("pseudopotentials",{}).get(element,{})
            filename=entry.get("filename","") if isinstance(entry,dict) else str(entry); combo.addItem(filename or "Automatic selection",None); self.table.setCellWidget(row,1,combo)
            for column in range(2,7): self.table.setItem(row,column,QTableWidgetItem("—"))

    def _mesh_enabled(self, auto):
        for box in self.mesh_boxes: box.setEnabled(not auto)

    def _refresh(self):
        functional=resolve(self.functional.currentData()); hybrid=functional.hybrid
        for widget in (self.exx,self.auto_mesh,self.ace,self.divergence): widget.setVisible(hybrid)
        for box in self.mesh_boxes: box.setVisible(hybrid)
        self.screening.setVisible(hybrid and functional.screening is not None); self.exx.setValue(round(100*(self._parameters.get("exx_fraction",functional.exx_fraction or 0)))); self.screening.setValue(round(1000*(self._parameters.get("screening_parameter",functional.screening or 0))))
        requested=self._parameters.get("exx_q_mesh"); mesh=requested or self._parameters.get("kpoints",[1,1,1]); self.auto_mesh.setChecked(not bool(requested))
        for box,value in zip(self.mesh_boxes,mesh): box.setValue(int(value))
        self.ace.setChecked(self._parameters.get("ace",True)); self.divergence.setCurrentText(str(self._parameters.get("exxdiv_treatment","gygi-baldereschi"))); self._mesh_enabled(self.auto_mesh.isChecked()); self._refresh_rows()
        if self.isVisible(): self._auto_if_needed()

    def _auto_if_needed(self,*_):
        if self.mode.currentData()=="manual" or self._thread is not None or not self.isVisible(): return
        self.provision_status.setText(f"Downloading/resolving pseudopotentials for {len(self._species)} species…")
        self._thread=_ProvisionThread(self._provisioner,self._species,self.functional.currentData(),bool(self._parameters.get("soc",False)),self.mode.currentData(),self); self._thread.ready.connect(self._provisioned); self._thread.failed.connect(self._provision_failed); self._thread.start()

    def _provisioned(self,results):
        if self._thread: self._thread.wait(); self._thread=None
        for result in results: self._records[result.record.element]=result.record
        self.provision_status.setText(f"✓ Pseudopotentials {len(self._records)} / {len(self._species)} ready")
        self._refresh_rows()

    def _provision_failed(self,message):
        if self._thread: self._thread.wait(); self._thread=None
        self.provision_status.setText("Download failed: "+message)

    def _refresh_rows(self):
        functional=resolve(self.functional.currentData())
        for row,element in enumerate(self._species):
            record=self._records.get(element)
            if record is None: continue
            combo=self.table.cellWidget(row,1)
            if combo.findText(record.filename)<0: combo.addItem(record.filename,record)
            combo.setCurrentText(record.filename)
            state=compatibility(functional.id,record,False); values=(record.library_id,record.xc_functional.upper(),record.pseudo_type.value,record.relativity.value.replace("_RELATIVISTIC","").replace("FULLY","FR").replace("SCALAR","SR"),"✓ Auto" if self.mode.currentData()!="manual" else state.reason)
            for column,value in enumerate(values,2): self.table.setItem(row,column,QTableWidgetItem(str(value)))

    def _choose_upf(self):
        row=self.table.currentRow()
        if row<0: QMessageBox.information(self,"Pseudopotential","Select an element row first."); return
        source,_=QFileDialog.getOpenFileName(self,"Import UPF","","UPF files (*.UPF *.upf);;All files (*)")
        if not source: return
        try: record=import_local_pseudopotential(source)
        except Exception as error: QMessageBox.warning(self,"Pseudopotential",str(error)); return
        element=self._species[row]
        if record.element!=element: QMessageBox.warning(self,"Pseudopotential",f"Selected UPF is for {record.element}, not {element}."); return
        self.mode.setCurrentIndex(self.mode.findData("manual")); self._records[element]=record; self.provision_status.setText("Manual pseudopotential selection."); self._refresh_rows()

    def _use_recommended_cutoffs(self):
        values=recommended_cutoffs(tuple(self._records.values())) if self._records else {"ecutwfc":None,"ecutrho":None,"complete":False}; self._applied_cutoffs={"ecutwfc":values["ecutwfc"],"ecutrho":values["ecutrho"]}; self.cutoffs.setText("Recommended minimum: %s / %s Ry"%(values["ecutwfc"] or "—",values["ecutrho"] or "—"))

    def values(self):
        functional=resolve(self.functional.currentData()); values={"xc_functional":functional.id,"pseudopotential_mode":self.mode.currentData()}
        if functional.hybrid:
            mesh=None if self.auto_mesh.isChecked() else [box.value() for box in self.mesh_boxes]; values.update({"exx_fraction":self.exx.value()/100.0,"ace":self.ace.isChecked(),"exxdiv_treatment":self.divergence.currentText()})
            if mesh is not None: values["exx_q_mesh"]=mesh
            if functional.screening is not None: values["screening_parameter"]=self.screening.value()/1000.0
            changed=values["exx_fraction"]!=functional.exx_fraction or (functional.screening is not None and values["screening_parameter"]!=functional.screening); values["hybrid_status"]=("custom_hse_like" if functional.id=="hse06" else "custom_b3lyp_like") if changed else "standard"
        pseudos=dict(self._parameters.get("pseudopotentials",{}))
        for element,record in self._records.items(): pseudos[element]={"filename":record.filename,"source":record.path,"sha256":record.sha256,"library_id":record.library_id,"library_version":record.library_version,"xc_functional":record.xc_functional,"pseudo_type":record.pseudo_type.value,"relativistic":record.relativity.value,"recommended_ecutwfc_ry":record.recommended_ecutwfc_ry,"recommended_ecutrho_ry":record.recommended_ecutrho_ry}
        if pseudos: values["pseudopotentials"]=pseudos
        values.update({key:value for key,value in self._applied_cutoffs.items() if value is not None}); return values
