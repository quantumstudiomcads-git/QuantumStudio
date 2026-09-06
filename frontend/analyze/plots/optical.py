from __future__ import annotations

import numpy as np
from PySide6.QtWidgets import QComboBox, QFormLayout, QWidget

from backend.results.optical import wavelength_nm, derive_optical_arrays
from .base import ScientificPlotWidget


class OpticalPlot(ScientificPlotWidget):
    """Component-resolved optical spectra stored in ResultStore arrays."""

    _properties = ("Dielectric Real", "Dielectric Imaginary", "Absorption", "Refractive Index", "Extinction Coefficient", "Reflectivity", "Loss Function")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.property = "Dielectric Real"
        self.direction = "xx"
        self.axis = "Photon Energy (eV)"
        self.controls = QWidget(self)
        form = QFormLayout(self.controls)
        self.property_selector = QComboBox(self.controls); self.property_selector.addItems(self._properties)
        self.direction_selector = QComboBox(self.controls); self.direction_selector.addItems(("xx", "yy", "zz", "average"))
        self.axis_selector = QComboBox(self.controls); self.axis_selector.addItems(("Photon Energy (eV)", "Wavelength (nm)"))
        form.addRow("Quantity", self.property_selector); form.addRow("Direction", self.direction_selector); form.addRow("X axis", self.axis_selector)
        self.property_selector.currentTextChanged.connect(self._set_property)
        self.direction_selector.currentTextChanged.connect(self._set_direction)
        self.axis_selector.currentTextChanged.connect(self._set_axis)

    def _set_property(self, value): self.property = value; self.redraw()
    def _set_direction(self, value): self.direction = value; self.redraw()
    def _set_axis(self, value): self.axis = value; self.redraw()

    def _values(self, result):
        prefix = {
            "Dielectric Real": "epsilon1_", "Dielectric Imaginary": "epsilon2_",
            "Absorption": "absorption_coefficient_cm1_", "Refractive Index": "refractive_index_",
            "Extinction Coefficient": "extinction_coefficient_", "Reflectivity": "reflectivity_", "Loss Function": "loss_function_",
        }[self.property]
        source = result.arrays
        if result.result_type == "OpticalDielectricResult" and self.property not in ("Dielectric Real", "Dielectric Imaginary"):
            source = {**source, **derive_optical_arrays(source["energy_eV"], {d: (source[f"epsilon1_{d}"], source[f"epsilon2_{d}"]) for d in ("xx", "yy", "zz")})}
        if self.direction == "average":
            return np.mean(np.vstack([np.asarray(source[prefix + item], float) for item in ("xx", "yy", "zz")]), axis=0)
        return np.asarray(source[prefix + self.direction], float)

    def _draw(self, result):
        energy = np.asarray(result.arrays.get("energy_eV", ()), float)
        if energy.ndim != 1 or len(energy) < 2: return
        values = self._values(result)
        if len(values) != len(energy): return
        if self.axis == "Wavelength (nm)":
            positive = energy > 0
            x = wavelength_nm(energy[positive]); y = values[positive]
            order = np.argsort(x); x, y = x[order], y[order]
            xlabel = "Wavelength (nm)"
        else:
            x, y, xlabel = energy, values, "Photon Energy (eV)"
        ylabel = {"Dielectric Real": "ε₁ (dimensionless)", "Dielectric Imaginary": "ε₂ (dimensionless)", "Absorption": "Absorption coefficient (cm⁻¹)", "Refractive Index": "n (dimensionless)", "Extinction Coefficient": "κ (dimensionless)", "Reflectivity": "Reflectivity (dimensionless)", "Loss Function": "−Im[1/ε] (dimensionless)"}[self.property]
        self.figure.clear(); self.axes = self.figure.add_subplot(111)
        self.axes.plot(x, y, color="#3f7fbf", label=self.direction)
        self.axes.set_xlabel(xlabel); self.axes.set_ylabel(ylabel); self.axes.set_title(self.property)
        self.axes.grid(True, alpha=.25); self.axes.legend()
