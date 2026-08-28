from pathlib import Path
from PySide6.QtWidgets import QCheckBox, QComboBox, QFileDialog, QLabel, QMessageBox
from .base import ScientificPlotWidget, normalize_export_filename
from backend.analyze.transforms import energy_reference, pdos_channels
from backend.analyze.export import export_dos_pdos_csv

class DOSPlot(ScientificPlotWidget):
    """DOS and PDOS view. Energy alignment is display-only and never mutates Results."""
    def __init__(self,parent=None):
        super().__init__(parent); self._pdos_channels=None
        self.reference=QComboBox(self); self.reference.addItem("Absolute"); self.reference.currentIndexChanged.connect(self._redraw)
        self.integrated=QCheckBox("Show integrated DOS",self); self.integrated.setVisible(False); self.integrated.toggled.connect(self._redraw)
        self.spin_mode=QComboBox(self); self.spin_mode.addItems(["Mirrored", "Both positive"]); self.spin_mode.setVisible(False); self.spin_mode.currentIndexChanged.connect(self._redraw)
        self.toolbar.insertWidget(1,QLabel("Energy reference:",self)); self.toolbar.insertWidget(2,self.reference); self.toolbar.insertWidget(3,self.integrated); self.toolbar.insertWidget(4,self.spin_mode)
    def set_pdos_channels(self,channels): self._pdos_channels=list(channels)
    def set_result(self,result):
        self.reference.blockSignals(True); self.reference.clear(); self.reference.addItem("Absolute")
        if result.metadata.get("fermi_energy_eV") is not None or result.metadata.get("fermi_energy") is not None or result.scalars.get("fermi_energy") is not None: self.reference.addItem("Fermi = 0")
        self.reference.setCurrentText("Fermi = 0" if "Fermi = 0" in [self.reference.itemText(i) for i in range(self.reference.count())] else "Absolute"); self.reference.blockSignals(False)
        self.integrated.setVisible(result.result_type=="DOSResult" and "integrated_dos" in result.arrays)
        self.spin_mode.setVisible(result.metadata.get("spin_semantics")=="COLLINEAR_SPIN")
        super().set_result(result)
    def _redraw(self,*_):
        if self._result is not None: super().set_result(self._result)
    def _draw(self,result):
        reference=self.reference.currentText() or "Absolute"
        try: x=energy_reference(result,"Fermi = 0" if reference=="Fermi = 0" else "Absolute")
        except ValueError: x=energy_reference(result,"Absolute"); reference="Absolute"
        fg="#D9DCE3"; self.axes.set_xlabel("Energy − E_F (eV)" if reference=="Fermi = 0" else "Energy (eV)",color=fg); self.axes.set_ylabel("DOS (states/eV/cell)",color=fg)
        if result.result_type=="PDOSResult":
            channels=self._pdos_channels if self._pdos_channels is not None else pdos_channels(result)
            for component,values in channels:
                displayed=-__import__("numpy").asarray(values) if component.get("spin")=="DOWN" and self.spin_mode.currentText()=="Mirrored" else values
                line=self.axes.plot(x,displayed,linewidth=1.2,label=str(component.get("label") or component.get("orbital") or "PDOS"))[0]; line._qs_series_id="pdos:"+str(component.get("id") or component.get("label") or component.get("orbital") or len(self.appearance_state.series)); self.appearance_state.series.setdefault(line._qs_series_id,{})
            self.axes.set_title("Projected Density of States",color=fg)
            if len(channels)<=12:self.axes.legend(facecolor="#17191F",labelcolor=fg)
        else:
            if "dos_up" in result.arrays and "dos_down" in result.arrays:
                up=result.arrays["dos_up"]; down=result.arrays["dos_down"]; display_down=-__import__("numpy").asarray(down) if self.spin_mode.currentText()=="Mirrored" else down
                line=self.axes.plot(x,up,color="#55C7D9",linewidth=1.3,label="Spin up ↑")[0]; line._qs_series_id="dos:up"; self.appearance_state.series.setdefault(line._qs_series_id,{})
                line=self.axes.plot(x,display_down,color="#E8A85C",linewidth=1.3,label="Spin down ↓" + (" (mirrored)" if self.spin_mode.currentText()=="Mirrored" else ""))[0]; line._qs_series_id="dos:down"; self.appearance_state.series.setdefault(line._qs_series_id,{})
                self.axes.legend(facecolor="#17191F",labelcolor=fg)
            else:
                values=result.arrays.get("dos",result.arrays.get("total_dos"))
                if values is not None:line=self.axes.plot(x,values,color="#55C7D9",linewidth=1.3,label="DOS")[0]; line._qs_series_id="dos:total"; self.appearance_state.series.setdefault(line._qs_series_id,{})
            if self.integrated.isChecked() and "integrated_dos" in result.arrays:line=self.axes.plot(x,result.arrays["integrated_dos"],color="#E8A85C",linewidth=1.1,label="N(E)")[0]; line._qs_series_id="dos:integrated"; self.appearance_state.series.setdefault(line._qs_series_id,{}); self.axes.legend(facecolor="#17191F",labelcolor=fg)
            self.axes.set_title("Density of States",color=fg)
        fermi=result.metadata.get("fermi_energy_eV",result.metadata.get("fermi_energy"))
        if fermi is not None:ref=self.axes.axvline(0.0 if reference=="Fermi = 0" else float(fermi),color="#AAB2BF",linestyle="--",linewidth=.8,label="E_F"); ref._qs_reference_id="fermi"; self.appearance_state.reference_lines.setdefault("fermi",{})
    def export_data(self):
        if self._result is None:return
        path,_=QFileDialog.getSaveFileName(self,"Export DOS Data","dos_data.csv",filter="CSV (*.csv)")
        if path:
            try: export_dos_pdos_csv(self._result,Path(normalize_export_filename(path,".csv")),reference=self.reference.currentText(),channels=self._pdos_channels)
            except Exception as error: QMessageBox.warning(self,"Export Data",f"Could not export data: {error}")
