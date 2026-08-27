from __future__ import annotations
import numpy as np
from .base import ScientificPlotWidget

class FermiSurfacePlot(ScientificPlotWidget):
    """Lightweight reciprocal-grid slice view of QE fs.x energies.

    The raw BXSF remains exportable; this view deliberately plots finite grid
    traces so Analyze never presents an empty placeholder when a surface exists.
    """
    def _draw(self, result):
        energies=np.asarray(result.arrays.get("energies", ()), dtype=float)
        if energies.ndim != 4 or energies.shape[0] == 0: return
        ef=result.metadata.get("fermi_energy_eV")
        if ef is None: ef=0.0
        for band, values in enumerate(energies):
            trace=np.asarray(values).reshape(-1)
            self.axes.plot(np.arange(trace.size), trace-float(ef), label=f"band {band+1}")
        self.axes.axhline(0.0,color="#d95f02",linewidth=0.8)
        self.axes.set_xlabel("Uniform reciprocal-grid sample")
        self.axes.set_ylabel("E - E_F (eV)")
        self.axes.set_title("Fermi-surface band energies")
        if energies.shape[0] <= 12: self.axes.legend()
