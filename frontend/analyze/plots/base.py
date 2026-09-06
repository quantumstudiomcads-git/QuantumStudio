from __future__ import annotations
from pathlib import Path
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QPushButton,QCheckBox,QFileDialog,QMessageBox,QDialog,QFormLayout,QComboBox,QDoubleSpinBox,QDialogButtonBox,QLineEdit,QInputDialog,QColorDialog,QSpinBox,QGroupBox,QScrollArea,QLabel,QListWidget,QStackedWidget,QSizePolicy)
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from backend.analyze.export import export_csv
from .appearance import PlotAppearanceState, PlotSeriesAppearance, UserPlotPresetStore, available_font_families, DEFAULT_COLOR_CYCLE

EXPORT_EXTENSIONS = {"PNG (*.png)": ".png", "SVG (*.svg)": ".svg", "PDF (*.pdf)": ".pdf"}

def normalize_export_filename(name, extension):
    ext = extension if extension.startswith(".") else "." + extension
    known = {".png",".jpg",".jpeg",".svg",".pdf",".csv",".npz"}
    path = Path(str(name))
    return str(path.with_suffix(ext)) if path.suffix.lower() in known else str(path)+ext

class _CategoryCompatibility:
    """Small read-only compatibility facade for older callers/tests.

    The visible navigation is now a vertical QListWidget, not a horizontal
    tab bar.
    """
    def __init__(self, names):
        self._names = ("Presets",) + tuple(names)
    def count(self):
        return len(self._names)
    def tabText(self, index):
        return self._names[index]


class PlotAppearanceEditor(QScrollArea):
    def __init__(self, plot, parent=None):
        super().__init__(parent)
        self.plot = plot
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(5)

        # Presets are a compact toolbar shared by every style category.
        preset_bar = QHBoxLayout()
        preset_bar.setSpacing(4)
        preset_bar.addWidget(QLabel("Preset"))
        self.preset = QComboBox()
        self.preset.addItem("Default")
        self.preset.addItems(plot.presets.names())
        self.preset.setMinimumWidth(100)
        preset_bar.addWidget(self.preset, 1)
        save = QPushButton("Save As…")
        reset = QPushButton("Reset")
        delete = QPushButton("Delete")
        save.setToolTip("Save the current visual settings as a reusable preset")
        delete.setToolTip("Delete the selected user preset")
        preset_bar.addWidget(save)
        preset_bar.addWidget(reset)
        preset_bar.addWidget(delete)
        layout.addLayout(preset_bar)
        self._delete_preset_button = delete

        categories = ("Series", "Axes", "Text", "Reference", "Legend", "Figure")
        self.category_names = categories
        self.category_tabs = _CategoryCompatibility(categories)
        self.category_list = QListWidget()
        self.category_list.addItems(categories)
        self.category_list.setFixedWidth(96)
        self.category_list.setSpacing(1)
        self.category_stack = QStackedWidget()
        self.style_categories = {}
        for category in categories:
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(3, 3, 3, 3)
            page_layout.setSpacing(5)
            self.style_categories[category] = page_layout
            self.category_stack.addWidget(page)
        self.category_list.currentRowChanged.connect(self.category_stack.setCurrentIndex)
        self.category_list.setCurrentRow(0)
        category_layout = QHBoxLayout()
        category_layout.setContentsMargins(0, 0, 0, 0)
        category_layout.setSpacing(5)
        category_layout.addWidget(self.category_list, 0)
        category_layout.addWidget(self.category_stack, 1)
        layout.addLayout(category_layout, 1)

        self.controls = {}
        typography = QGroupBox("Typography")
        tf = QFormLayout(typography)
        self._combo("font_family", "Font family", tf, available_font_families())
        for key, label in (("title_font_size", "Title size"), ("axis_label_font_size", "Axis-label size"), ("tick_label_font_size", "Tick-label size"), ("legend_font_size", "Legend size"), ("annotation_font_size", "Annotation size")):
            self._spin(key, label, tf, 2, 48)
        self._check("title_bold", "Title bold", tf)
        self._check("title_italic", "Title italic", tf)
        self._check("axis_label_bold", "Axis-label bold", tf)
        self._check("axis_label_italic", "Axis-label italic", tf)
        self.style_categories["Text"].addWidget(typography)

        figure = QGroupBox("Figure")
        ff = QFormLayout(figure)
        self._spin("figure_width", "Export width (in)", ff, .1, 30, decimals=2)
        self._spin("figure_height", "Export height (in)", ff, .1, 30, decimals=2)
        self._color("figure_background", "Figure background", ff)
        self._color("axes_background", "Axes background", ff)
        self._check("show_title", "Show title", ff)
        self._line("title", "Title", ff)
        self.style_categories["Figure"].addWidget(figure)
        image = QGroupBox("Image / Colorbar")
        imf = QFormLayout(image)
        self._combo("colormap", "Colormap", imf, ("viridis", "plasma", "inferno", "magma", "cividis", "RdBu_r", "coolwarm"))
        self._combo("interpolation", "Interpolation", imf, ("nearest", "bilinear", "bicubic"))
        self._spin("color_min", "Color minimum", imf, 0, 1, decimals=5, nullable=True)
        self._spin("color_max", "Color maximum", imf, 0, 1, decimals=5, nullable=True)
        self._check("colorbar_visible", "Show colorbar", imf)
        self._line("colorbar_label", "Colorbar label", imf)
        self.style_categories["Figure"].addWidget(image)

        axes = QGroupBox("Axes")
        af = QFormLayout(axes)
        self._line("x_label_override", "X label", af)
        self._line("y_label_override", "Y label", af)
        for key, label in (("x_min", "X minimum"), ("x_max", "X maximum"), ("y_min", "Y minimum"), ("y_max", "Y maximum")):
            self._spin(key, label, af, -1e6, 1e6, decimals=5, nullable=True)
        self._combo("x_scale", "X scale", af, ("linear", "log"))
        self._combo("y_scale", "Y scale", af, ("linear", "log"))
        self._spin("spine_width", "Spine width", af, 0.1, 10, decimals=2)
        self._combo("major_tick_direction", "Tick direction", af, ("in", "out"))
        self._check("minor_ticks_enabled", "Minor ticks", af)
        self.style_categories["Axes"].addWidget(axes)
        grid = QGroupBox("Grid")
        gf = QFormLayout(grid)
        self._check("show_grid", "Show grid", gf)
        self._color("grid_color", "Color", gf)
        self._combo("grid_line_style", "Line style", gf, ("Solid", "Dashed", "Dotted", "Dash-dot"))
        self._spin("grid_line_width", "Width", gf, .1, 10, decimals=2)
        self._spin("grid_alpha", "Opacity", gf, 0, 1, decimals=2)
        self.style_categories["Axes"].addWidget(grid)

        series = QGroupBox("Series")
        sf = QFormLayout(series)
        self.series_combo = QComboBox()
        sf.addRow("Series", self.series_combo)
        self._series_control("visible", "Visible", sf)
        self._series_control("color", "Color", sf)
        self._series_control("line_width", "Line width", sf)
        self._series_control("line_style", "Line style", sf, ("Solid", "Dashed", "Dotted", "Dash-dot", "None"))
        self._series_control("marker", "Marker", sf, ("None", "Circle", "Square", "Triangle Up", "Triangle Down", "Diamond", "Cross", "Plus"))
        self._series_control("marker_size", "Marker size", sf)
        self._series_control("opacity", "Opacity", sf)
        all_button = QPushButton("Apply to All Series")
        sf.addRow(all_button)
        all_button.clicked.connect(self.apply_all)
        self.style_categories["Series"].addWidget(series)

        references = QGroupBox("Reference Lines")
        rf = QFormLayout(references)
        self.reference_combo = QComboBox()
        self.reference_visible = QCheckBox()
        self.reference_color = QPushButton()
        self.reference_width = QDoubleSpinBox()
        self.reference_width.setRange(0, 10)
        self.reference_width.setValue(0.8)
        self.reference_style = QComboBox()
        self.reference_style.addItems(["Solid", "Dashed", "Dotted", "Dash-dot"])
        self.reference_opacity = QDoubleSpinBox()
        self.reference_opacity.setRange(0, 1)
        self.reference_opacity.setDecimals(2)
        self.reference_opacity.setValue(1)
        rf.addRow("Reference", self.reference_combo)
        rf.addRow("Visible", self.reference_visible)
        rf.addRow("Color", self.reference_color)
        rf.addRow("Width", self.reference_width)
        rf.addRow("Style", self.reference_style)
        rf.addRow("Opacity", self.reference_opacity)
        self.style_categories["Reference"].addWidget(references)
        legend = QGroupBox("Legend")
        lf = QFormLayout(legend)
        self._check("show_legend", "Show legend", lf)
        self._combo("legend_location", "Position", lf, ("best", "upper right", "upper left", "lower right", "lower left", "center right", "center left", "lower center", "upper center", "center"))
        self._spin("legend_columns", "Columns", lf, 1, 20, decimals=0)
        self._check("legend_frame", "Frame", lf)
        self._spin("legend_frame_alpha", "Frame opacity", lf, 0, 1, decimals=2)
        self.style_categories["Legend"].addWidget(legend)
        for page_layout in self.style_categories.values():
            page_layout.addStretch(1)

        save.clicked.connect(self.save_preset_as)
        reset.clicked.connect(plot.reset_appearance)
        delete.clicked.connect(self.delete_current_preset)
        self.preset.currentTextChanged.connect(self._preset_selected)
        self.reference_combo.currentTextChanged.connect(self._load_reference)
        self.reference_visible.toggled.connect(self._reference_changed)
        self.reference_color.clicked.connect(self._pick_reference_color)
        self.reference_width.valueChanged.connect(self._reference_changed)
        self.reference_style.currentTextChanged.connect(self._reference_changed)
        self.reference_opacity.valueChanged.connect(self._reference_changed)
        self.setWidget(body)
        self._load_state()
        self.series_combo.currentIndexChanged.connect(self._load_series)

    def _add(self,key,widget,label,form): self.controls[key]=widget; form.addRow(label,widget); widget.destroyed.connect(lambda:None)
    def _spin(self,key,label,form,minimum,maximum,decimals=2,nullable=False):
        if nullable:
            box=QLineEdit(); box.setPlaceholderText("Auto"); self._add(key,box,label,form); box.textChanged.connect(lambda value,k=key:self._nullable_changed(k,value)); return
        box=QDoubleSpinBox(); box.setRange(minimum,maximum); box.setDecimals(decimals); box.setSingleStep(.1); self._add(key,box,label,form); box.valueChanged.connect(lambda value,k=key:self._changed(k,value))
    def _nullable_changed(self,key,value):
        text=value.strip()
        if not text or text.lower()=="auto": setattr(self.plot.appearance_state,key,None)
        else:
            try: setattr(self.plot.appearance_state,key,float(text))
            except ValueError: return
        self.plot.redraw()
    def _line(self,key,label,form): box=QLineEdit(); self._add(key,box,label,form); box.textChanged.connect(lambda value,k=key:self._changed(k,value))
    def _combo(self,key,label,form,items): box=QComboBox(); box.addItems(list(items)); self._add(key,box,label,form); box.currentTextChanged.connect(lambda value,k=key:self._changed(k,value))
    def _check(self,key,label,form): box=QCheckBox(); self._add(key,box,label,form); box.toggled.connect(lambda value,k=key:self._changed(k,value))
    def _color(self,key,label,form):
        box=QPushButton(); box.setMinimumWidth(80); self._add(key,box,label,form); box.clicked.connect(lambda _=False,k=key:self._pick(k))
    def _series_control(self,key,label,form,items=None):
        if items: self._combo("series_"+key,label,form,items)
        elif key=="visible": self._check("series_"+key,label,form)
        elif key=="color": self._color("series_"+key,label,form)
        else: self._spin("series_"+key,label,form,0,100,decimals=2)
        w=self.controls["series_"+key]
        if isinstance(w,QComboBox): w.currentTextChanged.connect(self._series_changed)
        elif isinstance(w,QCheckBox): w.toggled.connect(self._series_changed)
        elif isinstance(w,QPushButton): w.clicked.connect(self._series_changed)
        else: w.valueChanged.connect(self._series_changed)
    def _load_reference(self,*_):
        key=self.reference_combo.currentData() or self.reference_combo.currentText(); value=self.plot.appearance_state.reference_lines.get(key,{})
        self.reference_visible.setChecked(value.get("visible",True)); self._set_color_button(self.reference_color, value.get("color","#808080")); self.reference_color.setProperty("color_value", value.get("color","#808080")); self.reference_width.setValue(float(value.get("line_width",.8))); self.reference_style.setCurrentText({"-":"Solid","--":"Dashed",":":"Dotted","-.":"Dash-dot"}.get(value.get("line_style","--"),"Dashed")); self.reference_opacity.setValue(float(value.get("opacity",1)))
    def _reference_changed(self,*_):
        key=self.reference_combo.currentData() or self.reference_combo.currentText();
        if key: self.plot.appearance_state.reference_lines[key]={"visible":self.reference_visible.isChecked(),"color":self.reference_color.property("color_value") or "#808080","line_width":self.reference_width.value(),"line_style":{"Solid":"-","Dashed":"--","Dotted":":","Dash-dot":"-."}.get(self.reference_style.currentText(),"--"),"opacity":self.reference_opacity.value()}; self.plot.redraw()
    def _pick_reference_color(self):
        color=QColorDialog.getColor(QColor(self.reference_color.property("color_value") or "#808080"),self)
        if color.isValid(): self._set_color_button(self.reference_color, color.name()); self.reference_color.setProperty("color_value", color.name()); self._reference_changed()
    def _load_state(self):
        s=self.plot.appearance_state
        for key,w in self.controls.items():
            if key.startswith("series_"): continue
            value=getattr(s,key)
            if isinstance(w,QComboBox): w.setCurrentText(str(value))
            elif isinstance(w,QCheckBox): w.setChecked(bool(value))
            elif isinstance(w,QLineEdit): w.setText("" if value is None else str(value))
            elif isinstance(w,QPushButton): self._set_color_button(w, str(value))
            elif isinstance(w,QDoubleSpinBox): w.setValue(float(value or 0))
        self._refresh_series(); self.reference_combo.blockSignals(True); self.reference_combo.clear(); self.reference_combo.addItems(list(s.reference_lines)); self.reference_combo.blockSignals(False); self._load_reference()
    def _changed(self,key,value):
        if key in ("x_min","x_max","y_min","y_max") and value == 0 and self.controls[key].specialValueText()=="Auto": value=None
        setattr(self.plot.appearance_state,key,value); self.plot.redraw()
    def _set_color_button(self, button, color):
        button.setText("  "+color)
        button.setProperty("color_value", color)
        button.setStyleSheet("QPushButton { background-color: %s; color: black; border: 1px solid #68717d; padding: 2px 6px; text-align: left; }" % color)
    def _pick(self,key):
        color=QColorDialog.getColor(QColor(getattr(self.plot.appearance_state,key)),self)
        if color.isValid(): self._set_color_button(self.controls[key], color.name()); self._changed(key,color.name())
    def _refresh_series(self):
        self.series_combo.blockSignals(True); self.series_combo.clear();
        for key in self.plot.appearance_state.series: self.series_combo.addItem(getattr(self.plot,"series_labels",{}).get(key,key),key); self.series_combo.blockSignals(False); self._load_series()
    def _load_series(self,*_):
        key=self.series_combo.currentData() or self.series_combo.currentText()
        value=PlotSeriesAppearance.from_dict(self.plot.appearance_state.series.get(key,{}))
        style_map={"-":"Solid","--":"Dashed",":":"Dotted","-.":"Dash-dot","None":"None"}
        marker_map={"none":"None","o":"Circle","s":"Square","^":"Triangle Up","v":"Triangle Down","D":"Diamond","x":"Cross","+":"Plus"}
        for field in ("visible","color","line_width","line_style","marker","marker_size","opacity"):
            widget=self.controls["series_"+field]; value_for_ui=getattr(value,field)
            if field=="line_style": value_for_ui=style_map.get(value_for_ui,value_for_ui)
            if field=="marker": value_for_ui=marker_map.get(value_for_ui,value_for_ui)
            if isinstance(widget,QComboBox): widget.setCurrentText(str(value_for_ui))
            elif isinstance(widget,QCheckBox): widget.setChecked(bool(value_for_ui))
            elif isinstance(widget,QPushButton):
                color=value_for_ui or "#0072B2"; self._set_color_button(widget, color)
            else: widget.setValue(float(value_for_ui or 0))

    def _series_changed(self,*_):
        key=self.series_combo.currentData() or self.series_combo.currentText()
        if not key:return
        value=PlotSeriesAppearance.from_dict(self.plot.appearance_state.series.get(key,{}))
        style_map={"Solid":"-","Dashed":"--","Dotted":":","Dash-dot":"-.","None":"None"}
        marker_map={"None":"none","Circle":"o","Square":"s","Triangle Up":"^","Triangle Down":"v","Diamond":"D","Cross":"x","Plus":"+"}
        for field in ("visible","color","line_width","line_style","marker","marker_size","opacity"):
            widget=self.controls["series_"+field]
            if isinstance(widget,QComboBox): current=widget.currentText(); setattr(value,field,style_map.get(current,marker_map.get(current,current)))
            elif isinstance(widget,QCheckBox): setattr(value,field,widget.isChecked())
            elif isinstance(widget,QPushButton): setattr(value,field,widget.property("color_value") or "#0072B2")
            else: setattr(value,field,widget.value())
        self.plot.appearance_state.series[key]=value.__dict__.copy()
        self.plot.redraw()

    def apply_all(self):
        key=self.series_combo.currentData() or self.series_combo.currentText()
        if not key:return
        source=dict(self.plot.appearance_state.series.get(key,{}))
        for other in self.plot.appearance_state.series: self.plot.appearance_state.series[other]=dict(source)
        self.plot.redraw()
    def _refresh_presets(self):
        current = self.preset.currentText()
        self.preset.blockSignals(True)
        self.preset.clear(); self.preset.addItem("Default"); self.preset.addItems(self.plot.presets.names())
        self.preset.setCurrentText(current if self.preset.findText(current) >= 0 else "Default")
        self.preset.blockSignals(False)
        self._delete_preset_button.setEnabled(self.preset.currentText() != "Default")
    def save_preset_as(self):
        self.plot.save_appearance_preset()
        self._refresh_presets()
    def _preset_selected(self, name):
        self._delete_preset_button.setEnabled(name != "Default")
        if name == "Default":
            self.plot.reset_appearance()
            return
        try:
            self.plot.appearance_state = self.plot.presets.load(name)
            self._load_state(); self.plot.redraw()
        except Exception as error:
            QMessageBox.warning(self, "Appearance", f"Could not load preset: {error}")
    def delete_current_preset(self):
        name = self.preset.currentText()
        if name == "Default": return
        self.plot.presets.delete(name)
        self._refresh_presets()

class ScientificPlotWidget(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent); self.appearance_state=PlotAppearanceState.default(); self.presets=UserPlotPresetStore(); self.figure=Figure(figsize=(self.appearance_state.figure_width,self.appearance_state.figure_height),facecolor="white"); self.canvas=FigureCanvasQTAgg(self.figure); self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding); self.canvas.setMinimumSize(0,0); self.axes=self.figure.add_subplot(111); self._result=None
        layout=QVBoxLayout(self); layout.setContentsMargins(4,4,4,4); layout.setSpacing(4); self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding); self.interaction_toolbar=QWidget(self); self.interaction_layout=QHBoxLayout(self.interaction_toolbar); self.interaction_layout.setContentsMargins(2,2,2,2); self.interaction_layout.setSpacing(4); self.interaction_toolbar.setVisible(False); layout.addWidget(self.interaction_toolbar,0); layout.addWidget(self.canvas,1)
    def create_appearance_editor(self,parent=None): return PlotAppearanceEditor(self,parent)
    def edit_appearance(self):
        return None
    def save_appearance_preset(self):
        name,ok=QInputDialog.getText(self,"Save Appearance Preset","Preset name:")
        if ok and name.strip():
            try: self.presets.save(name,self.appearance_state)
            except ValueError as error: QMessageBox.warning(self,"Appearance",str(error))
    def reset_view(self): self.axes.relim(); self.axes.autoscale_view(); self.canvas.draw_idle()
    def _toggle_grid(self,checked): self.appearance_state.show_grid=checked; self.apply_appearance(); self.canvas.draw_idle()
    def export_data(self):
        if self._result is None:return
        path,_=QFileDialog.getSaveFileName(self,"Export Result Data","result_data.csv","CSV (*.csv)")
        if path:
            try: export_csv(self._result,Path(normalize_export_filename(path,".csv")))
            except Exception as error: QMessageBox.warning(self,"Export Data",f"Could not export data: {error}")
    def export_figure(self,path,fmt=None,dpi=300,background="current",tight=True,width=None,height=None):
        if width is not None and width<=0 or height is not None and height<=0 or int(dpi)<=0: raise ValueError("Figure dimensions and DPI must be positive")
        old_size=self.figure.get_size_inches().copy(); old_face=self.figure.get_facecolor()
        if width is not None and height is not None:self.figure.set_size_inches(float(width),float(height),forward=True)
        face={"current":old_face,"white":"white","transparent":"none"}.get(background,background)
        self.figure.savefig(Path(path),format=fmt,dpi=int(dpi),facecolor=face,bbox_inches="tight" if tight else None)
        if width is not None and height is not None:self.figure.set_size_inches(old_size,forward=True)
    def export_image(self):
        dialog=QDialog(self); dialog.setWindowTitle("Export Figure"); form=QFormLayout(dialog)
        path_box=QLineEdit("scientific_plot.png"); dpi=QSpinBox(); dpi.setRange(1,9600); dpi.setValue(300)
        width=QDoubleSpinBox(); width.setRange(.1,30); width.setDecimals(2); width.setValue(self.appearance_state.figure_width)
        height=QDoubleSpinBox(); height.setRange(.1,30); height.setDecimals(2); height.setValue(self.appearance_state.figure_height)
        background=QComboBox(); background.addItems(["Current","White","Transparent"]); tight=QCheckBox(); tight.setChecked(True)
        form.addRow("File",path_box); form.addRow("DPI",dpi); form.addRow("Width (in)",width); form.addRow("Height (in)",height); form.addRow("Background",background); form.addRow("Tight bounding box",tight)
        choose=QPushButton("Choose…"); form.addRow(choose); buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel); form.addRow(buttons)
        choose.clicked.connect(lambda: path_box.setText(QFileDialog.getSaveFileName(self,"Export Figure",path_box.text(),"PNG (*.png);;SVG (*.svg);;PDF (*.pdf)")[0] or path_box.text()))
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject)
        if dialog.exec()!=QDialog.DialogCode.Accepted or not path_box.text().strip(): return
        try:
            suffix=Path(path_box.text()).suffix.lower() or ".png"; suffix=suffix if suffix in (".png",".svg",".pdf") else ".png"
            target=Path(normalize_export_filename(path_box.text(),suffix)); self.export_figure(target,fmt=suffix[1:],dpi=dpi.value(),background=background.currentText().lower(),tight=tight.isChecked(),width=width.value(),height=height.value())
        except Exception as error: QMessageBox.warning(self,"Export Figure",f"Could not export figure: {error}")
    def set_result(self,result):
        self._result=result; self.axes.clear(); self.axes.set_facecolor("white"); self._draw(result); self.series_labels={};
        for artist in self.axes.lines:
            key=getattr(artist,"_qs_series_id",None)
            if key: self.series_labels.setdefault(key,artist.get_label() if artist.get_label() not in ("_nolegend_","") else key)
        for artist in self.axes.patches:
            key=getattr(artist,"_qs_series_id",None)
            if key: self.series_labels.setdefault(key,key.replace("_"," " ).title())
        for artist in self.axes.collections:
            key=getattr(artist,"_qs_series_id",None)
            if key: self.series_labels.setdefault(key,artist.get_label() if artist.get_label() not in ("_nolegend_","") else key)
        self.apply_appearance(); self.canvas.draw_idle()
    def redraw(self):
        if self._result is not None:self.set_result(self._result)
    def _style_artist(self,artist,style):
        if hasattr(artist,"set_visible"): artist.set_visible(style.visible)
        if style.color and hasattr(artist,"set_color"): artist.set_color(style.color)
        if hasattr(artist,"set_linewidth"): artist.set_linewidth(style.line_width)
        if hasattr(artist,"set_linestyle"): artist.set_linestyle(style.line_style)
        if hasattr(artist,"set_marker"): artist.set_marker("None" if style.marker=="none" else style.marker)
        if hasattr(artist,"set_markersize"): artist.set_markersize(style.marker_size)
        if hasattr(artist,"set_alpha"): artist.set_alpha(style.opacity)
    def apply_appearance(self):
        s=self.appearance_state; self.figure.set_facecolor(s.figure_background); self.axes.set_facecolor(s.axes_background); self.axes.tick_params(direction=s.major_tick_direction,labelsize=s.tick_label_font_size,length=s.major_tick_length,width=s.major_tick_width,colors="black",which="major"); self.axes.tick_params(length=s.minor_tick_length,width=s.minor_tick_width,which="minor"); self.axes.minorticks_on() if s.minor_ticks_enabled else self.axes.minorticks_off(); self.axes.set_xscale(s.x_scale); self.axes.set_yscale(s.y_scale)
        if s.x_min is not None and s.x_max is not None:self.axes.set_xlim(s.x_min,s.x_max)
        if s.y_min is not None and s.y_max is not None:self.axes.set_ylim(s.y_min,s.y_max)
        self.axes.title.set_fontfamily(s.font_family); self.axes.title.set_fontsize(s.title_font_size); self.axes.title.set_fontweight("bold" if s.title_bold else "normal"); self.axes.title.set_fontstyle("italic" if s.title_italic else "normal"); self.axes.title.set_visible(s.show_title)
        for label in (self.axes.xaxis.label,self.axes.yaxis.label): label.set_fontfamily(s.font_family); label.set_fontsize(s.axis_label_font_size); label.set_fontweight("bold" if s.axis_label_bold else "normal"); label.set_fontstyle("italic" if s.axis_label_italic else "normal"); label.set_color("black")
        if s.x_label_override:self.axes.set_xlabel(s.x_label_override)
        if s.y_label_override:self.axes.set_ylabel(s.y_label_override)
        for label in self.axes.get_xticklabels()+self.axes.get_yticklabels(): label.set_fontfamily(s.font_family); label.set_fontsize(s.tick_label_font_size); label.set_color("black")
        for spine in self.axes.spines.values(): spine.set_linewidth(s.spine_width); spine.set_color("black")
        for artist in self.axes.lines:
            key=getattr(artist,"_qs_series_id",None)
            if key in s.series:self._style_artist(artist,PlotSeriesAppearance.from_dict(s.series[key]))
            ref=getattr(artist,"_qs_reference_id",None)
            if ref in s.reference_lines:self._style_artist(artist,PlotSeriesAppearance.from_dict(s.reference_lines[ref]))
        for artist in self.axes.collections:
            key=getattr(artist,"_qs_series_id",None)
            if key in s.series:
                style=PlotSeriesAppearance.from_dict(s.series[key]); artist.set_visible(style.visible); artist.set_alpha(style.opacity)
                if style.color: artist.set_facecolor(style.color); artist.set_edgecolor(style.color)
                if hasattr(artist,"set_sizes") and style.marker_size: artist.set_sizes([style.marker_size ** 2])
        for artist in self.axes.patches:
            key=getattr(artist,"_qs_series_id",None)
            if key in s.series:
                style=PlotSeriesAppearance.from_dict(s.series[key]); artist.set_visible(style.visible); artist.set_facecolor(style.color or artist.get_facecolor()); artist.set_edgecolor(style.color or artist.get_edgecolor()); artist.set_linewidth(style.line_width); artist.set_alpha(style.opacity)
        for image in self.axes.images:
            image.set_cmap(s.colormap); image.set_interpolation(s.interpolation)
            if s.color_min is not None and s.color_max is not None: image.set_clim(s.color_min,s.color_max)
        for text in self.figure.texts: text.set_fontfamily(s.font_family); text.set_fontsize(s.annotation_font_size)
        for axis in self.figure.axes:
            axis.xaxis.label.set_fontfamily(s.font_family); axis.yaxis.label.set_fontfamily(s.font_family); axis.xaxis.label.set_fontsize(s.axis_label_font_size); axis.yaxis.label.set_fontsize(s.axis_label_font_size)
            for text in axis.get_xticklabels()+axis.get_yticklabels(): text.set_fontfamily(s.font_family); text.set_fontsize(s.tick_label_font_size)
        if hasattr(self,"_colorbar") and self._colorbar is not None: self._colorbar.ax.set_visible(s.colorbar_visible)
        legend=self.axes.get_legend()
        if legend:
            legend.set_visible(s.show_legend); legend.set_frame_on(s.legend_frame); legend.get_frame().set_alpha(s.legend_frame_alpha); legend.set_ncols(s.legend_columns); legend.set_loc(s.legend_location)
            for text in legend.get_texts(): text.set_fontfamily(s.font_family); text.set_fontsize(s.legend_font_size); text.set_color("black")
        self.axes.grid(True,color=s.grid_color,linestyle=s.grid_line_style,linewidth=s.grid_line_width,alpha=s.grid_alpha) if s.show_grid else self.axes.grid(False)
    def reset_appearance(self):
        self.appearance_state=PlotAppearanceState.default(); self.redraw()
    def _draw(self,result): pass
    def closeEvent(self,event): self.figure.clear(); super().closeEvent(event)
