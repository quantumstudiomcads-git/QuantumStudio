from __future__ import annotations
from pathlib import Path
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QPushButton,QCheckBox,QFileDialog,QMessageBox

EXPORT_EXTENSIONS = {"PNG (*.png)":".png", "JPEG (*.jpg *.jpeg)":".jpg", "SVG (*.svg)":".svg", "PDF (*.pdf)":".pdf", "CSV (*.csv)":".csv"}

def normalize_export_filename(name, extension):
    """Replace only a final recognized export suffix, or append the selected suffix."""
    ext = extension if extension.startswith(".") else "." + extension
    known = {".png", ".jpg", ".jpeg", ".svg", ".pdf", ".csv"}
    path = Path(str(name))
    if path.suffix.lower() in known:
        return str(path.with_suffix(ext))
    return str(path) + ext
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from backend.analyze.export import export_csv

class ScientificPlotWidget(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent); self.figure=Figure(facecolor="#111318"); self.canvas=FigureCanvasQTAgg(self.figure); self.axes=self.figure.add_subplot(111); self.axes.set_facecolor("#111318"); self._result=None
        layout=QVBoxLayout(self); layout.setContentsMargins(4,4,4,4); layout.addWidget(self.canvas,1)
        self.toolbar=QHBoxLayout(); reset=QPushButton("Reset",self); reset.clicked.connect(self.reset_view); self.grid=QCheckBox("Grid",self); self.grid.setChecked(False); self.grid.toggled.connect(self._toggle_grid); data=QPushButton("Export Data…",self); data.clicked.connect(self.export_data); image=QPushButton("Export Image…",self); image.clicked.connect(self.export_image); reset.setToolTip("Restore automatic plot limits"); data.setToolTip("Export the structured Result data as CSV"); image.setToolTip("Export this plot without application chrome"); self.toolbar.addWidget(reset); self.toolbar.addWidget(self.grid); self.toolbar.addStretch(); self.toolbar.addWidget(data); self.toolbar.addWidget(image); layout.addLayout(self.toolbar)
    def reset_view(self): self.axes.relim(); self.axes.autoscale_view(); self.canvas.draw_idle()
    def _toggle_grid(self, checked):
        if checked: self.axes.grid(True,color="#39414d",alpha=.5)
        else: self.axes.grid(False)
        self.canvas.draw_idle()
    def export_data(self):
        if self._result is None:return
        path,_=QFileDialog.getSaveFileName(self,"Export Result Data","result_data.csv",filter="CSV (*.csv)")
        if path:
            try:
                target=Path(path)
                target=Path(normalize_export_filename(target, ".csv"))
                export_csv(self._result,target)
            except Exception as error: QMessageBox.warning(self,"Export Data",f"Could not export data: {error}")
    def export_image(self):
        dialog = QFileDialog(self, "Export Plot", "scientific_plot.png")
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        filters = ["PNG (*.png)", "JPEG (*.jpg *.jpeg)", "SVG (*.svg)", "PDF (*.pdf)"]
        dialog.setNameFilters(filters)
        dialog.selectNameFilter(filters[0])
        def update_suffix(selected):
            current = dialog.selectedFiles()[0] if dialog.selectedFiles() else "scientific_plot.png"
            dialog.selectFile(normalize_export_filename(current, EXPORT_EXTENSIONS.get(selected, ".png")))
        dialog.filterSelected.connect(update_suffix)
        if dialog.exec():
            try:
                selected = dialog.selectedNameFilter()
                suffix = EXPORT_EXTENSIONS.get(selected, ".png")
                target = Path(normalize_export_filename(dialog.selectedFiles()[0], suffix))
                face = "white" if suffix == ".jpg" else self.figure.get_facecolor()
                self.figure.savefig(target, facecolor=face, bbox_inches="tight", dpi=300)
            except Exception as error: QMessageBox.warning(self, "Export Plot", f"Could not export image: {error}")
    def set_result(self,result):
        if hasattr(self,"_selection_artist"): self._selection_artist=None
        if hasattr(self,"_measurement_artist"): self._measurement_artist=None
        self._result=result; self.axes.clear(); self.axes.set_facecolor("#111318"); self.axes.tick_params(colors="#D9DCE3"); [sp.set_color("#596273") for sp in self.axes.spines.values()]; self._draw(result); self._toggle_grid(self.grid.isChecked()); self.canvas.draw_idle()
    def _draw(self,result):
        pass

    def closeEvent(self, event):
        # Release Matplotlib artists when a result view is replaced repeatedly.
        self.figure.clear()
        super().closeEvent(event)
