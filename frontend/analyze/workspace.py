from __future__ import annotations
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QComboBox,QListWidget,QListWidgetItem,QStackedWidget,QPlainTextEdit,QPushButton,QFileDialog,QSplitter,QTableWidget,QTableWidgetItem,QMessageBox
from frontend.services.result_service import ResultService
from backend.analyze.transforms import result_kind,tabular_data
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
        split=QSplitter(Qt.Orientation.Horizontal); self.navigation=QListWidget(self); self.navigation.setMaximumWidth(190); self.navigation.currentRowChanged.connect(self._view_changed); self.views=QStackedWidget(self); split.addWidget(self.navigation); split.addWidget(self.views); split.setStretchFactor(1,1); root.addWidget(split,1)
        self.overview=QPlainTextEdit(self); self.overview.setReadOnly(True); self.views.addWidget(self.overview); self.plot=ScientificPlotWidget(self); self.views.addWidget(self.plot); self.table=QTableWidget(self); self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers); self.views.addWidget(self.table); self.provenance=QPlainTextEdit(self); self.provenance.setReadOnly(True); self.views.addWidget(self.provenance)
        self.empty=QLabel("No results to analyze.\n\nRun and parse a calculation in Calculate first.",self); self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter); self.views.addWidget(self.empty); self.views.setCurrentWidget(self.empty); self._populate_calculations()
    def _populate_calculations(self):
        self.calculation.clear()
        for request in self.project.get_calculations(): self.calculation.addItem(request.name or request.calculation_id,request.id)
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
        self.navigation.clear(); self.navigation.addItems(["Overview",result_kind(self.current_result),"Data","Provenance"]); self.navigation.setCurrentRow(0); self._show_overview()
    def _view_changed(self,row):
        if self.current_result is None:return
        if row==0:self._show_overview()
        elif row==1:self._show_plot()
        elif row==2:self._show_table()
        elif row==3:self._show_provenance()
    def _show_overview(self):
        r=self.current_result; p=r.provenance; lines=[f"Result: {result_kind(r)}",f"Status: {r.status.value}",f"Request: {p.request_id}",f"Execution: {p.execution_id}",f"Engine: {p.engine_id}",f"Tool: {p.tool_id}","", "Summary: "+r.summary()]
        if r.scalars: lines.extend(f"{k}: {v.get('value',v)} {v.get('units','')}" for k,v in r.scalars.items())
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
        headers,rows=tabular_data(self.current_result); self.table.clear(); self.table.setColumnCount(len(headers)); self.table.setHorizontalHeaderLabels(headers); self.table.setRowCount(min(len(rows),5000))
        for i,row in enumerate(rows[:5000]):
            for j,value in enumerate(row): self.table.setItem(i,j,QTableWidgetItem(str(value)))
        self.views.setCurrentWidget(self.table)
    def _show_provenance(self):
        p=self.current_result.provenance; self.provenance.setPlainText("\n".join(f"{k}: {v}" for k,v in p.__dict__.items())); self.views.setCurrentWidget(self.provenance)
