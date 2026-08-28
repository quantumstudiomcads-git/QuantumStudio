from __future__ import annotations
import numpy as np
from .base import ScientificPlotWidget

class DerivedElectronicPlot(ScientificPlotWidget):
    def _draw(self, result):
        kind=result.result_type
        if kind=="BandGapResult":
            x=np.asarray(result.arrays.get("path_coordinate",()),float); y=np.asarray(result.arrays.get("energies",()),float)
            if y.ndim==1:y=y[:,None]
            if len(x) and y.ndim==2:
                for i in range(y.shape[1]): line=self.axes.plot(x,y[:,i],color="#55C7D9",label="Band structure" if i==0 else "_nolegend_")[0]; line._qs_series_id="bands"; self.appearance_state.series.setdefault("bands",{})
                for key,color,marker in (("vbm","#C44E52","v"),("cbm","#4C72B0","^")):
                    edge=result.metadata.get(key) or {}; idx=edge.get("path_sample_index")
                    if idx is not None and 0<=int(idx)<len(x): artist=self.axes.scatter([x[int(idx)]],[y[int(idx),int(edge.get("band_index",0))]],color=color,marker=marker,s=55,zorder=5,label=key.upper()); artist._qs_series_id=key; self.appearance_state.series.setdefault(key,{})
            self.axes.set_title("Band Gap Analysis"); self.axes.set_xlabel("Path coordinate"); self.axes.set_ylabel("Energy (eV)")
        elif kind=="EffectiveMassResult":
            x=np.asarray(result.arrays.get("k_distance_Ainv",()),float); y=np.asarray(result.arrays.get("energy_eV",()),float); fit=np.asarray(result.arrays.get("fit_energy_eV",()),float)
            if len(x) and len(y): line=self.axes.plot(x,y,"o",label="Sampled E(k)")[0]; line._qs_series_id="sampled"; self.appearance_state.series.setdefault("sampled",{})
            if len(x) and len(fit): line=self.axes.plot(x,fit,"-",label="Parabolic fit")[0]; line._qs_series_id="fit"; self.appearance_state.series.setdefault("fit",{})
            edge=result.metadata.get("edge") or {}; energy=edge.get("energy_eV")
            if energy is not None and len(x): artist=self.axes.scatter([x[0]],[energy],marker="*",s=75,label="Edge"); artist._qs_series_id="edge"; self.appearance_state.series.setdefault("edge",{})
            self.axes.set_title("Effective Mass"); self.axes.set_xlabel("Distance from edge (Å⁻¹)"); self.axes.set_ylabel("Energy (eV)")
        self.axes.legend()
