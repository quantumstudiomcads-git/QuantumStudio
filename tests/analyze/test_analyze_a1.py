import os, tempfile, unittest, csv
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from frontend.analyze import AnalyzeWorkspace
from frontend.core import Project
from backend.results import ResultProvenance, ResultStatus, ScientificResult
from backend.analyze import tabular_data, export_csv

class AnalyzeA1Tests(unittest.TestCase):
    def test_empty_workspace(self):
        app=QApplication.instance() or QApplication([]); w=AnalyzeWorkspace(Project("A1")); w.show(); app.processEvents()
        self.assertEqual(w.calculation.count(),0); self.assertIn("No results",w.empty.text()); w.close()
    def test_band_table_and_csv(self):
        p=ResultProvenance("r","e","t","qe","pw.x",(),{},"fixture")
        r=ScientificResult("BandStructureResult",ResultStatus.VALID,p,arrays={"path_coordinate":[0,1],"energies":[[-1,1],[-.5,.5]]})
        headers,rows=tabular_data(r); self.assertEqual(headers,["path_coordinate","band_1","band_2"]); self.assertEqual(len(rows),2)
        with tempfile.TemporaryDirectory() as d:
            path=export_csv(r,os.path.join(d,"bands.csv")); self.assertTrue(path.is_file());
            with path.open() as stream: self.assertEqual(len(list(csv.reader(stream))),3)
    def test_dos_units_remain_result_metadata(self):
        p=ResultProvenance("r","e","t","qe","dos.x",(),{},"fixture")
        r=ScientificResult("DOSResult",ResultStatus.VALID,p,arrays={"energy":[-1,0],"dos":[1,2]},metadata={"units":{"energy":"eV"}})
        self.assertEqual(tabular_data(r)[0],["energy","dos"]); self.assertEqual(r.metadata["units"]["energy"],"eV")
