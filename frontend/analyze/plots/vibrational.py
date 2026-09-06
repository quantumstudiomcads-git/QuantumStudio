from pathlib import Path
import csv, json
import numpy as np
from .base import ScientificPlotWidget, normalize_export_filename
from PySide6.QtWidgets import QWidget, QFileDialog, QMessageBox, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QGridLayout, QLabel
from backend.analyze.export import export_csv

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

class PhononDispersionPlot(ScientificPlotWidget):
    def __init__(self, parent=None):
        super().__init__(parent); self.frequency_unit = "cm^-1"
    def _draw(self, result):
        key = "frequencies_cm1" if self.frequency_unit == "cm^-1" else "frequencies_THz"
        values = np.asarray(result.arrays[key], dtype=float)
        x = np.asarray(result.arrays.get("q_distance", np.arange(len(values))), dtype=float)
        units = result.metadata.get("units", {})
        indices = units.get("high_symmetry_indices", result.metadata.get("high_symmetry_indices", ()))
        labels = units.get("high_symmetry_labels", result.metadata.get("high_symmetry_labels", ()))
        tick_indices = [int(index) for index in indices if 0 <= int(index) < len(x)]
        for index in tick_indices:
            self.axes.axvline(x[index], color="#777777", linewidth=0.6, linestyle="--", zorder=0)
        if tick_indices:
            self.axes.set_xticks([x[index] for index in tick_indices], [str(label) for label in labels[:len(tick_indices)]])
        for branch in range(values.shape[1]): self.axes.plot(x, values[:, branch], linewidth=1.0)
        self.axes.axhline(0.0, color="#666666", linewidth=0.8, linestyle="--")
        self.axes.set_xlabel("q-path distance"); self.axes.set_ylabel(f"Frequency ({'cm⁻¹' if self.frequency_unit == 'cm^-1' else 'THz'})"); self.axes.set_title("Phonon dispersion")
    def set_frequency_unit(self, unit): self.frequency_unit = "THz" if str(unit).upper() == "THZ" else "cm^-1"; self.redraw()
    def export_data(self):
        if self._result is None: return
        path, _ = QFileDialog.getSaveFileName(self, "Export Phonon Dispersion", "phonon_dispersion.csv", "CSV (*.csv);;NumPy archive (*.npz)")
        if not path: return
        target = Path(path); arrays = self._result.arrays
        try:
            if target.suffix.lower() == ".npz":
                target = Path(normalize_export_filename(str(target), ".npz")); np.savez(target, q_points_fractional=np.asarray(arrays["q_points_fractional"]), q_distance=np.asarray(arrays["q_distance"]), frequencies_cm1=np.asarray(arrays["frequencies_cm1"]), frequencies_THz=np.asarray(arrays["frequencies_THz"]))
                target.with_suffix(".json").write_text(json.dumps({"result_type": self._result.result_type, "metadata": self._result.metadata}, indent=2, default=str), encoding="utf-8")
            else:
                target = Path(normalize_export_filename(str(target), ".csv")); q=np.asarray(arrays["q_points_fractional"]); d=np.asarray(arrays["q_distance"]); cm=np.asarray(arrays["frequencies_cm1"]); thz=np.asarray(arrays["frequencies_THz"]); labels=dict(zip(self._result.metadata.get("units", {}).get("high_symmetry_indices", self._result.metadata.get("high_symmetry_indices", ())), self._result.metadata.get("units", {}).get("high_symmetry_labels", self._result.metadata.get("high_symmetry_labels", ()))))
                with target.open("w", newline="", encoding="utf-8") as stream:
                    writer=csv.writer(stream); writer.writerow(["q_index", "qx_fractional", "qy_fractional", "qz_fractional", "q_distance_Ainv", "branch", "frequency_cm1", "frequency_THz", "high_symmetry_label"])
                    for index in range(len(d)):
                        for branch in range(cm.shape[1]): writer.writerow([index, *q[index], d[index], branch + 1, cm[index, branch], thz[index, branch], labels.get(index, "")])
        except Exception as error: QMessageBox.warning(self, "Export Phonon Dispersion", f"Could not export data: {error}")



class PhononDOSPlot(ScientificPlotWidget):
    def __init__(self, parent=None):
        super().__init__(parent); self.frequency_unit = "cm^-1"
    def _draw(self, result):
        key = "frequency_cm1" if self.frequency_unit == "cm^-1" else "frequency_THz"
        frequency = np.asarray(result.arrays[key], float)
        dos = np.asarray(result.arrays["dos"], float)
        if self.frequency_unit == "THz":
            dos = dos * 33.3564095
        self.axes.plot(frequency, dos, linewidth=1.2, label="Phonon DOS")
        self.axes.set_xlabel(f"Frequency ({'cm⁻¹' if self.frequency_unit == 'cm^-1' else 'THz'})"); self.axes.set_ylabel("Phonon DOS"); self.axes.set_title("Phonon density of states"); self.axes.legend()
    def set_frequency_unit(self, unit): self.frequency_unit = "THz" if str(unit).upper() == "THZ" else "cm^-1"; self.redraw()
    def export_data(self):
        if self._result is None: return
        path, _ = QFileDialog.getSaveFileName(self, "Export Phonon DOS", "phonon_dos.csv", "CSV (*.csv);;NumPy archive (*.npz)")
        if not path: return
        target = Path(path); arrays = self._result.arrays
        try:
            if target.suffix.lower() == ".npz":
                target = Path(normalize_export_filename(str(target), ".npz")); np.savez(target, frequency_cm1=np.asarray(arrays["frequency_cm1"]), frequency_THz=np.asarray(arrays["frequency_THz"]), dos=np.asarray(arrays["dos"]))
                target.with_suffix(".json").write_text(json.dumps({"result_type": self._result.result_type, "metadata": self._result.metadata}, indent=2, default=str), encoding="utf-8")
            else:
                target = Path(normalize_export_filename(str(target), ".csv"))
                with target.open("w", newline="", encoding="utf-8") as stream:
                    writer=csv.writer(stream); writer.writerow(["frequency_cm1", "frequency_THz", "dos"])
                    for cm, thz, dos in zip(np.asarray(arrays["frequency_cm1"]), np.asarray(arrays["frequency_THz"]), np.asarray(arrays["dos"])): writer.writerow([cm, thz, dos])
        except Exception as error: QMessageBox.warning(self, "Export Phonon DOS", f"Could not export data: {error}")


class PolarTensorPlot(ScientificPlotWidget):
    """Compact matrix view for polar-response tensors; values remain raw."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.atom_index = 0
        self.tensor_table = QTableWidget(3, 3, self)
        self.tensor_table.setObjectName("polarTensorTable")
        self.tensor_table.setHorizontalHeaderLabels(["Displacement x", "Displacement y", "Displacement z"])
        self.tensor_table.setVerticalHeaderLabels(["Polarization x", "Polarization y", "Polarization z"])
        self.tensor_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tensor_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.tensor_table.setMinimumHeight(132)
        self.tensor_table.setMaximumHeight(180)
        self.tensor_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tensor_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.layout().insertWidget(1, self.tensor_table, 0)
    def set_atom_index(self, index):
        self.atom_index = max(0, int(index))
        self.redraw()
    def set_result(self, result):
        super().set_result(result)
        self._update_tensor_table(result)
    def _update_tensor_table(self, result):
        values = np.asarray(result.arrays["born_effective_charges"] if result.result_type == "BornEffectiveChargeResult" else result.arrays["epsilon_infinity"], dtype=float)
        if result.result_type == "BornEffectiveChargeResult":
            values = values[min(self.atom_index, len(values) - 1)]
        for row in range(3):
            for column in range(3):
                self.tensor_table.setItem(row, column, QTableWidgetItem(f"{values[row, column]:.6f}"))
        self.tensor_table.setToolTip("Rows: polarization Cartesian component; columns: displacement Cartesian component.")
    def _draw(self, result):
        import numpy as np
        key = "born_effective_charges" if result.result_type == "BornEffectiveChargeResult" else "epsilon_infinity"
        values = np.asarray(result.arrays[key], dtype=float)
        if result.result_type == "BornEffectiveChargeResult":
            values = values[min(self.atom_index, len(values)-1)]
            title = f"Born effective charge — atom {self.atom_index + 1}"
            unit = "e"
        else:
            title = "Electronic high-frequency dielectric tensor, ε∞"
            unit = "dimensionless"
        image = self.axes.imshow(values, cmap="viridis", aspect="equal")
        self.axes.set_xticks(range(3), ["x", "y", "z"])
        self.axes.set_yticks(range(3), ["x", "y", "z"])
        self.axes.set_xlabel("Displacement")
        self.axes.set_ylabel("Polarization")
        self.axes.set_title(title)
        self.axes.figure.colorbar(image, ax=self.axes, label=unit)


class RamanPlot(ScientificPlotWidget):
    """Native QE Raman activities with a selectable numeric mode tensor."""
    def __init__(self,parent=None):
        super().__init__(parent); self.frequency_unit="cm^-1"; self.mode_index=0
        self.mode_selector=QComboBox(self); self.tensor_table=QTableWidget(3,3,self); self.tensor_table.setHorizontalHeaderLabels(["Cartesian β x","Cartesian β y","Cartesian β z"]); self.tensor_table.setVerticalHeaderLabels(["Cartesian α x","Cartesian α y","Cartesian α z"])
        self.mode_selector.currentIndexChanged.connect(self._select_mode); self.layout().insertWidget(1,self.mode_selector,0); self.layout().insertWidget(2,self.tensor_table,0)
    def set_result(self,result):
        super().set_result(result); self.mode_selector.blockSignals(True); self.mode_selector.clear(); self.mode_selector.addItems([f"Mode {i+1}" for i in range(len(result.arrays.get("mode_indices",()))) ]); self.mode_selector.blockSignals(False); self._update_tensor(result)
    def _select_mode(self,index): self.mode_index=max(0,int(index)); self._update_tensor(self._result)
    def _update_tensor(self,result):
        if result is None or "raman_tensors" not in result.arrays: return
        values=np.asarray(result.arrays["raman_tensors"])[min(self.mode_index,len(result.arrays["raman_tensors"])-1)]
        for i in range(3):
            for j in range(3): self.tensor_table.setItem(i,j,QTableWidgetItem(f"{values[i,j]:.6f}"))
    def _draw(self,result):
        key="frequencies_THz" if self.frequency_unit=="THz" else "frequencies_cm1"; x=np.asarray(result.arrays[key],float); y=np.asarray(result.arrays["raman_activity"],float); self.axes.vlines(x,0,y,color="#69a7ff",linewidth=2); self.axes.plot(x,y,"o",color="#d7e7ff"); self.axes.set_xlabel(f"Raman shift ({'THz' if key=='frequencies_THz' else 'cm⁻¹'})"); self.axes.set_ylabel(f"Raman activity ({result.metadata.get('activity_unit','A^4/amu')})"); self.axes.set_title("QE-native Raman spectrum")
    def set_frequency_unit(self,unit): self.frequency_unit="THz" if str(unit).upper()=="THZ" else "cm^-1"; self.redraw()

class PhononDielectricPlot(ScientificPlotWidget):
    """Numeric electronic/ionic/static dielectric tensors and mode table."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.tensor_tables={}
        panel=QWidget(self); grid=QGridLayout(panel)
        for col,(key,title) in enumerate((("epsilon_infinity","Electronic ε∞"),("epsilon_ionic","Ionic εionic"),("epsilon_static","Static εstatic"))):
            label=QLabel(title,panel); grid.addWidget(label,0,col)
            table=QTableWidget(3,3,panel); table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers); table.setHorizontalHeaderLabels(["x","y","z"]); table.setVerticalHeaderLabels(["x","y","z"]); table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch); table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch); table.setMinimumHeight(132); self.tensor_tables[key]=table; grid.addWidget(table,1,col)
        self.mode_table=QTableWidget(panel); self.mode_table.setColumnCount(5); self.mode_table.setHorizontalHeaderLabels(["Mode","Frequency (cm⁻¹)","Included","Δεxx","Δεyy"]); self.mode_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch); grid.addWidget(QLabel("Mode-resolved ionic contribution (dimensionless)",panel),2,0,1,3); grid.addWidget(self.mode_table,3,0,1,3); self.layout().insertWidget(1,panel,0)
    def set_result(self,result):
        super().set_result(result); a=result.arrays
        for key,table in self.tensor_tables.items():
            values=np.asarray(a[key],float)
            for i in range(3):
                for j in range(3): table.setItem(i,j,QTableWidgetItem(f"{values[i,j]:.6f}"))
        freq=np.asarray(a["mode_frequencies_cm1"],float); inc=np.asarray(a["included_mode_mask"],bool); contrib=np.asarray(a["mode_dielectric_contributions"],float); self.mode_table.setRowCount(len(freq))
        for i in range(len(freq)):
            for j,value in enumerate((i+1,freq[i],"yes" if inc[i] else "no",contrib[i,0,0],contrib[i,1,1])): self.mode_table.setItem(i,j,QTableWidgetItem(f"{value:.6f}" if isinstance(value,(float,np.floating)) else str(value)))
    def export_data(self):
        if self._result is None: return
        path,_=QFileDialog.getSaveFileName(self,"Export Phonon Dielectric Response","phonon_dielectric.csv","CSV (*.csv);;NumPy archive (*.npz)")
        if not path: return
        target=Path(path)
        try:
            a=self._result.arrays
            if target.suffix.lower()==".npz":
                target=Path(normalize_export_filename(str(target),".npz")); np.savez(target,epsilon_infinity=a["epsilon_infinity"],epsilon_ionic=a["epsilon_ionic"],epsilon_static=a["epsilon_static"],mode_frequencies_cm1=a["mode_frequencies_cm1"],mode_frequencies_THz=a["mode_frequencies_THz"],mode_dielectric_contributions=a["mode_dielectric_contributions"],included_mode_mask=a["included_mode_mask"])
            else:
                target=Path(normalize_export_filename(str(target),".csv"))
                with target.open("w",newline="",encoding="utf-8") as f:
                    w=csv.writer(f); w.writerow(["tensor","alpha","beta","value"])
                    for key in ("epsilon_infinity","epsilon_ionic","epsilon_static"):
                        for i in range(3):
                            for j in range(3): w.writerow([key,"xyz"[i],"xyz"[j],a[key][i,j]])
                target.with_name(target.stem+"_modes.csv").write_text("mode,frequency_cm1,included,delta_epsilon_xx,delta_epsilon_yy,delta_epsilon_zz\n"+"\n".join(f"{i+1},{a['mode_frequencies_cm1'][i]},{bool(a['included_mode_mask'][i])},{a['mode_dielectric_contributions'][i,0,0]},{a['mode_dielectric_contributions'][i,1,1]},{a['mode_dielectric_contributions'][i,2,2]}" for i in range(len(a['mode_indices']))),encoding="utf-8")
            target.with_suffix(".json").write_text(json.dumps({"result_type":self._result.result_type,"metadata":self._result.metadata},indent=2,default=str),encoding="utf-8")
        except Exception as error: QMessageBox.warning(self,"Export Phonon Dielectric Response",f"Could not export data: {error}")

    def _draw(self,result):
        contrib=np.asarray(result.arrays["mode_dielectric_contributions"],float); freq=np.asarray(result.arrays["mode_frequencies_cm1"],float); mask=np.asarray(result.arrays["included_mode_mask"],bool); self.axes.scatter(freq[mask],contrib[mask,0,0],label="Δεxx"); self.axes.scatter(freq[mask],contrib[mask,1,1],label="Δεyy"); self.axes.scatter(freq[mask],contrib[mask,2,2],label="Δεzz"); self.axes.set_xlabel("Mode frequency (cm⁻¹)"); self.axes.set_ylabel("Dielectric contribution (dimensionless)"); self.axes.set_title("Ionic mode contributions"); self.axes.legend()

class LOTOPlot(ScientificPlotWidget):
    """Directional Γ analytic/non-analytic frequency comparison."""
    def _draw(self, result):
        key = "THz" if getattr(self, "frequency_unit", "cm^-1") == "THz" else "cm1"
        cm=np.asarray(result.arrays[f"frequencies_nonanalytic_{key}"],float)
        ref=np.asarray(result.arrays[f"frequencies_uncorrected_{key}"],float)
        x=np.arange(1,len(cm)+1)
        self.axes.plot(x,ref,"o-",label="Analytic Γ")
        self.axes.plot(x,cm,"s-",label="Non-analytic q→0")
        self.axes.axhline(0,color="#666666",linewidth=.8,linestyle="--")
        self.axes.set_xlabel("Mode index"); self.axes.set_ylabel(f"Frequency ({'THz' if key == 'THz' else 'cm⁻¹'})"); self.axes.set_title("Directional LO–TO splitting")
        self.axes.legend()
    def set_frequency_unit(self,unit):
        self.frequency_unit = "THz" if str(unit).upper() == "THZ" else "cm^-1"
        self.redraw()
    def export_data(self):
        if self._result is None: return
        path, _ = QFileDialog.getSaveFileName(self, "Export LO–TO Result", "lo_to.csv", "CSV (*.csv);;NumPy archive (*.npz)")
        if not path: return
        target = Path(path); arrays = self._result.arrays
        try:
            if target.suffix.lower() == ".npz":
                target = Path(normalize_export_filename(str(target), ".npz"))
                np.savez(target, direction_unit_cartesian=np.asarray(self._result.metadata.get("direction_unit_cartesian", ())), original_requested_direction=np.asarray(self._result.metadata.get("original_requested_direction", ())), frequencies_uncorrected_cm1=np.asarray(arrays["frequencies_uncorrected_cm1"]), frequencies_uncorrected_THz=np.asarray(arrays["frequencies_uncorrected_THz"]), frequencies_nonanalytic_cm1=np.asarray(arrays["frequencies_nonanalytic_cm1"]), frequencies_nonanalytic_THz=np.asarray(arrays["frequencies_nonanalytic_THz"]), frequency_shifts_cm1=np.asarray(arrays["frequency_shifts_cm1"]), frequency_shifts_THz=np.asarray(arrays["frequency_shifts_THz"]))
                target.with_suffix(".json").write_text(json.dumps({"result_type": self._result.result_type, "metadata": self._result.metadata}, indent=2, default=str), encoding="utf-8")
            else:
                target = Path(normalize_export_filename(str(target), ".csv")); export_csv(self._result, target)
        except Exception as error: QMessageBox.warning(self, "Export LO–TO Result", f"Could not export data: {error}")

class IRPlot(ScientificPlotWidget):
    """QE-native discrete infrared activities; no density Jacobian."""
    def __init__(self,parent=None): super().__init__(parent); self.frequency_unit="cm^-1"
    def _draw(self,result):
        key="frequencies_cm1" if self.frequency_unit=="cm^-1" else "frequencies_THz"
        x=np.asarray(result.arrays[key],float); y=np.asarray(result.arrays["native_ir_quantity"],float)
        self.axes.vlines(x,0,y,linewidth=1.4); self.axes.scatter(x,y,s=18)
        self.axes.set_xlabel(f"Frequency ({'cm⁻¹' if self.frequency_unit=='cm^-1' else 'THz'})")
        self.axes.set_ylabel("IR activity ((D/Å)²/amu)"); self.axes.set_title("Infrared spectrum (QE native activities)")
    def set_frequency_unit(self,unit): self.frequency_unit="THz" if str(unit).upper()=="THZ" else "cm^-1"; self.redraw()
    def export_data(self):
        if self._result is None: return
        path, _ = QFileDialog.getSaveFileName(self, "Export Infrared Spectrum", "infrared.csv", "CSV (*.csv);;NumPy archive (*.npz)")
        if not path: return
        target = Path(path); arrays = self._result.arrays
        try:
            if target.suffix.lower() == ".npz":
                target = Path(normalize_export_filename(str(target), ".npz"))
                np.savez(target, frequencies_cm1=np.asarray(arrays["frequencies_cm1"]), frequencies_THz=np.asarray(arrays["frequencies_THz"]), ir_activity=np.asarray(arrays["native_ir_quantity"]), activity_mask=np.asarray(arrays["activity_mask"]))
                target.with_suffix(".json").write_text(json.dumps({"result_type": self._result.result_type, "metadata": self._result.metadata}, indent=2, default=str), encoding="utf-8")
            else:
                target = Path(normalize_export_filename(str(target), ".csv")); export_csv(self._result, target)
        except Exception as error: QMessageBox.warning(self, "Export Infrared Spectrum", f"Could not export data: {error}")
