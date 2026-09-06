from __future__ import annotations

import numpy as np

from .base import ScientificPlotWidget


class EliashbergPlot(ScientificPlotWidget):
    """Plot persisted alpha2F and cumulative-lambda result arrays."""

    def _draw(self, result):
        frequency = np.asarray(result.arrays.get("frequency", result.arrays.get("frequency_meV", result.arrays.get("frequency_mev", ()))), dtype=float)
        alpha2f = np.asarray(result.arrays.get("alpha2F", result.arrays.get("alpha2f", ())), dtype=float)
        if alpha2f.ndim > 1:
            alpha2f = alpha2f[:, 0]
        cumulative = np.asarray(result.arrays.get("cumulative_lambda", ()), dtype=float)
        if cumulative.size == 0 and frequency.size == alpha2f.size:
            cumulative = np.zeros_like(frequency)
            if frequency.size > 1:
                integrand = np.divide(alpha2f, frequency, out=np.zeros_like(alpha2f), where=frequency != 0)
                cumulative[1:] = np.cumsum(0.5 * (integrand[1:] + integrand[:-1]) * np.diff(frequency)) * 2.0
        if frequency.size == 0 or alpha2f.size != frequency.size:
            return
        self.figure.clear()
        self.axes = self.figure.add_subplot(111)
        self.axes.plot(frequency, alpha2f, color="#55C7D9", label=r"$\alpha^2F(\omega)$")
        if cumulative.size == frequency.size:
            self.axes.plot(frequency, cumulative, color="#E8A85C", label=r"$\lambda(\omega)$")
        self.axes.set_xlabel(result.metadata.get("frequency_unit", "Frequency"))
        self.axes.set_ylabel(r"$\alpha^2F(\omega)$ / $\lambda(\omega)$")
        self.axes.set_title("Eliashberg Function")
        self.axes.legend()
        self.axes.grid(True, alpha=0.25)
