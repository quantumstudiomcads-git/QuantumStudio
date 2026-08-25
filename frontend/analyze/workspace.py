from __future__ import annotations
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QComboBox,QListWidget,QListWidgetItem,QStackedWidget,QPlainTextEdit,QPushButton,QFileDialog,QSplitter,QTableWidget,QTableWidgetItem,QMessageBox,QDialog,QDialogButtonBox
from frontend.services.result_service import ResultService
from backend.analyze.transforms import result_kind,tabular_data,pdos_channels
from backend.analyze.comparison import AnalysisSeries, ComparisonModel, provenance_differences, difference_eligible
from frontend.analyze.plots.compare import ComparisonPlot
from frontend.analyze.plots.bands import BandPlot
from frontend.analyze.plots.dos import DOSPlot
from frontend.analyze.plots.base import ScientificPlotWidget

class AnalyzeWorkspace(QWidget):
    """Result-only browser; it never compiles, generates, executes, or parses."""
    def __init__(self, project, parent=None):
        super().__init__(parent); self.project=project; self.service=ResultService(); self.workflow_roots={}; self.current_result=None
        self.setObjectName("analyzeWorkspace"); self.setStyleSheet("AnalyzeWorkspace{background:#111318;color:#E8EAF0;} QComboBox,QPlainTextEdit,QTableWidget{background:#17191F;color:#E8EAF0;border:1px solid #30343D;} QListWidget{background:#17191F;color:#D9DCE3;border:1px solid #30343D;} QPushButton{background:#252932;color:#D9DCE3;padding:7px 11px;border-radius:6px;} QToolTip{background:#17191F;color:#E8EAF0;border:1px solid #3A4655;}")
        root=QVBoxLayout(self); header=QHBoxLayout(); title=QLabel("Analyze"); title.setStyleSheet("font-size:16px;font-weight:600;"); header.addWidget(title); header.addStretch(); self.attach=QPushButton("Open Results Folder…",self); self.attach.clicked.connect(self._attach_root); header.addWidget(self.attach); root.addLayout(header)
        selectors=QHBoxLayout(); self.calculation=QComboBox(self); self.execution=QComboBox(self); self.result=QComboBox(self); selectors.addWidget(QLabel("Calculation:")); selectors.addWidget(self.calculation,1); selectors.addWidget(QLabel("Execution:")); selectors.addWidget(self.execution,1); selectors.addWidget(QLabel("Result:")); selectors.addWidget(self.result,1); root.addLayout(selectors)
        self.calculation.currentIndexChanged.connect(self._calculation_changed); self.execution.currentIndexChanged.connect(self._execution_changed); self.result.currentIndexChanged.connect(self._result_changed)
        self.pdos_controls=QWidget(self); pf=QHBoxLayout(self.pdos_controls); pf.setContentsMargins(0,0,0,0); self.pdos_species=QComboBox(self); self.pdos_atom=QComboBox(self); self.pdos_orbital=QComboBox(self); self.pdos_component=QComboBox(self); self.pdos_aggregation=QComboBox(self); self.pdos_aggregation.addItems(["None","By species","By atom","By orbital"]);
        for label, box in (("Species",self.pdos_species),("Atom",self.pdos_atom),("Orbital",self.pdos_orbital),("Component",self.pdos_component),("Aggregation",self.pdos_aggregation)): pf.addWidget(QLabel(label+":")); pf.addWidget(box)
        self.pdos_controls.setVisible(False); root.addWidget(self.pdos_controls)
        for box in (self.pdos_species,self.pdos_atom,self.pdos_orbital,self.pdos_component,self.pdos_aggregation): box.currentIndexChanged.connect(self._refresh_pdos_view)
        self.mode=QComboBox(self); self.mode.addItems(["Single Result","Compare Results"]); self.mode.currentIndexChanged.connect(self._mode_changed); root.insertWidget(1,self.mode)
        self.compare_panel=QWidget(self); cp=QVBoxLayout(self.compare_panel); self.series_list=QListWidget(self); self.series_list.itemChanged.connect(self._series_visibility_changed); cp.addWidget(self.series_list); cb=QHBoxLayout(); self.add_series=QPushButton("Add Result",self); self.remove_series=QPushButton("Remove",self); self.move_up=QPushButton("Move Up",self); self.move_down=QPushButton("Move Down",self); self.rename_series=QPushButton("Rename",self); self.compare_details=QPushButton("Comparison Details",self); cb.addWidget(self.add_series); cb.addWidget(self.remove_series); cb.addWidget(self.move_up); cb.addWidget(self.move_down); cb.addWidget(self.rename_series); cb.addWidget(self.compare_details); cp.addLayout(cb); self.compare_panel.setVisible(False); root.insertWidget(2,self.compare_panel); self.add_series.clicked.connect(self._open_result_picker); self.remove_series.clicked.connect(self._remove_series); self.move_up.clicked.connect(lambda:self._move_series(-1)); self.move_down.clicked.connect(lambda:self._move_series(1)); self.rename_series.clicked.connect(self._rename_series); self.compare_details.clicked.connect(self._show_compare_details); self.series=[]
        split=QSplitter(Qt.Orientation.Horizontal); self.navigation=QListWidget(self); self.navigation.setMaximumWidth(190); self.navigation.currentRowChanged.connect(self._view_changed); self.views=QStackedWidget(self); split.addWidget(self.navigation); split.addWidget(self.views); split.setStretchFactor(1,1); root.addWidget(split,1)
        self.overview=QPlainTextEdit(self); self.overview.setReadOnly(True); self.views.addWidget(self.overview); self.plot=ScientificPlotWidget(self); self.views.addWidget(self.plot); self.table=QTableWidget(self); self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers); self.views.addWidget(self.table); self.provenance=QPlainTextEdit(self); self.provenance.setReadOnly(True); self.views.addWidget(self.provenance)
        self.empty=QLabel("No results to analyze.\n\nRun and parse a calculation in Calculate first.",self); self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter); self.views.addWidget(self.empty); self.views.setCurrentWidget(self.empty); self._populate_calculations()
    def _mode_changed(self,*_):
        comparing=self.mode.currentText()=="Compare Results"; self.compare_panel.setVisible(comparing)
        if comparing and not self.series and self.current_result is not None:self._add_current_series()
        if comparing:self._render_comparison()
    def _open_result_picker(self):
        dialog=QDialog(self); dialog.setWindowTitle("Add Result to Comparison"); form=QFormLayout(dialog); calc=QComboBox(dialog); exe=QComboBox(dialog); result=QComboBox(dialog); status=QLabel(dialog); candidates=[]
        for request in self.project.get_calculations():
            root=self.workflow_roots.get(str(request.id));
            if not root: continue
            for execution_id in self.service.executions(root):
                for row in self.service.summaries(root,execution_id):
                    if self.series and row["type"] != self.series[0].result_type: continue
                    candidates.append((request,root,execution_id,row))
        for request,root,eid,row in candidates: calc.addItem(request.name or request.calculation_id,(request,root,eid,row)); exe.addItem(eid[-12:],(request,root,eid,row)); result.addItem(row["type"],(request,root,eid,row))
        form.addRow("Calculation",calc); form.addRow("Execution",exe); form.addRow("Result",result); form.addRow("Status",status); buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel,dialog); form.addRow(buttons)
        def sync(index=0):
            item=result.currentData(); status.setText(item[3]["status"] if item else "No compatible results")
        result.currentIndexChanged.connect(sync); sync(); buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); dialog.resize(520,180)
        if dialog.exec()!=QDialog.DialogCode.Accepted or result.currentData() is None:return
        request,root,eid,row=result.currentData(); key=(request.id,eid,row["result_id"])
        if any((item.request_id,item.execution_id,item.series_id)==key for item in self.series): QMessageBox.information(self,"Comparison","This Result is already in the comparison."); return
        try: loaded=self.service.load_result(root,eid,row["result_id"])
        except Exception as error: QMessageBox.warning(self,"Add Result",str(error)); return
        series=AnalysisSeries.from_result(loaded,label=loaded.metadata.get("functional") or request.name or request.calculation_id); self.series.append(series); item=QListWidgetItem(series.label+" — "+series.status); item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable); item.setCheckState(Qt.CheckState.Checked); self.series_list.addItem(item); self._render_comparison()

    def _add_current_series(self):
        if self.current_result is None:return
        series=AnalysisSeries.from_result(self.current_result)
        if any(item.series_id==series.series_id for item in self.series):return
        self.series.append(series); item=QListWidgetItem(series.label+" — "+series.status); item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable); item.setCheckState(Qt.CheckState.Checked); self.series_list.addItem(item); self._render_comparison()
    def _series_visibility_changed(self,item):
        row=self.series_list.row(item)
        if 0 <= row < len(self.series): self.series[row].visible=item.checkState() == Qt.CheckState.Checked; self._render_comparison()
    def _move_series(self, delta):
        row=self.series_list.currentRow(); target=row+delta
        if row<0 or target<0 or target>=len(self.series): return
        self.series[row],self.series[target]=self.series[target],self.series[row]; item=self.series_list.takeItem(row); self.series_list.insertItem(target,item); self.series_list.setCurrentRow(target); self._render_comparison()
    def _rename_series(self):
        row=self.series_list.currentRow()
        if row<0:return
        from PySide6.QtWidgets import QInputDialog
        label,ok=QInputDialog.getText(self,"Rename Series","Label:",text=self.series[row].label)
        if ok and label.strip(): self.series[row].label=label.strip(); self.series_list.item(row).setText(label.strip()+" — "+self.series[row].status); self._render_comparison()

    def _remove_series(self):
        row=self.series_list.currentRow()
        if row>=0:self.series.pop(row); self.series_list.takeItem(row); self._render_comparison()
    def _render_comparison(self):
        if self.mode.currentText()!="Compare Results" or not self.series:return
        model=ComparisonModel("Comparison", "", self.series).check(); self._comparison_model=model
        if model.compatibility=="INCOMPATIBLE":self.empty.setText("Comparison unavailable.\n"+"\n".join(model.warnings)); self.views.setCurrentWidget(self.empty); return
        if not hasattr(self,"comparison_plot"):self.comparison_plot=ComparisonPlot(self); self.views.addWidget(self.comparison_plot)
        self.comparison_plot.set_comparison(model); self.views.setCurrentWidget(self.comparison_plot)
    def _show_compare_details(self):
        model=getattr(self,"_comparison_model",None)
        if model is None:return
        lines=[f"Comparing {len(model.series)} {model.result_family} Results",f"Compatibility: {model.compatibility}"]
        for key,values in provenance_differences(model):lines.append(key+": "+" | ".join(values))
        QMessageBox.information(self,"Comparison Details","\n".join(lines))

    def _populate_calculations(self):
        self.calculation.clear()
        for request in self.project.get_calculations():
            self.calculation.addItem(request.name or request.calculation_id, request.id)
        if hasattr(self.project, "execution_roots"):
            self.workflow_roots.update({str(k): str(v) for k, v in self.project.execution_roots().items()})
        self._calculation_changed()
    def set_workflow_root(self, request_id, root): self.workflow_roots[str(request_id)]=str(Path(root).resolve()); self._calculation_changed()
    def _attach_root(self):
        root=QFileDialog.getExistingDirectory(self,"Choose Results/Workflow Folder")
        if root and self.calculation.currentData() is not None: self.set_workflow_root(self.calculation.currentData(),root)
    def _calculation_changed(self,*_):
        self.execution.clear(); self.result.clear(); self.navigation.clear(); self.current_result=None; root=self.workflow_roots.get(str(self.calculation.currentData()))
        if not root: self.views.setCurrentWidget(self.empty); return
        try:
            for execution_id in self.service.executions(root): self.execution.addItem(execution_id[-12:],execution_id)
        except Exception as error: self.empty.setText("Results unavailable.\n"+str(error)); self.views.setCurrentWidget(self.empty)
        self._execution_changed()
    def _execution_changed(self,*_):
        self.result.clear(); root=self.workflow_roots.get(str(self.calculation.currentData())); execution=self.execution.currentData()
        if not root or not execution: self.views.setCurrentWidget(self.empty); return
        try:
            for row in self.service.summaries(root,execution): self.result.addItem(f"{result_kind(type('R',(),{'result_type':row['type']})())} — {row['status']}",row['result_id'])
        except Exception as error: self.empty.setText("Results unavailable.\n"+str(error)); self.views.setCurrentWidget(self.empty)
        self._result_changed()
    def _result_changed(self,*_):
        root=self.workflow_roots.get(str(self.calculation.currentData())); execution=self.execution.currentData(); rid=self.result.currentData()
        if not root or not execution or not rid: self.navigation.clear(); self.views.setCurrentWidget(self.empty); return
        try: self.current_result=self.service.load_result(root,execution,rid)
        except Exception as error: self.empty.setText("Result unavailable.\n"+str(error)); self.views.setCurrentWidget(self.empty); return
        self._populate_pdos_filters()
        self.navigation.clear(); self.navigation.addItems(["Overview",result_kind(self.current_result),"Data","Provenance"]); self.navigation.setCurrentRow(0); self._show_overview()
    def _populate_pdos_filters(self):
        is_pdos=self.current_result is not None and self.current_result.result_type == "PDOSResult"
        self.pdos_controls.setVisible(is_pdos)
        if not is_pdos:return
        channels=self.current_result.metadata.get("components",())
        def fill(box, values): box.blockSignals(True); box.clear(); box.addItem("All"); [box.addItem(str(v)) for v in sorted({str(v) for v in values if v not in (None, "")})]; box.blockSignals(False)
        fill(self.pdos_species,[c.get("species",c.get("element")) for c in channels]); fill(self.pdos_atom,[c.get("atom",c.get("atom_index")) for c in channels]); fill(self.pdos_orbital,[c.get("orbital",c.get("label")) for c in channels]); fill(self.pdos_component,[c.get("component",c.get("m")) for c in channels])
    def _refresh_pdos_view(self,*_):
        if self.current_result is not None and self.current_result.result_type == "PDOSResult":
            if self.navigation.currentRow() == 1:self._show_plot()
            elif self.navigation.currentRow() == 2:self._show_table()

    def _view_changed(self,row):
        if self.current_result is None:return
        if row==0:self._show_overview()
        elif row==1:self._show_plot()
        elif row==2:self._show_table()
        elif row==3:self._show_provenance()
    def _show_overview(self):
        r=self.current_result; p=r.provenance; lines=[f"Result: {result_kind(r)}",f"Status: {r.status.value}",f"Request: {p.request_id}",f"Execution: {p.execution_id}",f"Engine: {p.engine_id}",f"Tool: {p.tool_id}","", "Summary: "+r.summary()]
        if r.scalars: lines.extend(f"{k}: {v.get('value',v)} {v.get('units','')}" for k,v in r.scalars.items())
        if r.metadata.get("final_structure"):
            structure=r.metadata["final_structure"]; lines.append(f"Final structure available (read-only), atoms: {len(structure.get('atoms',()))}")
        if r.warnings: lines.extend(["","Warnings:"]+r.warnings)
        self.overview.setPlainText("\n".join(lines)); self.views.setCurrentWidget(self.overview)
    def _show_plot(self):
        if self.current_result.result_type not in {"BandStructureResult","DOSResult","PDOSResult","PhononDOSResult"}:
            self.views.setCurrentWidget(self.overview); return
        old=self.plot
        self.views.removeWidget(old); old.deleteLater()
        self.plot = BandPlot(self) if self.current_result.result_type == "BandStructureResult" else DOSPlot(self)
        self.views.insertWidget(1,self.plot); self.plot.set_result(self.current_result); self.views.setCurrentWidget(self.plot)
    def _show_table(self):
        if self.current_result.result_type == "PDOSResult":
            channels=pdos_channels(self.current_result, species=self.pdos_species.currentText(), atom=self.pdos_atom.currentText(), orbital=self.pdos_orbital.currentText(), component=self.pdos_component.currentText(), aggregation=self.pdos_aggregation.currentText())
            energy=list(self.current_result.arrays.get("energy",()))
            headers=["energy"]+[str(channel.get("label") or channel.get("orbital") or "channel") for channel,_ in channels]; rows=[[energy[i]]+[values[i] for _,values in channels if i<len(values)] for i in range(len(energy))]
        else: headers,rows=tabular_data(self.current_result)
        self.table.clear(); self.table.setColumnCount(len(headers)); self.table.setHorizontalHeaderLabels(headers); self.table.setRowCount(min(len(rows),5000))
        for i,row in enumerate(rows[:5000]):
            for j,value in enumerate(row): self.table.setItem(i,j,QTableWidgetItem(str(value)))
        self.views.setCurrentWidget(self.table)
    def _show_provenance(self):
        p=self.current_result.provenance; self.provenance.setPlainText("\n".join(f"{k}: {v}" for k,v in p.__dict__.items())); self.views.setCurrentWidget(self.provenance)
