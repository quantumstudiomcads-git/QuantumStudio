import os, unittest
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
import numpy as np
from PySide6.QtWidgets import QApplication
from backend.results.models import ResultProvenance,ResultStatus,ScientificResult
from frontend.analyze.plots.volumetric import VolumetricPlot
class VolumetricAnalyzeE4Tests(unittest.TestCase):
 def test_slice_profile_and_display_only_controls(self):
  app=QApplication.instance() or QApplication([]); result=ScientificResult("VolumetricResult",ResultStatus.VALID,ResultProvenance("r","e","t","qe","pp.x",(),{},"fixture"),arrays={"values":np.arange(27,dtype=float).reshape(3,3,3)},metadata={"cell":[[3,0,0],[0,3,0],[0,0,3]],"origin":[0,0,0],"unit":"e/bohr^3","quantity_kind":"SPIN_DENSITY","signed":True})
  plot=VolumetricPlot(); plot.set_result(result); self.assertTrue(plot.axes.images); first=plot.axes.images[0].get_array().copy(); plot.position.setValue(66); self.assertFalse(np.array_equal(first,plot.axes.images[0].get_array())); plot.mode.setCurrentText("Profile"); self.assertTrue(plot.axes.lines); self.assertTrue(np.array_equal(result.arrays["values"],np.arange(27).reshape(3,3,3)))

