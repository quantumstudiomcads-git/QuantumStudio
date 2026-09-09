import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtWidgets import QApplication

from backend.results import ResultProvenance, ResultStatus, ScientificResult
from frontend.analyze.plots.transport import TransportPlot
from frontend.analyze.workspace import AnalyzeWorkspace
from frontend.core import Project


class TransportAnalyzeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.provenance = ResultProvenance("request", "execution", "transport", "boltztrap2", "btp2", (), {}, "btp2.transport.json")

    def result(self):
        mu = np.array([-0.15, 0.0, 0.15])
        temperatures = np.array([300.0, 500.0])
        carrier = np.array([[-2.0e19, 0.0, 3.0e19], [-1.0e19, 0.0, 2.0e19]])
        tensor = np.zeros((2, 3, 3, 3))
        tensor[:, :, 0, 0] = 1.0
        tensor[:, :, 1, 1] = 2.0
        tensor[:, :, 2, 2] = 3.0
        return ScientificResult("TransportResult", ResultStatus.VALID, self.provenance, arrays={
            "temperatures_K": temperatures, "chemical_potential_eV": mu,
            "carrier_concentration_cm3": carrier, "seebeck": tensor,
            "electrical_conductivity_over_tau": tensor + 10.0,
            "electronic_thermal_conductivity_over_tau": tensor + 20.0,
        }, metadata={"backend": "BoltzTraP2", "backend_version": "26.3.1",
                     "units": {"seebeck": "V K^-1", "electrical_conductivity_over_tau": "S m^-1 s",
                               "electronic_thermal_conductivity_over_tau": "W m^-1 K^-1 s", "carrier_concentration": "cm^-3"},
                     "method_assumptions": {"energy_reference": "QE Fermi reference"}})

    def test_transport_plot_controls_and_selection(self):
        workspace = AnalyzeWorkspace(Project("Transport Analyze"))
        workspace.current_result = self.result()
        workspace._show_plot()
        try:
            self.assertIsInstance(workspace.plot, TransportPlot)
            self.assertEqual(workspace.transport_property.count(), 4)
            self.assertEqual(workspace.transport_temperature.count(), 2)
            self.assertIn("xx", [workspace.transport_component.itemText(i) for i in range(workspace.transport_component.count())])
            self.assertIn("Chemical potential relative to QE Fermi reference", workspace.plot.axes.get_xlabel())
            workspace.transport_property.setCurrentText("Signed carrier concentration")
            self.assertIn("Signed carrier concentration", workspace.plot.axes.get_ylabel())
            workspace.transport_temperature.setCurrentIndex(1)
            workspace.transport_component.setCurrentText("zz")
            self.assertEqual(len(workspace.plot.axes.lines[0].get_ydata()), 3)
            workspace._show_table()
            self.assertEqual(workspace.table_model.rowCount(), 3)
        finally:
            workspace.close()

    def test_transport_exports_preserve_arrays_and_figure_formats(self):
        plot = TransportPlot()
        plot.set_result(self.result())
        with tempfile.TemporaryDirectory() as directory:
            directory = os.path.abspath(directory)
            plot.export_transport_npz(os.path.join(directory, "transport.npz"))
            with np.load(os.path.join(directory, "transport.npz")) as archive:
                self.assertEqual(archive["seebeck"].shape, (2, 3, 3, 3))
                self.assertEqual(archive["carrier_concentration_cm3"].shape, (2, 3))
            for suffix in ("png", "pdf", "svg"):
                plot.export_figure(os.path.join(directory, "transport." + suffix), fmt=suffix, dpi=120)
                self.assertGreater(os.path.getsize(os.path.join(directory, "transport." + suffix)), 0)
        plot.close()


if __name__ == "__main__":
    unittest.main()
