from __future__ import annotations
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QComboBox,QListWidget,QListWidgetItem,QStackedWidget,QPlainTextEdit,QPushButton,QFileDialog,QSplitter,QTableWidget,QTableWidgetItem,QTableView,QMessageBox,QDialog,QDialogButtonBox,QDoubleSpinBox,QSpinBox,QCheckBox,QInputDialog,QScrollArea,QSizePolicy
from frontend.services.result_service import ResultService
from backend.analyze.transforms import result_kind,tabular_data,pdos_channels
from backend.analyze.comparison import AnalysisSeries, ComparisonModel, provenance_differences, difference_eligible
from backend.analyze.export import export_comparison
from backend.analyze.transforms import energy_reference, exact_difference
from backend.analyze.electronic import analyze_band_edges, available_fit_directions, fit_effective_mass, strain_gap_trend, derived_comparison_rows
from frontend.analyze.plots.compare import ComparisonPlot
from frontend.analyze.plots.bands import BandPlot
from frontend.analyze.plots.dos import DOSPlot
from frontend.analyze.plots.base import ScientificPlotWidget
from frontend.analyze.table_model import ScientificTableModel, ScientificTableView

class AnalyzeWorkspace(QWidget):
    """Result-only browser; it never compiles, generates, executes, or parses."""
    def __init__(self, project, parent=None):
        super().__init__(parent); self.project=project; self.service=ResultService(); self.workflow_roots={}; self.current_result=None; self._electronic_cache={}; self._show_band_edges=False; self._electronic_reference="VBM = 0"; self._last_fit=None
        self.setObjectName("analyzeWorkspace"); self.setStyleSheet("AnalyzeWorkspace{background:#111318;color:#E8EAF0;} QComboBox,QPlainTextEdit,QTableWidget,QTableView,QScrollArea{background:#17191F;color:#E8EAF0;border:1px solid #30343D;} QListWidget,QHeaderView::section,QMenu{background:#17191F;color:#D9DCE3;border:1px solid #30343D;} QPushButton{background:#252932;color:#D9DCE3;padding:7px 11px;border-radius:6px;} QToolTip{background:#17191F;color:#E8EAF0;border:1px solid #3A4655;}")
        root=QVBoxLayout(self); header=QHBoxLayout(); title=QLabel("Analyze"); title.setStyleSheet("font-size:16px;font-weight:600;"); header.addWidget(title); header.addStretch(); self.refresh=QPushButton("Refresh Results",self); self.refresh.setToolTip("Refresh Result metadata without parsing scientific output"); self.refresh.clicked.connect(self._refresh_results); header.addWidget(self.refresh); self.attach=QPushButton("Open Results Folder…",self); self.attach.setToolTip("Advanced fallback for legacy or external Quantum Studio results"); self.attach.clicked.connect(self._attach_root); header.addWidget(self.attach); root.addLayout(header)
        selectors=QHBoxLayout(); self.calculation=QComboBox(self); self.execution=QComboBox(self); self.result=QComboBox(self); selectors.addWidget(QLabel("Calculation:")); selectors.addWidget(self.calculation,1); selectors.addWidget(QLabel("Execution:")); selectors.addWidget(self.execution,1); selectors.addWidget(QLabel("Result:")); selectors.addWidget(self.result,1); root.addLayout(selectors)
        for combo in (self.calculation, self.execution, self.result): combo.setMinimumWidth(0); combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.calculation.setToolTip("Configured calculation"); self.execution.setToolTip("Completed execution for this calculation"); self.result.setToolTip("Parsed scientific Result"); self.mode.setToolTip("Inspect one Result or compare compatible Results") if hasattr(self,"mode") else None; self.calculation.currentIndexChanged.connect(self._calculation_changed); self.execution.currentIndexChanged.connect(self._execution_changed); self.result.currentIndexChanged.connect(self._result_changed)
        self.pdos_controls=QWidget(self); pf=QHBoxLayout(self.pdos_controls); pf.setContentsMargins(0,0,0,0); self.pdos_species=QComboBox(self); self.pdos_atom=QComboBox(self); self.pdos_orbital=QComboBox(self); self.pdos_component=QComboBox(self); self.pdos_spin=QComboBox(self); self.pdos_aggregation=QComboBox(self); self.pdos_aggregation.addItems(["None","By species","By atom","By orbital","By spin"]);
        for label, box in (("Species",self.pdos_species),("Atom",self.pdos_atom),("Orbital",self.pdos_orbital),("Component",self.pdos_component),("Spin",self.pdos_spin),("Aggregation",self.pdos_aggregation)): pf.addWidget(QLabel(label+":")); pf.addWidget(box)
        self.pdos_controls.setVisible(False); root.addWidget(self.pdos_controls)
        for box in (self.pdos_species,self.pdos_atom,self.pdos_orbital,self.pdos_component,self.pdos_spin,self.pdos_aggregation): box.currentIndexChanged.connect(self._refresh_pdos_view)
        self.mode=QComboBox(self); self.mode.addItems(["Single Result","Compare Results"]); self.mode.setToolTip("Inspect one Result or compare compatible Results"); self.mode.currentIndexChanged.connect(self._mode_changed); root.insertWidget(1,self.mode)
        self.compare_panel=QWidget(self); cp=QVBoxLayout(self.compare_panel); self.series_list=QListWidget(self); self.series_list.itemChanged.connect(self._series_visibility_changed); cp.addWidget(self.series_list); cb=QHBoxLayout(); self.add_series=QPushButton("Add Result",self); self.remove_series=QPushButton("Remove",self); self.move_up=QPushButton("Move Up",self); self.move_down=QPushButton("Move Down",self); self.rename_series=QPushButton("Rename",self); self.compare_details=QPushButton("Comparison Details",self); self.derived_details=QPushButton("Electronic Analysis",self); self.derived_trend=QPushButton("Gap vs Strain",self); cb.addWidget(self.add_series); cb.addWidget(self.remove_series); cb.addWidget(self.move_up); cb.addWidget(self.move_down); cb.addWidget(self.rename_series); cb.addWidget(self.compare_details); cb.addWidget(self.derived_details); cb.addWidget(self.derived_trend); self.export_comparison_button=QPushButton("Export Comparison…",self); cb.addWidget(self.export_comparison_button); self.export_comparison_button.clicked.connect(self._export_comparison); self.derived_details.clicked.connect(self._show_compare_electronic); self.derived_trend.clicked.connect(self._show_strain_trend); cp.addLayout(cb); self.compare_panel.setVisible(False); root.insertWidget(2,self.compare_panel); self.add_series.clicked.connect(self._open_result_picker); self.remove_series.clicked.connect(self._remove_series); self.move_up.clicked.connect(lambda:self._move_series(-1)); self.move_down.clicked.connect(lambda:self._move_series(1)); self.rename_series.clicked.connect(self._rename_series); self.compare_details.clicked.connect(self._show_compare_details); self.series=[]
        self.view_mode=QComboBox(self); self.view_mode.addItem("Overlay"); self.view_mode.currentIndexChanged.connect(self._render_comparison); self.reference=QComboBox(self); self.reference.addItems(["Absolute","Fermi = 0","VBM = 0"]); self.reference.currentIndexChanged.connect(self._render_comparison); self.auto_range=QCheckBox("Auto range",self); self.auto_range.setChecked(True); self.min_energy=QDoubleSpinBox(self); self.max_energy=QDoubleSpinBox(self); self.min_energy.setRange(-1e4,1e4); self.max_energy.setRange(-1e4,1e4);
        controls=QHBoxLayout(); controls.addWidget(QLabel("View:")); controls.addWidget(self.view_mode); controls.addWidget(QLabel("Energy reference:")); controls.addWidget(self.reference); controls.addWidget(self.auto_range); controls.addWidget(QLabel("Min")); controls.addWidget(self.min_energy); controls.addWidget(QLabel("Max")); controls.addWidget(self.max_energy); self.compare_controls=QWidget(self); self.compare_controls.setLayout(controls); self.compare_controls.setVisible(False); root.insertWidget(3,self.compare_controls)
        split=QSplitter(Qt.Orientation.Horizontal); self.navigation=QListWidget(self); self.navigation.setMaximumWidth(190); self.navigation.currentRowChanged.connect(self._view_changed); self.views=QStackedWidget(self); split.addWidget(self.navigation); split.addWidget(self.views); split.setStretchFactor(1,1); root.addWidget(split,1)
        self.overview=QPlainTextEdit(self); self.overview.setReadOnly(True); self.views.addWidget(self.overview); self.plot=ScientificPlotWidget(self); self.views.addWidget(self.plot); self.table=ScientificTableView(self); self.table_model=ScientificTableModel(parent=self.table); self.table.setModel(self.table_model); self.table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers); self.table.setAlternatingRowColors(True); self.views.addWidget(self.table); self.provenance=QPlainTextEdit(self); self.provenance.setReadOnly(True); self.views.addWidget(self.provenance)
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
        model=ComparisonModel("Comparison", "", self.series).check(); self._comparison_model=model; self.compare_controls.setVisible(True)
        visible=model.visible_series(); requested=self.view_mode.currentText() if hasattr(self,"view_mode") else "Overlay"; self.view_mode.blockSignals(True); self.view_mode.clear(); self.view_mode.addItem("Overlay")
        eligible,reason=difference_eligible(model)
        if eligible:self.view_mode.addItem(f"Difference {visible[1].label} - {visible[0].label}")
        if requested.startswith("Difference") and eligible:self.view_mode.setCurrentIndex(1)
        self.view_mode.blockSignals(False)
        if model.compatibility=="INCOMPATIBLE":self.empty.setText("Comparison unavailable.\n"+"\n".join(model.warnings)); self.views.setCurrentWidget(self.empty); return
        if not hasattr(self,"comparison_plot"):self.comparison_plot=ComparisonPlot(self); self.views.addWidget(self.comparison_plot)
        if self.view_mode.currentIndex()==1 and eligible:
            try:
                import numpy as np
                a,b=visible; key="energies" if "energies" in a.scientific_result.arrays else "dos"; values=exact_difference(a.scientific_result,b.scientific_result,key=key); self.comparison_plot.axes.clear(); x=b.scientific_result.arrays.get("path_coordinate",b.scientific_result.arrays.get("energy")); self.comparison_plot.axes.plot(x,values,color="#E8A85C"); self.comparison_plot.axes.set_title(f"Difference {b.label} - {a.label}",color="#E8EAF0"); self.comparison_plot.axes.set_ylabel("Δ (eV)",color="#D9DCE3"); self.comparison_plot.canvas.draw_idle()
            except Exception as error:self.empty.setText("Difference unavailable.\n"+str(error)); self.views.setCurrentWidget(self.empty); return
        else:self.comparison_plot.set_comparison(model)
        self.views.setCurrentWidget(self.comparison_plot)
    def _export_comparison(self):
        model=getattr(self,"_comparison_model",None)
        if model is None:return
        directory=QFileDialog.getExistingDirectory(self,"Export Comparison Folder")
        if directory:
            try: export_comparison(model,directory,operation=self.view_mode.currentText(),reference=self.reference.currentText())
            except Exception as error: QMessageBox.warning(self,"Export Comparison",str(error))

    def _show_compare_electronic(self):
        model=getattr(self,"_comparison_model",None)
        if model is None or model.result_family!="bands":
            QMessageBox.information(self,"Electronic Analysis","Electronic comparison is available for Band Structure Results."); return
        dialog=QDialog(self); dialog.setWindowTitle("Derived Electronic Analysis"); layout=QVBoxLayout(dialog)
        visible=model.visible_series(); rows,delta,warning=derived_comparison_rows(visible)
        table=QTableWidget(dialog); table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers); table.setRowCount(6); table.setColumnCount(len(rows)+1)
        table.setHorizontalHeaderLabels(["Property"]+[row["label"] for row in rows]); names=["Source status","Scope","Gap","Type","VBM (eV)","CBM (eV)"]
        values=[("status",str), ("scope",str), ("gap",str), ("directness",str), ("vbm",lambda value:"—" if value is None else f"{value:.6g}"), ("cbm",lambda value:"—" if value is None else f"{value:.6g}")]
        for row_index,(name,formatter) in enumerate(values):
            table.setItem(row_index,0,QTableWidgetItem(names[row_index]))
            for col,row in enumerate(rows,1): table.setItem(row_index,col,QTableWidgetItem(formatter(row[name])))
        layout.addWidget(table)
        if delta is not None: layout.addWidget(QLabel(f"Δ sampled-path gap ({visible[1].label} - {visible[0].label}): {delta:+.6g} eV"))
        if warning: layout.addWidget(QLabel(warning))
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close,dialog); buttons.rejected.connect(dialog.reject); buttons.accepted.connect(dialog.accept); layout.addWidget(buttons); dialog.resize(700,340); dialog.exec()

    def _show_strain_trend(self):
        model=getattr(self,"_comparison_model",None)
        if model is None or model.result_family!="bands":
            QMessageBox.information(self,"Gap vs Strain","A derived gap trend is available for Band Structure comparisons."); return
        points,warnings=strain_gap_trend(model.visible_series())
        if len(points)<2:
            QMessageBox.information(self,"Gap vs Strain","At least two visible series with explicit numeric strain metadata and same-scope defensible gaps are required.\n"+"\n".join(warnings)); return
        dialog=QDialog(self); dialog.setWindowTitle("Sampled-path Gap vs Strain"); layout=QVBoxLayout(dialog)
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        figure=Figure(facecolor="#111318"); axes=figure.add_subplot(111); axes.set_facecolor("#111318")
        x=[point["strain_percent"] for point in points]; y=[point["gap_eV"] for point in points]
        axes.plot(x,y,color="#55C7D9",marker="o"); axes.set_xlabel("Strain (%)",color="#D9DCE3"); axes.set_ylabel("Sampled-path gap (eV)",color="#D9DCE3"); axes.set_title("Sampled-path Gap vs Strain",color="#E8EAF0"); axes.tick_params(colors="#D9DCE3"); [spine.set_color("#59606D") for spine in axes.spines.values()]
        layout.addWidget(FigureCanvasQTAgg(figure)); note=QLabel("\n".join(warnings)); note.setVisible(bool(warnings)); layout.addWidget(note)
        export=QPushButton("Export Trend CSV…",dialog)
        def write_trend():
            import csv
            filename,_=QFileDialog.getSaveFileName(dialog,"Export Gap Trend","gap_vs_strain.csv","CSV (*.csv)")
            if filename:
                with Path(filename).open("w",newline="",encoding="utf-8") as stream:
                    writer=csv.DictWriter(stream,fieldnames=["strain_percent","gap_eV","gap_scope","directness","request_id","execution_id","label"]); writer.writeheader(); writer.writerows(points)
        export.clicked.connect(write_trend); layout.addWidget(export); buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close,dialog); buttons.rejected.connect(dialog.reject); buttons.accepted.connect(dialog.accept); layout.addWidget(buttons); dialog.resize(680,460); dialog.exec()

    def _show_compare_details(self):
        model=getattr(self,"_comparison_model",None)
        if model is None:return
        lines=[f"Comparing {len(model.series)} {model.result_family} Results",f"Compatibility: {model.compatibility}"]
        for key,values in provenance_differences(model):lines.append(key+": "+" | ".join(values))
        QMessageBox.information(self,"Comparison Details","\n".join(lines))

    def _refresh_results(self):
        calculation_id=self.calculation.currentData(); execution_id=self.execution.currentData(); result_id=self.result.currentData()
        if hasattr(self.project, "execution_roots"):
            self.workflow_roots={str(key):str(value) for key,value in self.project.execution_roots().items()}
        self._populate_calculations()
        for combo,value in ((self.calculation,calculation_id),(self.execution,execution_id),(self.result,result_id)):
            index=combo.findData(value)
            if index >= 0: combo.setCurrentIndex(index)

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
        if not root:
            if self.calculation.count() == 0:
                self.empty.setText("No results to analyze.\n\nRun and parse a calculation in Calculate first.")
            else:
                self.empty.setText("Calculations are available, but no parsed scientific Results were found.\n\nParse Results in Calculate first.")
            self.views.setCurrentWidget(self.empty); return
        try:
            for execution_id in self.service.executions(root): self.execution.addItem(execution_id[-12:],execution_id)
        except Exception as error: self.empty.setText("Results unavailable.\n"+str(error)); self.views.setCurrentWidget(self.empty)
        self._execution_changed()
    def _execution_changed(self,*_):
        self.result.clear(); root=self.workflow_roots.get(str(self.calculation.currentData())); execution=self.execution.currentData()
        if not root or not execution: self.views.setCurrentWidget(self.empty); return
        try:
            if not self.service.summaries(root, execution):
                self.service.parse(root, execution)
            for row in self.service.summaries(root,execution): self.result.addItem(f"{result_kind(type('R',(),{'result_type':row['type']})())} — {row['status']}",row['result_id'])
        except Exception as error: self.empty.setText("Results unavailable.\n"+str(error)); self.views.setCurrentWidget(self.empty)
        if self.result.count() == 0:
            self.empty.setText("No parsed scientific Results are available for this execution.\n\nParse Results in Calculate first.")
            self.views.setCurrentWidget(self.empty)
            return
        self._result_changed()
    def _result_changed(self,*_):
        root=self.workflow_roots.get(str(self.calculation.currentData())); execution=self.execution.currentData(); rid=self.result.currentData()
        if not root or not execution or not rid: self.navigation.clear(); self.views.setCurrentWidget(self.empty); return
        try: self.current_result=self.service.load_result(root,execution,rid)
        except Exception as error: self.empty.setText("Result unavailable.\n"+str(error)); self.views.setCurrentWidget(self.empty); return
        self._populate_pdos_filters()
        self.navigation.clear(); items=["Overview",result_kind(self.current_result)]
        if self.current_result.result_type == "BandStructureResult": items.append("Electronic Analysis")
        items += ["Data","Provenance"]; self.navigation.addItems(items); self.navigation.setCurrentRow(0); self._show_overview()
    def _populate_pdos_filters(self):
        is_pdos=self.current_result is not None and self.current_result.result_type == "PDOSResult"
        self.pdos_controls.setVisible(is_pdos)
        if not is_pdos:return
        channels=self.current_result.metadata.get("components",())
        def fill(box, values): box.blockSignals(True); box.clear(); box.addItem("All"); [box.addItem(str(v)) for v in sorted({str(v) for v in values if v not in (None, "")})]; box.blockSignals(False)
        fill(self.pdos_species,[c.get("species",c.get("element")) for c in channels]); fill(self.pdos_atom,[c.get("atom",c.get("atom_index")) for c in channels]); fill(self.pdos_orbital,[c.get("orbital",c.get("label")) for c in channels]); fill(self.pdos_component,[c.get("component",c.get("m")) for c in channels]); fill(self.pdos_spin,[c.get("spin") for c in channels if c.get("spin") is not None])
    def _refresh_pdos_view(self,*_):
        if self.current_result is not None and self.current_result.result_type == "PDOSResult":
            if self.navigation.currentRow() == 1:self._show_plot()
            elif self.navigation.currentRow() == 2:self._show_table()

    def _view_changed(self,row):
        if self.current_result is None:return
        label=self.navigation.item(row).text() if row >= 0 else ""
        if label=="Overview":self._show_overview()
        elif label in {"Band Structure","Density of States","Projected DOS","Phonon DOS"}:self._show_plot()
        elif label=="Electronic Analysis":self._show_electronic()
        elif label=="Data":self._show_table()
        elif label=="Provenance":self._show_provenance()
    def _show_overview(self):
        r=self.current_result; p=r.provenance; lines=[f"Result: {result_kind(r)}",f"Status: {r.status.value}",f"Request: {p.request_id}",f"Execution: {p.execution_id}",f"Engine: {p.engine_id}",f"Tool: {p.tool_id}","", "Summary: "+r.summary()]
        if r.scalars: lines.extend(f"{k}: {v.get('value',v)} {v.get('units','')}" for k,v in r.scalars.items())
        method=r.metadata.get("electronic_method",{})
        if method: lines.append("Method: "+str(method.get("spin_treatment","SCALAR_NONSPIN")).replace("_"," ")+(" + U" if method.get("dft_plus_u") else ""))
        if r.metadata.get("final_structure"):
            structure=r.metadata["final_structure"]; lines.append(f"Final structure available (read-only), atoms: {len(structure.get('atoms',()))}")
        if r.warnings: lines.extend(["","Warnings:"]+r.warnings)
        self.overview.setPlainText("\n".join(lines)); self.views.setCurrentWidget(self.overview)
    def _electronic_analysis(self):
        if self.current_result is None:
            return None
        key=str(self.current_result.result_id)
        if key not in self._electronic_cache:
            self._electronic_cache[key]=analyze_band_edges(self.current_result)
        return self._electronic_cache[key]

    @staticmethod
    def _edge_text(edge):
        if edge is None:
            return "—"
        location=edge.label or ("k="+", ".join(f"{value:.3g}" for value in edge.kpoint) if edge.kpoint else f"sample {edge.path_sample_index}")
        return f"band {edge.band_index + 1} — {location}"

    def _reference_offset(self, analysis):
        if self._electronic_reference == "Fermi = 0":
            value=self.current_result.metadata.get("fermi_energy", self.current_result.scalars.get("fermi_energy",{}).get("value"))
            return float(value) if value is not None else 0.0
        if self._electronic_reference == "VBM = 0" and analysis is not None and analysis.status == "VALID" and analysis.vbm:
            return float(analysis.vbm.energy)
        return 0.0

    def _refresh_electronic_reference(self, *_):
        self._electronic_reference=self.electronic_reference.currentText()
        if self.current_result is not None:
            self._show_plot()

    def _show_electronic(self):
        analysis=self._electronic_analysis()
        if not hasattr(self,"electronic_view"):
            self.electronic_view=QScrollArea(self); self.electronic_view.setWidgetResizable(True)
            self.electronic_content=QWidget(self.electronic_view); self.electronic_layout=QVBoxLayout(self.electronic_content); self.electronic_view.setWidget(self.electronic_content); self.views.addWidget(self.electronic_view)
        while self.electronic_layout.count():
            item=self.electronic_layout.takeAt(0); widget=item.widget()
            if widget: widget.deleteLater()
        header=QLabel("Electronic Analysis"); header.setStyleSheet("font-size:15px;font-weight:600;"); self.electronic_layout.addWidget(header)
        source=QLabel(f"Source Result: {self.current_result.status.value}    Derived analysis: {analysis.status}"); self.electronic_layout.addWidget(source)
        scope="Fundamental band gap" if analysis.gap_scope == "full_bz" else "Sampled-path band gap"
        summary=QPlainTextEdit(self.electronic_content); summary.setReadOnly(True); summary.setMaximumHeight(178)
        state_names={"VALID":"Semiconductor", "METALLIC":"Metallic", "ZERO_GAP":"Zero-gap", "UNRESOLVED_OCCUPANCY":"Unavailable"}
        state=state_names.get(analysis.status, analysis.status.replace("_", " ").title())
        lines=[f"Electronic state: {state}", f"Gap scope: {'Full Brillouin zone' if analysis.gap_scope == 'full_bz' else 'Sampled path'}"]
        if analysis.gap is not None:
            kind=analysis.classification.replace("DIRECT_SAMPLED_PATH", "Direct on sampled path").replace("INDIRECT_SAMPLED_PATH", "Indirect on sampled path").replace("DIRECT_FULL_BZ", "Direct gap").replace("INDIRECT_FULL_BZ", "Indirect gap").replace("ZERO_GAP", "Zero-gap")
            lines += [f"{scope}: {analysis.gap:.6g} eV", f"Classification: {kind}", f"VBM: {analysis.vbm.energy:.6g} eV — {self._edge_text(analysis.vbm)}", f"CBM: {analysis.cbm.energy:.6g} eV — {self._edge_text(analysis.cbm)}"]
            if analysis.minimum_direct_gap is not None: lines.append(f"Minimum sampled direct gap: {analysis.minimum_direct_gap:.6g} eV")
        if analysis.warnings: lines += ["", "Warnings:"] + list(analysis.warnings)
        summary.setPlainText("\n".join(lines)); self.electronic_layout.addWidget(summary)
        edges=QCheckBox("Show band edges",self.electronic_content); edges.setChecked(self._show_band_edges); edges.setToolTip("Markers are derived only from retained A6 VBM/CBM candidates."); edges.toggled.connect(self._set_show_band_edges); self.electronic_layout.addWidget(edges)
        ref_row=QHBoxLayout(); self.electronic_reference=QComboBox(self.electronic_content); self.electronic_reference.addItem("Absolute")
        fermi=self.current_result.metadata.get("fermi_energy",self.current_result.scalars.get("fermi_energy",{}).get("value"))
        if fermi is not None:self.electronic_reference.addItem("Fermi = 0")
        if analysis.status == "VALID" and analysis.vbm is not None:self.electronic_reference.addItem("VBM = 0")
        self.electronic_reference.setCurrentText(self._electronic_reference if self.electronic_reference.findText(self._electronic_reference)>=0 else "Absolute")
        self.electronic_reference.currentIndexChanged.connect(self._refresh_electronic_reference); ref_row.addWidget(QLabel("Energy reference:")); ref_row.addWidget(self.electronic_reference); ref_row.addStretch(); self.electronic_layout.addLayout(ref_row)
        mass_box=QWidget(self.electronic_content); form=QFormLayout(mass_box); carrier=QComboBox(mass_box); carrier.addItems(["Electron (CBM)","Hole (VBM)"])
        extremum=QComboBox(mass_box); direction=QComboBox(mass_box); points=QSpinBox(mass_box); points.setRange(3,99); fit_button=QPushButton("Fit",mass_box); result_label=QLabel("Select an edge and sampled direction.",mass_box); preview=QPushButton("Show Fit",mass_box); preview.setEnabled(False)
        state={"edge":None,"directions":()}
        def invalidate_fit(*_):
            self._last_fit=None
            preview.setEnabled(False)
            result_label.setText("Fit settings changed — run Fit to update the effective mass.")
        def populate_edges(*_):
            carrier_name="CBM" if carrier.currentIndex()==0 else "VBM"; candidates=analysis.degenerate_cbm if carrier_name=="CBM" else analysis.degenerate_vbm
            extremum.blockSignals(True); extremum.clear()
            for edge in candidates: extremum.addItem(f"{carrier_name} — {self._edge_text(edge)}",edge)
            extremum.blockSignals(False); populate_directions()
        def populate_directions(*_):
            edge=extremum.currentData(); state["edge"]=edge; choices=available_fit_directions(self.current_result,edge) if edge is not None else ()
            state["directions"]=choices; direction.clear()
            for choice in choices: direction.addItem(choice.label,choice)
            maximum=max((len(choice.sample_indices) for choice in choices),default=3); points.setMaximum(max(3,maximum)); points.setValue(min(5,max(3,maximum)))
            enabled=edge is not None and bool(choices); fit_button.setEnabled(enabled)
            if not enabled: result_label.setText("Effective mass unavailable: no continuous sampled direction is available.")
        def perform_fit(*_):
            edge=extremum.currentData(); chosen=direction.currentData(); carrier_name="CBM" if carrier.currentIndex()==0 else "VBM"
            fit=fit_effective_mass(self.current_result,edge,carrier=carrier_name,direction=chosen,points_each_side=points.value()) if edge and chosen else None
            self._last_fit=fit
            if fit is None or fit.status!="VALID":
                result_label.setText("Effective mass unavailable: "+("; ".join(fit.warnings) if fit else "select an edge and direction.")); preview.setEnabled(False); return
            quality="Good fit" if fit.r_squared >= .995 else "Acceptable fit" if fit.r_squared >= .98 else "Poor parabolic fit — use with caution."
            title="Electron" if fit.edge=="CBM" else "Hole"
            result_label.setText(f"{title} effective mass: {fit.mass_me:.4g} m₀   R²={fit.r_squared:.4g}   {fit.sample_count} points   {fit.k_range[1]:.4g} Å⁻¹\n{fit.direction} — {quality}")
            preview.setEnabled(True)
        carrier.currentIndexChanged.connect(populate_edges); carrier.currentIndexChanged.connect(invalidate_fit); extremum.currentIndexChanged.connect(populate_directions); extremum.currentIndexChanged.connect(invalidate_fit); direction.currentIndexChanged.connect(invalidate_fit); points.valueChanged.connect(invalidate_fit); fit_button.clicked.connect(perform_fit); preview.clicked.connect(self._show_fit_preview); populate_edges()
        form.addRow(QLabel("Effective Mass")); form.addRow("Carrier:",carrier); form.addRow("Extremum:",extremum); form.addRow("Direction:",direction); form.addRow("Fit points:",points); form.addRow(fit_button); form.addRow(result_label); form.addRow(preview); self.electronic_layout.addWidget(mass_box)
        export=QPushButton("Export Electronic Analysis…",self.electronic_content); export.clicked.connect(self._export_electronic_analysis); self.electronic_layout.addWidget(export); self.electronic_layout.addStretch(); self.views.setCurrentWidget(self.electronic_view)

    def _set_show_band_edges(self, enabled):
        self._show_band_edges=bool(enabled)
        if self.current_result is not None:self._show_plot()

    def _show_fit_preview(self):
        fit=self._last_fit
        if fit is None or fit.status != "VALID": return
        dialog=QDialog(self); dialog.setWindowTitle("Effective-mass fit preview"); layout=QVBoxLayout(dialog)
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        figure=Figure(facecolor="#111318"); axes=figure.add_subplot(111); axes.set_facecolor("#111318")
        axes.scatter(fit.sample_distances,fit.sample_energies,color="#55C7D9",label="sampled band")
        axes.plot(fit.sample_distances,fit.fitted_energies,color="#E8A85C",label="quadratic fit")
        axes.set_xlabel("Δk (Å⁻¹)",color="#D9DCE3"); axes.set_ylabel("Energy (eV)",color="#D9DCE3"); axes.legend(facecolor="#17191F",labelcolor="#E8EAF0")
        axes.tick_params(colors="#D9DCE3"); [spine.set_color("#59606D") for spine in axes.spines.values()]
        canvas=FigureCanvasQTAgg(figure); layout.addWidget(canvas); buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close,dialog); buttons.rejected.connect(dialog.reject); buttons.accepted.connect(dialog.accept); layout.addWidget(buttons); dialog.resize(620,420); dialog.exec()

    def _export_electronic_analysis(self):
        import json
        analysis=self._electronic_analysis(); filename,_=QFileDialog.getSaveFileName(self,"Export Electronic Analysis","electronic_analysis.json","JSON (*.json)")
        if not filename:return
        def edge(value):
            return None if value is None else {"energy_eV":value.energy,"band_index":value.band_index,"path_sample_index":value.path_sample_index,"path_coordinate":value.path_coordinate,"kpoint":value.kpoint,"label":value.label}
        payload={"result_id":self.current_result.result_id,"request_id":self.current_result.provenance.request_id,"execution_id":self.current_result.provenance.execution_id,"source_status":self.current_result.status.value,"status":analysis.status,"gap_scope":analysis.gap_scope,"sampled_gap_eV":analysis.gap,"sampled_path_gap_eV":analysis.gap,"sampled_path_character":analysis.classification,"minimum_sampled_direct_gap_eV":analysis.minimum_direct_gap,"classification":analysis.classification,"vbm":[edge(item) for item in analysis.degenerate_vbm],"cbm":[edge(item) for item in analysis.degenerate_cbm],"fits":[fit.__dict__ for fit in (() if self._last_fit is None else (self._last_fit,))]}
        Path(filename).write_text(json.dumps(payload,indent=2,sort_keys=True),encoding="utf-8")

    def _show_plot(self):
        if self.current_result.result_type not in {"BandStructureResult","DOSResult","PDOSResult","PhononDOSResult"}:
            self.views.setCurrentWidget(self.overview); return
        if self.current_result.result_type == "PDOSResult":
            selected=pdos_channels(self.current_result, species=self.pdos_species.currentText(), atom=self.pdos_atom.currentText(), orbital=self.pdos_orbital.currentText(), component=self.pdos_component.currentText(), spin=self.pdos_spin.currentText(), aggregation=self.pdos_aggregation.currentText())
            if not selected:
                self.empty.setText("No PDOS channels match the current filter.")
                self.views.setCurrentWidget(self.empty); return
        old=self.plot
        self.views.removeWidget(old)
        old.figure.clear()
        old.deleteLater()
        self.plot = BandPlot(self) if self.current_result.result_type == "BandStructureResult" else DOSPlot(self)
        self.views.insertWidget(1,self.plot)
        if self.current_result.result_type == "BandStructureResult":
            analysis=self._electronic_analysis(); self.plot.configure_electronic_analysis(analysis,show_edges=self._show_band_edges,energy_offset=self._reference_offset(analysis),reference_label=self._electronic_reference)
            request=next((item for item in self.project.get_calculations() if str(item.id)==str(self.current_result.provenance.request_id)),None)
            if request is not None: self.plot.set_path_metadata(request.parameters.get("kpath"))
        if self.current_result.result_type == "PDOSResult": self.plot.set_pdos_channels(selected)
        self.plot.set_result(self.current_result); self.views.setCurrentWidget(self.plot)
    def _show_table(self):
        if self.current_result.result_type == "PDOSResult":
            channels=pdos_channels(self.current_result, species=self.pdos_species.currentText(), atom=self.pdos_atom.currentText(), orbital=self.pdos_orbital.currentText(), component=self.pdos_component.currentText(), spin=self.pdos_spin.currentText(), aggregation=self.pdos_aggregation.currentText())
            energy=list(self.current_result.arrays.get("energy",()))
            headers=["energy"]+[str(channel.get("label") or channel.get("orbital") or "channel") for channel,_ in channels]; rows=[[energy[i]]+[values[i] for _,values in channels if i<len(values)] for i in range(len(energy))]
        else: headers,rows=tabular_data(self.current_result)
        self.table_model.set_data(headers, rows)
        self.table.resizeColumnsToContents()
        self.views.setCurrentWidget(self.table)
    def _show_provenance(self):
        p=self.current_result.provenance; rows=[f"{k}: {v}" for k,v in p.__dict__.items()]
        method=self.current_result.metadata.get("electronic_method",{})
        if method: rows.append("electronic_method: "+str(method))
        self.provenance.setPlainText("\n".join(rows)); self.views.setCurrentWidget(self.provenance)
