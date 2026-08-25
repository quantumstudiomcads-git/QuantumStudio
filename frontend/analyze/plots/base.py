from __future__ import annotations
from pathlib import Path
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QPushButton,QCheckBox,QFileDialog,QMessageBox
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from backend.analyze.export import export_csv

class ScientificPlotWidget(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent); self.figure=Figure(facecolor="#111318"); self.canvas=FigureCanvasQTAgg(self.figure); self.axes=self.figure.add_subplot(111); self.axes.set_facecolor("#111318"); self._result=None
        layout=QVBoxLayout(self); layout.setContentsMargins(4,4,4,4); layout.addWidget(self.canvas,1)
        bar=QHBoxLayout(); reset=QPushButton("Reset",self); reset.clicked.connect(self.reset_view); self.grid=QCheckBox("Grid",self); self.grid.toggled.connect(self._toggle_grid); data=QPushButton("Export Data…",self); data.clicked.connect(self.export_data); image=QPushButton("Export Image…",self); image.clicked.connect(self.export_image); reset.setToolTip("Restore automatic plot limits"); data.setToolTip("Export the structured Result data as CSV"); image.setToolTip("Export this plot without application chrome"); bar.addWidget(reset); bar.addWidget(self.grid); bar.addStretch(); bar.addWidget(data); bar.addWidget(image); layout.addLayout(bar)
    def reset_view(self): self.axes.relim(); self.axes.autoscale_view(); self.canvas.draw_idle()
    def _toggle_grid(self, checked): self.axes.grid(checked,color="#39414d",alpha=.5); self.canvas.draw_idle()
    def export_data(self):
        if self._result is None:return
        path,_=QFileDialog.getSaveFileName(self,"Export Result Data","result_data.csv",filter="CSV (*.csv)")
        if path:
            try:
                target=Path(path)
                if target.suffix.lower() != ".csv": target=target.with_suffix(".csv")
                export_csv(self._result,target)
            except Exception as error: QMessageBox.warning(self,"Export Data",f"Could not export data: {error}")
    def export_image(self):
        path,selected=QFileDialog.getSaveFileName(self,"Export Plot","scientific_plot.png",filter="PNG (*.png);;SVG (*.svg);;PDF (*.pdf)")
        if path:
            try:
                target=Path(path)
                suffix={"PNG (*.png)":".png","SVG (*.svg)":".svg","PDF (*.pdf)":".pdf"}.get(selected,".png")
                if not target.suffix: target=target.with_suffix(suffix)
                self.figure.savefig(target,facecolor=self.figure.get_facecolor(),bbox_inches="tight")
            except Exception as error: QMessageBox.warning(self,"Export Plot",f"Could not export image: {error}")
    def set_result(self,result): self._result=result; self.axes.clear(); self.axes.set_facecolor("#111318"); self.axes.tick_params(colors="#D9DCE3"); [sp.set_color("#596273") for sp in self.axes.spines.values()]; self._draw(result); self.canvas.draw_idle()
    def _draw(self,result):
        pass

    def closeEvent(self, event):
        # Release Matplotlib artists when a result view is replaced repeatedly.
        self.figure.clear()
        super().closeEvent(event)
