from .base import ScientificPlotWidget, normalize_export_filename
from PySide6.QtWidgets import (QPushButton,QDialog,QFormLayout,QComboBox,QDoubleSpinBox,QCheckBox,QDialogButtonBox,QColorDialog,QLineEdit,QLabel)
from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor
import numpy as np

class BandPlot(ScientificPlotWidget):
    """Scientific band plot with one controller for selection, zoom, and pan."""
    def __init__(self,parent=None):
        super().__init__(parent); self.edge_analysis=None; self.show_band_edges=False; self.energy_offset=0.; self.reference_label="Absolute"; self.plot_style="Default"; self.band_color="#111111"; self.line_width=1.; self.line_style="-"; self.opacity=1.; self.box=True; self.tick_direction="in"; self.separator_color="#777777"; self.separator_width=.55; self.separator_style="-"; self.separators=True; self.energy_grid=False; self.energy_grid_style="--"; self.energy_grid_color="#999999"; self.energy_grid_width=.6; self.energy_grid_alpha=.5; self.x_label=""; self.y_label="Energy (eV)"; self.x_auto=True; self.y_auto=True; self.x_min=None; self.x_max=None; self.y_min=None; self.y_max=None; self._mode="NONE"; self._selected_points=[]; self._measurement_points=[]; self._markers=[]; self._pan_last=None; self.font_family=self.appearance_state.font_family; self.axis_font_size=10.; self.tick_font_size=9.; self.title_font_size=11.; self._selection_artist=None; self._measurement_artist=None
        self._nav_draw_pending=False; self.measurement_card=QLabel("",self); self.measurement_card.setMaximumWidth(320); self.measurement_card.setWordWrap(True); self.measurement_card.setStyleSheet("background: rgba(255,255,255,220); color: #111; padding: 4px; border: 1px solid #888;"); self.axes_scale=QPushButton("Axes & Scale…",self); self.select_button=QPushButton("Select Point",self); self.measure_button=QPushButton("Measure ΔE",self); self.clear_measurement=QPushButton("Clear ΔE",self); self.marker_button=QPushButton("Add Marker",self); self.readout=QLabel("",self)
        self.select_button.setCheckable(True); self.measure_button.setCheckable(True); self.marker_button.setCheckable(True)
        self.axes_scale.clicked.connect(self._axes_dialog); self.select_button.clicked.connect(lambda:self._set_mode("SELECT_POINT")); self.measure_button.clicked.connect(lambda:self._set_mode("MEASURE_DELTA_E")); self.marker_button.clicked.connect(lambda:self._set_mode("ADD_MARKER")); self.clear_measurement.clicked.connect(self._clear_measurement)
        self._mpl_connections=[self.canvas.mpl_connect("button_press_event",self._on_press),self.canvas.mpl_connect("button_release_event",self._on_release),self.canvas.mpl_connect("motion_notify_event",self._on_motion),self.canvas.mpl_connect("scroll_event",self._on_scroll)]
    def configure_electronic_analysis(self,analysis,*,show_edges=False,energy_offset=0.,reference_label="Absolute",plot_style="Default",show_gap=False): self.edge_analysis=analysis; self.show_band_edges=bool(show_edges); self.energy_offset=float(energy_offset); self.reference_label=reference_label; self.plot_style=str(plot_style)
    def set_path_metadata(self,path):
        if not isinstance(path,(list,tuple)) or len(path)<2: return
        positions=[0]
        for point in path[:-1]: positions.append(positions[-1]+int(point.get("points",1)))
        self._path_metadata={"path_node_positions":positions,"path_labels":{i:point.get("label","") for i,point in zip(positions,path) if point.get("label")}}
    def _draw(self,result):
        x=np.asarray(result.arrays.get("path_coordinate",result.arrays.get("kpoint",[])),float); values=result.arrays.get("energies",result.arrays.get("energy"));
        if values is None:return
        y=np.asarray(values,float); y=y[:,None] if y.ndim==1 else y; display_y=y-self.energy_offset; publication=True; bg="white" if publication else "#111318"; fg="#111111" if publication else "#D9DCE3"; self.figure.set_facecolor(bg); self.axes.set_facecolor(bg)
        for j in range(display_y.shape[1]): line=self.axes.plot(x,display_y[:,j],color=self.band_color if publication else "#55C7D9",linewidth=self.line_width,linestyle=self.line_style,alpha=self.opacity,label="Band structure" if j==0 else "_nolegend_")[0]; line._qs_series_id="band:"+str(j); self.appearance_state.series.setdefault(line._qs_series_id,{})
        path_meta=getattr(self,"_path_metadata",{})
        labels=result.metadata.get("path_labels") or path_meta.get("path_labels") or {i:p.get("label","") for i,p in zip(result.metadata.get("path_node_positions",()),result.metadata.get("band_path",())) if p.get("label")}; positions=[]
        if isinstance(labels,dict): positions=sorted((int(i),v) for i,v in labels.items() if 0<=int(i)<len(x) and v not in (None,""))
        elif isinstance(labels,(list,tuple)): positions=[(i,v) for i,v in enumerate(labels) if i<len(x) and v not in (None,"")]
        if positions:
            self.axes.set_xticks([x[i] for i,_ in positions],[str(v) for _,v in positions])
            if self.separators:
                for i,_ in positions:
                    line=self.axes.axvline(x[i],color=self.separator_color,linewidth=self.separator_width,linestyle=self.separator_style); line._qs_reference_id="symmetry"; self.appearance_state.reference_lines.setdefault("symmetry",{})
        elif self.x_label=="": self.x_label="Path coordinate"
        if self.reference_label in {"Fermi = 0","VBM = 0"}: line=self.axes.axhline(0.,color="#555555",linewidth=.7,linestyle="--"); line._qs_reference_id="energy_reference"; self.appearance_state.reference_lines.setdefault("energy_reference",{})
        if self.show_band_edges and self.edge_analysis is not None and self.edge_analysis.status=="VALID":
            for e in self.edge_analysis.degenerate_vbm:self.axes.scatter([x[e.path_sample_index]],[e.energy-self.energy_offset],marker="v",s=38,color="#C44E52",zorder=5)
            for e in self.edge_analysis.degenerate_cbm:self.axes.scatter([x[e.path_sample_index]],[e.energy-self.energy_offset],marker="^",s=38,color="#4C72B0",zorder=5)
        self.axes.set_xlabel(self.x_label if not positions else "",color=fg,fontfamily=self.font_family,fontsize=self.axis_font_size); self.axes.set_ylabel(self.y_label,color=fg,fontfamily=self.font_family,fontsize=self.axis_font_size); self.axes.set_title("Band Structure" if True else "",color=fg,fontfamily=self.font_family,fontsize=self.title_font_size); self.axes.tick_params(direction=self.tick_direction,colors=fg,labelsize=self.tick_font_size); self.axes.grid(False)
        if self.energy_grid: self.axes.yaxis.grid(True,color=self.energy_grid_color,linestyle=self.energy_grid_style,linewidth=self.energy_grid_width,alpha=self.energy_grid_alpha)
        for spine in self.axes.spines.values(): spine.set_visible(self.box); spine.set_linewidth(.8)
        if not self.x_auto and self.x_min is not None and self.x_max is not None:self.axes.set_xlim(self.x_min,self.x_max)
        if not self.y_auto and self.y_min is not None and self.y_max is not None:self.axes.set_ylim(self.y_min,self.y_max)
        self._redraw_annotations(x,y)
    def _redraw_annotations(self,x,y):
        self._selection_artist=None
        points=self._measurement_points or self._selected_points
        for point in points:
            self.axes.scatter([point["x"]],[point["energy"]-self.energy_offset],s=68,facecolors="none",edgecolors="#D62728",linewidths=1.4,zorder=8)
        for marker in self._markers:
            self.axes.scatter([marker["x"]],[marker["energy"]-self.energy_offset],s=54,marker="+",color="#2C7FB8",zorder=8)
        if len(self._measurement_points)==2:
            a,b=self._measurement_points; self.axes.plot([a["x"],b["x"]],[a["energy"]-self.energy_offset,b["energy"]-self.energy_offset],color="#D62728",linewidth=.8,linestyle=":",zorder=7)
            self.axes.text((a["x"]+b["x"])/2, (a["energy"]+b["energy"])/2-self.energy_offset, "ΔE = %.5f eV" % abs(b["energy"]-a["energy"]), fontsize=9, color="#8B1E1E", bbox={"facecolor":"white","alpha":0.8,"edgecolor":"#D62728","pad":2}, zorder=9)
    def _nearest(self,event):
        if event.inaxes is not self.axes or event.x is None or event.y is None:return None
        x=np.asarray(self._result.arrays.get("path_coordinate",[]),float); y=np.asarray(self._result.arrays.get("energies",[]),float); y=y[:,None] if y.ndim==1 else y
        if not len(x) or not len(y):return None
        cursor=np.array([event.x,event.y]); best=None
        for i in range(len(x)):
            for j in range(y.shape[1]):
                q=self.axes.transData.transform((x[i],y[i,j]-self.energy_offset)); d=float(np.linalg.norm(q-cursor))
                candidate={"i":i,"j":j,"x":float(x[i]),"energy":float(y[i,j]),"distance":d,"kind":"EXACT_SAMPLE","t":0.}
                if best is None or d<best["distance"]: best=candidate
                if i+1<len(x):
                    a=self.axes.transData.transform((x[i],y[i,j]-self.energy_offset)); b=self.axes.transData.transform((x[i+1],y[i+1,j]-self.energy_offset)); v=b-a; denom=float(np.dot(v,v))
                    if denom>0:
                        t=float(np.clip(np.dot(cursor-a,v)/denom,0.,1.)); q=a+t*v; d=float(np.linalg.norm(q-cursor))
                        if d<best["distance"]: best={"i":i,"j":j,"x":float(x[i]+t*(x[i+1]-x[i])),"energy":float(y[i,j]+t*(y[i+1,j]-y[i,j])),"distance":d,"kind":"DISPLAY_INTERPOLATED","t":t}
        return best if best is not None and best["distance"]<=18. else None
    def _toggle_grid(self, checked):
        self.axes.xaxis.grid(False)
        if checked: self.axes.yaxis.grid(True,color=self.energy_grid_color,linestyle=self.energy_grid_style,linewidth=self.energy_grid_width,alpha=self.energy_grid_alpha)
        else: self.axes.yaxis.grid(False)
        self._schedule_nav_draw()
    def _on_press(self,event):
        if event.button==3 and event.inaxes is self.axes:self._pan_last=(event.x,event.y); return
        if event.button!=1:return
        point=self._nearest(event)
        if self._mode=="SELECT_POINT": self._selected_points=[point] if point else []; self._update_readout(point); self.set_result(self._result)
        elif self._mode=="MEASURE_DELTA_E":
            if point is None: self.readout.setText("No band curve near cursor."); return
            if len(self._selected_points)>=2:self._selected_points=[]; self._measurement_points=[]
            self._selected_points.append(point); self._update_readout(point)
            if len(self._selected_points)==1: self.readout.setText("Point A selected — select second band point.")
            else:
                self._measurement_points=list(self._selected_points); a,b=self._measurement_points; delta=b["energy"]-a["energy"]; self.readout.setText(f"ΔE = {delta:+.6g} eV   |ΔE| = {abs(delta):.6g} eV"); self._selected_points=[]
                self.measurement_card.setText("ΔE Measurement\nA Band %d: E1 = %.5f eV\nB Band %d: E2 = %.5f eV\nΔE = %+.5f eV  |ΔE| = %.5f eV" % (a["j"]+1, a["energy"]-self.energy_offset, b["j"]+1, b["energy"]-self.energy_offset, delta, abs(delta)))
            self.set_result(self._result)
        elif self._mode=="ADD_MARKER":
            if point is None:self.readout.setText("No band curve near cursor."); return
            self._markers.append(point); self._mode="NONE"; self.marker_button.setChecked(False); self.set_result(self._result)
    def _on_release(self,event):
        if event.button==3:self._pan_last=None
    def _on_motion(self,event):
        if self._pan_last and event.inaxes is self.axes and event.x is not None:
            x0,y0=self.axes.transData.inverted().transform(self._pan_last); x1,y1=self.axes.transData.inverted().transform((event.x,event.y)); xa,xb=self.axes.get_xlim(); ya,yb=self.axes.get_ylim(); self.axes.set_xlim(xa-(x1-x0),xb-(x1-x0)); self.axes.set_ylim(ya-(y1-y0),yb-(y1-y0)); self._pan_last=(event.x,event.y); self.canvas.draw_idle(); return
        if event.inaxes is self.axes and event.xdata is not None:self._hover(event)
    def _schedule_nav_draw(self):
        if self._nav_draw_pending: return
        self._nav_draw_pending=True
        QTimer.singleShot(0, self._finish_nav_draw)
    def _finish_nav_draw(self):
        self._nav_draw_pending=False
        self.canvas.draw_idle()
    def _on_scroll(self,event):
        if event.inaxes is not self.axes:return
        factor=0.8 if event.button=="up" else 1.25; x,y=event.xdata,event.ydata; xa,xb=self.axes.get_xlim(); ya,yb=self.axes.get_ylim(); self.axes.set_xlim(x+(xa-x)*factor,x+(xb-x)*factor); self.axes.set_ylim(y+(ya-y)*factor,y+(yb-y)*factor); self._schedule_nav_draw()
    def _energy(self,p): return float(p["energy"] if isinstance(p,dict) else np.asarray(self._result.arrays.get("energies",self._result.arrays.get("energy")))[p[0],p[1]])
    def _update_readout(self,p):
        if not p:self.readout.setText("No band point selected."); return
        self.readout.setText(f"Band {p['j']+1} · E = {p['energy']-self.energy_offset:.6g} eV · path = {p['x']:.6g} · {p['kind']}")
    def _hover(self,event):
        p=self._nearest(event)
        if p:self._update_readout(p)
    def _clear_measurement(self):
        self._selected_points=[]; self._measurement_points=[]; self.measurement_card.clear(); self.set_result(self._result)
    def _set_mode(self,mode):
        if mode=="MEASURE_DELTA_E": self.measurement_card.clear()
        if mode=="MEASURE_DELTA_E": self._selected_points=[]; self._measurement_points=[]
        self._mode=mode; self.select_button.setChecked(mode=="SELECT_POINT"); self.measure_button.setChecked(mode=="MEASURE_DELTA_E"); self.marker_button.setChecked(mode=="ADD_MARKER"); self.readout.setText("Select first band point." if mode=="MEASURE_DELTA_E" else mode.replace("_"," ").title())
    def reset_view(self):
        self.x_auto=True; self.y_auto=True; super().reset_view(); self.set_result(self._result)
    def export_data(self):
        if self._result is None:return
        from PySide6.QtWidgets import QFileDialog,QMessageBox
        import csv
        path,_=QFileDialog.getSaveFileName(self,"Export Band Data","bands.csv","CSV (*.csv)")
        if not path:return
        target=__import__("pathlib").Path(normalize_export_filename(path, ".csv"))
        x=np.asarray(self._result.arrays.get("path_coordinate",[]),float); y=np.asarray(self._result.arrays.get("energies",[]),float); y=y[:,None] if y.ndim==1 else y; k=np.asarray(self._result.arrays.get("kpoints",self._result.metadata.get("kpoints",[[None,None,None]]*len(x))),object); labels=self._result.metadata.get("path_labels",{})
        try:
            with target.open("w",newline="",encoding="utf-8") as stream:
                writer=csv.writer(stream); writer.writerow(["path_coordinate","k_x","k_y","k_z","node_label","band_index","energy_eV"])
                for i in range(len(x)):
                    kv=list(k[i]) if i<len(k) else ["","",""]; kv=(kv+["","",""])[:3]
                    for j in range(y.shape[1]): writer.writerow([x[i],*kv,labels.get(i,"") if isinstance(labels,dict) else "",j+1,y[i,j]])
        except Exception as error: QMessageBox.warning(self,"Export Data",f"Could not export data: {error}")

    def _appearance_dialog(self):
        d=QDialog(self); d.setWindowTitle("Band Plot Appearance"); f=QFormLayout(d); family=QComboBox(d); family.addItems(available_font_families()); family.setCurrentText(self.font_family if self.font_family in available_font_families() else family.currentText()); f.addRow("Font family",family); w=QDoubleSpinBox(d); w.setRange(.3,4); w.setValue(self.line_width); box=QCheckBox(d); box.setChecked(self.box); ticks=QComboBox(d); ticks.addItems(["In","Out","In/Out"]); ticks.setCurrentText({"in":"In","out":"Out","inout":"In/Out"}[self.tick_direction]); color=QPushButton(self.band_color,d); f.addRow("Line width",w); f.addRow("Box",box); f.addRow("Tick direction",ticks); f.addRow("Line colour",color); b=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel,d); f.addRow(b); color.clicked.connect(lambda: self._choose_color(color,d)); b.accepted.connect(lambda:(setattr(self,"font_family",family.currentText()),setattr(self.appearance_state,"font_family",family.currentText()),setattr(self,"line_width",w.value()),setattr(self,"box",box.isChecked()),setattr(self,"tick_direction",{"In":"in","Out":"out","In/Out":"inout"}[ticks.currentText()]),setattr(self,"band_color",color.text()),d.accept(),self.set_result(self._result))); b.rejected.connect(d.reject); d.exec()
    def _choose_color(self,b,d):
        c=QColorDialog.getColor(QColor(b.text()),d)
        if c.isValid():b.setText(c.name())
    def _axes_dialog(self):
        d=QDialog(self); d.setWindowTitle("Axes & Scale"); f=QFormLayout(d); xl=QLineEdit(self.x_label,d); yl=QLineEdit(self.y_label,d); ya=QCheckBox(d); ya.setChecked(self.y_auto); ymin=QDoubleSpinBox(d); ymax=QDoubleSpinBox(d); ymin.setRange(-1e6,1e6); ymax.setRange(-1e6,1e6); ymin.setValue(self.y_min if self.y_min is not None else -5); ymax.setValue(self.y_max if self.y_max is not None else 5); eg=QCheckBox(d); eg.setChecked(self.energy_grid); sep=QCheckBox(d); sep.setChecked(self.separators); f.addRow("X label",xl); f.addRow("Y label",yl); f.addRow("Auto Y range",ya); f.addRow("Y minimum",ymin); f.addRow("Y maximum",ymax); f.addRow("Energy grid",eg); f.addRow("K-point separators",sep); b=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel,d); f.addRow(b)
        def apply():
            if not ya.isChecked() and ymin.value()>=ymax.value(): return
            self.x_label=xl.text().replace("\n"," ")[:80]; self.y_label=yl.text().replace("\n"," ")[:80]; self.y_auto=ya.isChecked(); self.y_min=ymin.value(); self.y_max=ymax.value(); self.energy_grid=eg.isChecked(); self.separators=sep.isChecked(); d.accept(); self.set_result(self._result)
        b.accepted.connect(apply); b.rejected.connect(d.reject); d.exec()
