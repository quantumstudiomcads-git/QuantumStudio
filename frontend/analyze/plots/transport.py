from pathlib import Path
import csv
import numpy as np
from .base import ScientificPlotWidget, normalize_export_filename
from backend.analyze.export import export_csv
from backend.analyze.export import export_csv

PROPERTIES={
    "Seebeck coefficient, S": ("seebeck", "Seebeck coefficient (V/K)"),
    "Electrical conductivity / relaxation time, σ/τ": ("electrical_conductivity_over_tau", "Electrical conductivity / relaxation time (S m⁻¹ s)"),
    "Electronic thermal conductivity / relaxation time, κe/τ": ("electronic_thermal_conductivity_over_tau", "Electronic thermal conductivity / relaxation time (W m⁻¹ K⁻¹ s)"),
    "Signed carrier concentration": ("carrier_concentration_cm3", "Signed carrier concentration (cm⁻³)"),
}

class TransportPlot(ScientificPlotWidget):
    def __init__(self,parent=None):
        super().__init__(parent); self.transport_property=next(iter(PROPERTIES)); self.transport_temperature=0; self.transport_component="xx"
    def _series(self):
        key,label=PROPERTIES[self.transport_property]; a=np.asarray(self._result.arrays[key],float)
        if key=="carrier_concentration_cm3": return a[self.transport_temperature], label
        component={"xx":(0,0),"xy":(0,1),"xz":(0,2),"yx":(1,0),"yy":(1,1),"yz":(1,2),"zx":(2,0),"zy":(2,1),"zz":(2,2)}[self.transport_component]
        return a[self.transport_temperature,:,component[0],component[1]], label
    def _draw(self,result):
        x=np.asarray(result.arrays["chemical_potential_eV"],float); y,label=self._series(); self.axes.plot(x,y,label=label,color="#0072B2",linewidth=1.3)[0]._qs_series_id="transport:value"; self.axes.set_xlabel("Chemical potential relative to QE Fermi reference (eV)"); self.axes.set_ylabel(label); self.axes.set_title("BoltzTraP2 transport"); self.axes.legend()
        if "carrier" in self.transport_property.lower(): self.axes.axhline(0,color="#666",linewidth=.8,linestyle="--")
    def set_transport_selection(self, property_name=None, temperature=None, component=None):
        if property_name is not None: self.transport_property=property_name
        if temperature is not None: self.transport_temperature=int(temperature)
        if component is not None: self.transport_component=component
        self.redraw()
    def export_data(self):
        if self._result is None:return
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        path,_=QFileDialog.getSaveFileName(self,"Export Transport Data","transport_data.csv","CSV (*.csv);;NumPy archive (*.npz)")
        if not path:return
        if Path(path).suffix.lower() == ".npz":
            self.export_transport_npz(path); return
        try:
            key,label=PROPERTIES[self.transport_property]; y,label=self._series(); x=np.asarray(self._result.arrays["chemical_potential_eV"]); carrier=np.asarray(self._result.arrays["carrier_concentration_cm3"])[self.transport_temperature]; unit=self._result.metadata["units"].get(key,"")
            with Path(normalize_export_filename(path,".csv")).open("w",newline="",encoding="utf-8") as stream:
                writer=csv.writer(stream); writer.writerow(["# backend=BoltzTraP2","# energy_reference=QE Fermi reference"]); writer.writerow(["temperature_K","chemical_potential_eV","tensor_component","value","unit","carrier_concentration_cm3"]); writer.writerows([[self._result.arrays["temperatures_K"][self.transport_temperature],x[i],self.transport_component,y[i],unit,carrier[i]] for i in range(len(x))])
        except Exception as error: QMessageBox.warning(self,"Export Transport Data",str(error))
    def export_transport_npz(self,path):
        np.savez_compressed(path,**{key:np.asarray(value) for key,value in self._result.arrays.items()})
class GammaPhononPlot(ScientificPlotWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.frequency_unit = "cm^-1"
    def _draw(self, result):
        import numpy as np
        key = "frequencies_cm1" if self.frequency_unit == "cm^-1" else "frequencies_THz"
        unit = "cm⁻¹" if self.frequency_unit == "cm^-1" else "THz"
        values = np.asarray(result.arrays[key], dtype=float)
        self.axes.axhline(0.0, color="#666666", linewidth=0.8, linestyle="--")
        self.axes.plot(np.arange(1, len(values) + 1), values, "o", label="Γ-point modes")
        self.axes.set_xlabel("Mode index")
        self.axes.set_ylabel(f"Frequency ({unit})")
        self.axes.set_title("Γ-point phonon frequencies")
        self.axes.legend()
    def set_frequency_unit(self, unit):
        self.frequency_unit = "THz" if str(unit).upper() == "THZ" else "cm^-1"
        self.redraw()
