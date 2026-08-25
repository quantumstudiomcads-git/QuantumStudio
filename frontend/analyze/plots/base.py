from __future__ import annotations
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QPushButton,QCheckBox,QFileDialog,QMessageBox
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from backend.analyze.export import export_csv

class ScientificPlotWidget(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent); self.figure=Figure(facecolor="#111318"); self.canvas=FigureCanvasQTAgg(self.figure); self.axes=self.figure.add_subplot(111); self.axes.set_facecolor("#111318"); self._result=None
        layout=QVBoxLayout(self); layout.setContentsMargins(4,4,4,4); layout.addWidget(self.canvas,1)
        bar=QHBoxLayout(); reset=QPushButton("Reset",self); reset.clicked.connect(self.reset_view); self.grid=QCheckBox("Grid",self); self.grid.toggled.connect(self._toggle_grid); data=QPushButton("Export Data…",self); data.clicked.connect(self.export_data); image=QPushButton("Export Image…",self); image.clicked.connect(self.export_image); bar.addWidget(reset); bar.addWidget(self.grid); bar.addStretch(); bar.addWidget(data); bar.addWidget(image); layout.addLayout(bar)
    def reset_view(self): self.axes.relim(); self.axes.autoscale_view(); self.canvas.draw_idle()
    def _toggle_grid(self, checked): self.axes.grid(checked,color="#39414d",alpha=.5); self.canvas.draw_idle()
    def export_data(self):
        if self._result is None:return
        path,_=QFileDialog.getSaveFileName(self,"Export Result Data",filter="CSV (*.csv)")
        if path:
            try: export_csv(self._result,path)
            except Exception as error: QMessageBox.warning(self,"Export Data",str(error))
    def export_image(self):
        path,_=QFileDialog.getSaveFileName(self,"Export Plot",filter="PNG (*.png);;SVG (*.svg);;PDF (*.pdf)")
        if path:self.figure.savefig(path,facecolor=self.figure.get_facecolor(),bbox_inches="tight")
    def set_result(self,result): self._result=result; self.axes.clear(); self.axes.set_facecolor("#111318"); self.axes.tick_params(colors="#D9DCE3"); [sp.set_color("#596273") for sp in self.axes.spines.values()]; self._draw(result); self.canvas.draw_idle()
    def _draw(self,result):
        pass
