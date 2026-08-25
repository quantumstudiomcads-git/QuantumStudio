from .base import ScientificPlotWidget


class BandPlot(ScientificPlotWidget):
    """Dark, engine-neutral band canvas with optional A7 derived-edge annotations."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.edge_analysis = None
        self.show_band_edges = False
        self.energy_offset = 0.0
        self.reference_label = "Absolute"

    def configure_electronic_analysis(self, analysis, *, show_edges=False, energy_offset=0.0, reference_label="Absolute"):
        self.edge_analysis = analysis
        self.show_band_edges = bool(show_edges)
        self.energy_offset = float(energy_offset)
        self.reference_label = reference_label

    def _draw(self, result):
        import numpy as np
        x = result.arrays.get("path_coordinate", result.arrays.get("kpoint"))
        y = result.arrays.get("energies", result.arrays.get("energy"))
        if y is None:
            return
        y = np.asarray(y, dtype=float) - self.energy_offset
        x = np.arange(len(y)) if x is None else np.asarray(x, dtype=float)
        y = y[:, None] if y.ndim == 1 else y
        for index in range(y.shape[1]):
            self.axes.plot(x, y[:, index], color="#55C7D9", linewidth=1.2)
        fermi = result.metadata.get("fermi_energy", result.scalars.get("fermi_energy", {}).get("value"))
        if fermi is not None and self.reference_label != "Fermi = 0":
            self.axes.axhline(float(fermi) - self.energy_offset, color="#E8A85C", linewidth=1, linestyle="--")
        elif self.reference_label in {"Fermi = 0", "VBM = 0"}:
            self.axes.axhline(0.0, color="#E8A85C", linewidth=1, linestyle="--")
        if self.show_band_edges and self.edge_analysis is not None and self.edge_analysis.status == "VALID":
            for edge in self.edge_analysis.degenerate_vbm:
                if edge.path_sample_index < len(x):
                    self.axes.scatter([x[edge.path_sample_index]], [edge.energy - self.energy_offset], marker="v", s=42,
                                      color="#E8A85C", edgecolors="#111318", linewidths=.7, zorder=6,
                                      label="VBM" if edge is self.edge_analysis.degenerate_vbm[0] else "_nolegend_")
            for edge in self.edge_analysis.degenerate_cbm:
                if edge.path_sample_index < len(x):
                    self.axes.scatter([x[edge.path_sample_index]], [edge.energy - self.energy_offset], marker="^", s=42,
                                      color="#B88AE6", edgecolors="#111318", linewidths=.7, zorder=6,
                                      label="CBM" if edge is self.edge_analysis.degenerate_cbm[0] else "_nolegend_")
            self.axes.legend(facecolor="#17191F", labelcolor="#E8EAF0", fontsize=8)
        self.axes.set_xlabel("Path coordinate", color="#D9DCE3")
        self.axes.set_ylabel("Energy (eV)", color="#D9DCE3")
        suffix = "" if self.reference_label == "Absolute" else f" — {self.reference_label}"
        self.axes.set_title("Band Structure" + suffix, color="#E8EAF0")
