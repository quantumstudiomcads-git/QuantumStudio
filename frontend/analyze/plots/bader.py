from __future__ import annotations
import numpy as np
from .base import ScientificPlotWidget

class BaderChargePlot(ScientificPlotWidget):
    def _draw(self, result):
        transfer = result.result_type == "ChargeTransferResult"
        key = "charge_transfer" if transfer and "charge_transfer" in result.arrays else "net_charge"
        y = np.asarray(result.arrays.get(key, ()), dtype=float)
        x = np.asarray(result.arrays.get("atom_index", np.arange(len(y))+1), dtype=float)
        mask = np.isfinite(x) & np.isfinite(y)
        if not np.any(mask):
            self.axes.text(0.5, 0.5, "No finite charge data", ha="center", va="center", transform=self.axes.transAxes)
            return
        bars=self.axes.bar(x[mask], y[mask], color="#55C7D9" if not transfer else "#E8A85C"); self.appearance_state.series.setdefault("charge_transfer" if transfer else "net_charge",{}); [setattr(bar,"_qs_series_id","charge_transfer" if transfer else "net_charge") for bar in bars]
        line=self.axes.axhline(0.0, color="#9097A5", linewidth=0.8); line._qs_reference_id="zero_charge"; self.appearance_state.reference_lines.setdefault("zero_charge",{})
        self.axes.set_xlabel("Atom index")
        self.axes.set_ylabel("Net atomic charge (e)" if not transfer else "Charge transfer (e)")
        self.axes.set_title("Bader Charge Analysis" if not transfer else "Atomic Charge Transfer (Bader)")
        self.axes.set_xticks(x[mask])
