from __future__ import annotations
from pathlib import Path
from PySide6.QtWidgets import QComboBox,QLabel,QSlider,QFileDialog,QMessageBox
from PySide6.QtCore import Qt
from .base import ScientificPlotWidget,normalize_export_filename
from backend.analyze.volumetric import export_slice_csv,export_profile_csv,export_volumetric_npz
from backend.results.volumetric import field_slice,field_profile
class VolumetricPlot(ScientificPlotWidget):
 def __init__(self,parent=None):
  super().__init__(parent); self.mode=QComboBox(self); self.mode.addItems(["2D Slice","Profile"]); self.plane=QComboBox(self); self.plane.addItems(["XY","XZ","YZ"]); self.position=QSlider(Qt.Orientation.Horizontal,self); self.position.setRange(0,100); self.mode.currentIndexChanged.connect(self._redraw); self.plane.currentIndexChanged.connect(self._redraw); self.position.valueChanged.connect(self._redraw); self.toolbar.insertWidget(1,QLabel("View:",self)); self.toolbar.insertWidget(2,self.mode); self.toolbar.insertWidget(3,QLabel("Plane:",self)); self.toolbar.insertWidget(4,self.plane); self.toolbar.insertWidget(5,QLabel("Position:",self)); self.toolbar.insertWidget(6,self.position)
 def _redraw(self,*_):
  if self._result is not None: super().set_result(self._result)
 def _draw(self,result):
  if hasattr(self,"_colorbar") and self._colorbar is not None:
   try:
    if getattr(self._colorbar,"ax",None) is not None: self._colorbar.remove()
   except (AttributeError,ValueError): pass
   self._colorbar=None
  unit=result.metadata.get("unit",""); signed=bool(result.metadata.get("signed")); title=result.metadata.get("quantity_kind","Volumetric field").replace("_"," ").title()
  if self.mode.currentText()=="Profile":
   profile=field_profile(result,{"XY":"Z","XZ":"Y","YZ":"X"}[self.plane.currentText()]); self.axes.plot(profile["distance_A"],profile["values"]); self.axes.set_xlabel(f"Distance along {profile['axis']} (Å)"); self.axes.set_ylabel(unit); self.axes.set_title(title+" planar profile")
  else:
   data=field_slice(result,self.plane.currentText(),self.position.value()/100); limit=max(abs(float(data.values.min())),abs(float(data.values.max()))) if signed else None; image=self.axes.imshow(data.values.T,origin="lower",aspect="auto",cmap=self.appearance_state.colormap or ("RdBu_r" if signed else "viridis"),vmin=self.appearance_state.color_min if self.appearance_state.color_min is not None else (-limit if signed else None),vmax=self.appearance_state.color_max if self.appearance_state.color_max is not None else (limit if signed else None)); self._colorbar=self.figure.colorbar(image,ax=self.axes,label=self.appearance_state.colorbar_label or unit); image._qs_series_id="volumetric_field"; self.appearance_state.series.setdefault("volumetric_field",{}); self.axes.set_xlabel(self.plane.currentText()[0]+" fractional"); self.axes.set_ylabel(self.plane.currentText()[1]+" fractional"); self.axes.set_title(f"{title} {self.plane.currentText()} slice")
 def export_data(self):
  if self._result is None:return
  path,_=QFileDialog.getSaveFileName(self,"Export field data","field_slice.csv",filter="Slice CSV (*.csv);;Profile CSV (*.csv);;NPZ (*.npz)")
  if not path:return
  try:
   target=Path(path)
   if target.suffix.lower()==".npz": export_volumetric_npz(self._result,target)
   elif self.mode.currentText()=="Profile": export_profile_csv(self._result,Path(normalize_export_filename(target,".csv")),{"XY":"Z","XZ":"Y","YZ":"X"}[self.plane.currentText()])
   else: export_slice_csv(self._result,Path(normalize_export_filename(target,".csv")),self.plane.currentText(),self.position.value()/100)
  except Exception as error: QMessageBox.warning(self,"Export field data",str(error))

