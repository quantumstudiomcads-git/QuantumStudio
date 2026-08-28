from __future__ import annotations
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any
from matplotlib import font_manager

DEFAULT_FONT_FAMILY = "DejaVu Sans"
DEFAULT_TITLE_SIZE = 11.0
DEFAULT_AXIS_LABEL_SIZE = 10.0
DEFAULT_TICK_LABEL_SIZE = 9.0
DEFAULT_LEGEND_SIZE = 9.0
DEFAULT_ANNOTATION_SIZE = 9.0
DEFAULT_LINE_WIDTH = 1.2
DEFAULT_SPINE_WIDTH = 0.8
DEFAULT_FIGURE_WIDTH = 6.4
DEFAULT_FIGURE_HEIGHT = 4.2
DEFAULT_COLOR_CYCLE = ("#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9")

def available_font_families() -> tuple[str, ...]:
    return tuple(sorted({str(x.name).strip() for x in font_manager.fontManager.ttflist if str(x.name).strip()}, key=str.casefold))

@dataclass
class PlotSeriesAppearance:
    visible: bool = True
    color: str | None = None
    line_width: float = DEFAULT_LINE_WIDTH
    line_style: str = "-"
    marker: str = "none"
    marker_size: float = 5.0
    opacity: float = 1.0
    @classmethod
    def from_dict(cls, values: Any):
        values = values if isinstance(values, dict) else {}
        aliases={"title_size":"title_font_size","axis_label_size":"axis_label_font_size","tick_label_size":"tick_label_font_size","legend_size":"legend_font_size","annotation_size":"annotation_font_size","background":"figure_background","tick_direction":"major_tick_direction","minor_ticks":"minor_ticks_enabled"}; values={aliases.get(k,k):v for k,v in values.items()}; clean = {k:v for k,v in values.items() if k in cls.__dataclass_fields__}
        try:
            clean["line_width"] = max(0.0, float(clean.get("line_width", DEFAULT_LINE_WIDTH)))
            clean["marker_size"] = max(0.0, float(clean.get("marker_size", 5.0)))
            clean["opacity"] = min(1.0, max(0.0, float(clean.get("opacity", 1.0))))
        except (TypeError, ValueError): return cls()
        return cls(**clean)

@dataclass
class PlotAppearanceState:
    title: str = ""
    show_title: bool = True
    figure_width: float = DEFAULT_FIGURE_WIDTH
    figure_height: float = DEFAULT_FIGURE_HEIGHT
    figure_background: str = "white"
    axes_background: str = "white"
    font_family: str = DEFAULT_FONT_FAMILY
    title_font_size: float = DEFAULT_TITLE_SIZE
    title_bold: bool = False
    title_italic: bool = False
    axis_label_font_size: float = DEFAULT_AXIS_LABEL_SIZE
    axis_label_bold: bool = False
    axis_label_italic: bool = False
    tick_label_font_size: float = DEFAULT_TICK_LABEL_SIZE
    legend_font_size: float = DEFAULT_LEGEND_SIZE
    annotation_font_size: float = DEFAULT_ANNOTATION_SIZE
    x_label_override: str = ""
    y_label_override: str = ""
    x_min: float | None = None
    x_max: float | None = None
    y_min: float | None = None
    y_max: float | None = None
    x_scale: str = "linear"
    y_scale: str = "linear"
    spine_width: float = DEFAULT_SPINE_WIDTH
    major_tick_direction: str = "in"
    minor_ticks_enabled: bool = True
    major_tick_length: float = 3.5
    minor_tick_length: float = 2.0
    major_tick_width: float = 0.8
    minor_tick_width: float = 0.6
    show_legend: bool = True
    legend_location: str = "best"
    legend_columns: int = 1
    legend_frame: bool = False
    legend_frame_alpha: float = 0.8
    reference_lines: dict[str, dict[str, Any]] = field(default_factory=dict)
    series: dict[str, dict[str, Any]] = field(default_factory=dict)
    show_grid: bool = False
    grid_color: str = "#808080"
    grid_line_style: str = ":"
    grid_line_width: float = 0.6
    grid_alpha: float = 0.35
    colormap: str = "viridis"
    interpolation: str = "nearest"
    color_min: float | None = None
    color_max: float | None = None
    colorbar_visible: bool = True
    colorbar_label: str = ""
    @property
    def background(self): return self.figure_background
    @background.setter
    def background(self, value): self.figure_background = value
    @property
    def title_size(self): return self.title_font_size
    @title_size.setter
    def title_size(self, value): self.title_font_size = value
    @property
    def axis_label_size(self): return self.axis_label_font_size
    @axis_label_size.setter
    def axis_label_size(self, value): self.axis_label_font_size = value
    @property
    def tick_label_size(self): return self.tick_label_font_size
    @tick_label_size.setter
    def tick_label_size(self, value): self.tick_label_size = value
    @property
    def legend_size(self): return self.legend_font_size
    @legend_size.setter
    def legend_size(self, value): self.legend_font_size = value
    @property
    def annotation_size(self): return self.annotation_font_size
    @annotation_size.setter
    def annotation_size(self, value): self.annotation_font_size = value
    @property
    def tick_direction(self): return self.major_tick_direction
    @tick_direction.setter
    def tick_direction(self, value): self.major_tick_direction = value
    @property
    def minor_ticks(self): return self.minor_ticks_enabled
    @minor_ticks.setter
    def minor_ticks(self, value): self.minor_ticks_enabled = value
    @classmethod
    def default(cls): return cls()
    @classmethod
    def from_dict(cls, values: Any):
        values = values if isinstance(values, dict) else {}
        clean = {k:v for k,v in values.items() if k in cls.__dataclass_fields__}
        installed = set(available_font_families())
        if clean.get("font_family") not in installed:
            clean["font_family"] = DEFAULT_FONT_FAMILY if DEFAULT_FONT_FAMILY in installed else next(iter(installed), DEFAULT_FONT_FAMILY)
        for key, default in (("figure_width", DEFAULT_FIGURE_WIDTH), ("figure_height", DEFAULT_FIGURE_HEIGHT), ("spine_width", DEFAULT_SPINE_WIDTH)):
            try: clean[key] = max(0.1, float(clean.get(key, default)))
            except (TypeError, ValueError): clean[key] = default
        try: clean["legend_columns"] = max(1, int(clean.get("legend_columns", 1)))
        except (TypeError, ValueError): clean["legend_columns"] = 1
        clean["series"] = {str(k): PlotSeriesAppearance.from_dict(v).__dict__ for k,v in (clean.get("series") or {}).items()}
        return cls(**clean)
    def to_dict(self): return asdict(self)
    def copy(self): return type(self).from_dict(self.to_dict())

class UserPlotPresetStore:
    def __init__(self, directory=None): self.directory = Path(directory or (Path.home() / ".quantum_studio_plot_presets"))
    def _path(self, name):
        clean = str(name).strip()
        if not clean or Path(clean).name != clean: raise ValueError("Preset name must be a non-empty simple name")
        return self.directory / (clean + ".json")
    def save(self, name, state):
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(name)
        path.write_text(json.dumps(state.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        return path
    def load(self, name):
        try: return PlotAppearanceState.from_dict(json.loads(self._path(name).read_text(encoding="utf-8")))
        except (OSError, ValueError, json.JSONDecodeError) as error: raise ValueError(f"Could not load appearance preset: {error}") from error
    def delete(self, name):
        try: self._path(name).unlink(missing_ok=True)
        except OSError: pass
    def names(self):
        return tuple(sorted((p.stem for p in self.directory.glob("*.json")), key=str.casefold)) if self.directory.exists() else ()
