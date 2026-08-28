from __future__ import annotations
import numpy as np
from .base import ScientificPlotWidget

class ProjectionPlot(ScientificPlotWidget):
    def _draw(self, result):
        t=result.result_type
        if t == "LowdinPopulationResult":
            y=np.asarray(result.arrays.get("population",()),float); x=np.arange(len(y))+1
            mask=np.isfinite(y); bars=self.axes.bar(x[mask],y[mask],color="#55C7D9"); self.appearance_state.series.setdefault("population",{}); [setattr(bar,"_qs_series_id","population") for bar in bars]
            self.axes.set_xlabel("Projector index"); self.axes.set_ylabel("Population (electrons)"); self.axes.set_title("Löwdin Population Analysis")
        elif t == "MagneticMomentResult":
            y=np.asarray(result.arrays.get("projected_local_moment",()),float); x=np.asarray(result.arrays.get("atom_index",np.arange(len(y))+1),float); mask=np.isfinite(x)&np.isfinite(y)
            bars=self.axes.bar(x[mask],y[mask],color="#E8A85C"); self.appearance_state.series.setdefault("magnetic_moment",{}); [setattr(bar,"_qs_series_id","magnetic_moment") for bar in bars]; line=self.axes.axhline(0,color="#9097A5",linewidth=.8); line._qs_reference_id="zero_moment"; self.appearance_state.reference_lines.setdefault("zero_moment",{}); self.axes.set_xlabel("Atom index"); self.axes.set_ylabel("Projected local moment (µB-like)"); self.axes.set_title("Magnetic Moments")
        elif t == "OrbitalCharacterResult":
            k=np.asarray(result.arrays.get("k_index",()),float); b=np.asarray(result.arrays.get("band_index",()),int); w=np.asarray(result.arrays.get("projection_weight",()),float)
            e=np.asarray(result.arrays.get("energy_eV",()),float) if "energy_eV" in result.arrays else w
            finite=np.isfinite(k)&np.isfinite(w)&np.isfinite(e)
            for band in sorted(set(b[finite].tolist())):
                sel=finite&(b==band); line=self.axes.plot(k[sel],e[sel],color="#7C8799",linewidth=.8)[0]; line._qs_series_id=f"orbital_band:{band}"; self.appearance_state.series.setdefault(line._qs_series_id,{})
                sizes=20+100*w[sel]/max(float(np.nanmax(w[sel])),1e-12); artist=self.axes.scatter(k[sel],e[sel],s=sizes,c=w[sel],cmap="viridis",vmin=0,vmax=max(float(np.nanmax(w[sel])),1e-12),label=f"band {band}"); artist._qs_series_id=f"orbital_projection:{band}"; self.appearance_state.series.setdefault(artist._qs_series_id,{})
            self.axes.set_xlabel("k-point index"); self.axes.set_ylabel("Energy (eV)" if "energy_eV" in result.arrays else "Projection weight"); self.axes.set_title("Orbital Character / Texture")
        handles, labels = self.axes.get_legend_handles_labels()
        if handles:
            self.axes.legend(loc="best")
