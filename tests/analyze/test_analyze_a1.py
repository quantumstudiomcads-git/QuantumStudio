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

    def test_pdos_filters_and_aggregation(self):
        from backend.analyze.transforms import pdos_channels
        p=ResultProvenance("r","e","t","qe","projwfc.x",(),{},"fixture")
        r=ScientificResult("PDOSResult",ResultStatus.VALID,p,arrays={"energy":[0,1]},metadata={"components":[{"species":"Si","atom":1,"orbital":"p"},{"species":"O","atom":2,"orbital":"p"}],"component_values":[[1,2],[3,4]]})
        self.assertEqual(len(pdos_channels(r,species="Si")),1)
        grouped=pdos_channels(r,aggregation="By species"); self.assertEqual(len(grouped),2)

    def test_project_execution_root_pointer_roundtrip(self):
        from frontend.core import Project
        project=Project("Roots"); project.register_execution_root("request-a","/tmp/workflow-a")
        self.assertEqual(project.execution_roots()["request-a"],"/tmp/workflow-a")

    def test_comparison_compatibility_and_provenance(self):
        from backend.analyze import AnalysisSeries, ComparisonModel, compatible_results, provenance_differences
        p=ResultProvenance("r1","e1","t","qe","pw.x",(),{},"fixture",structure_fingerprint="same")
        a=ScientificResult("BandStructureResult",ResultStatus.VALID,p,arrays={"energy":[0,1]},metadata={"band_path":[{"label":"G"},{"label":"X"}],"functional":"PBE"})
        b=ScientificResult("BandStructureResult",ResultStatus.STALE,ResultProvenance("r2","e2","t","qe","pw.x",(),{},"fixture",structure_fingerprint="same"),arrays={"energy":[0,1]},metadata={"band_path":[{"label":"G"},{"label":"X"}],"functional":"HSE06"})
        model=compatible_results(a,b); self.assertEqual(model.compatibility,"POTENTIALLY_COMPATIBLE"); self.assertTrue(model.warnings); self.assertTrue(provenance_differences(model))
        bad=ScientificResult("DOSResult",ResultStatus.VALID,p,arrays={"energy":[0]}); self.assertEqual(compatible_results(a,bad).compatibility,"INCOMPATIBLE")

    def test_shared_energy_alignment_does_not_mutate_result(self):
        from backend.analyze.transforms import energy_reference, exact_difference, frequency_convert
        p=ResultProvenance("r","e","t","qe","pw.x",(),{},"f")
        a=ScientificResult("DOSResult",ResultStatus.VALID,p,arrays={"energy":[1.,2.]},metadata={"fermi_energy":1.})
        self.assertEqual(energy_reference(a,"Fermi = 0").tolist(),[0.,1.]); self.assertEqual(a.arrays["energy"].tolist() if hasattr(a.arrays["energy"],"tolist") else a.arrays["energy"],[1.,2.])
        b=ScientificResult("DOSResult",ResultStatus.VALID,p,arrays={"energy":[1.,2.]})
        b.arrays["dos"]=[3.,5.]; a.arrays["dos"]=[1.,2.]; self.assertEqual(exact_difference(a,b).tolist(),[2.,3.]); self.assertAlmostEqual(frequency_convert([1.],"THz","cm^-1")[0],33.3564095)

    def test_difference_rejects_band_sampling_mismatch(self):
        from backend.analyze import AnalysisSeries, ComparisonModel, difference_eligible
        p=ResultProvenance("r","e","t","qe","pw.x",(),{},"f")
        a=ScientificResult("BandStructureResult",ResultStatus.VALID,p,arrays={"energies":[[1],[2]]})
        b=ScientificResult("BandStructureResult",ResultStatus.VALID,p,arrays={"energies":[[1],[2],[3]]})
        model=ComparisonModel("x","bands",[AnalysisSeries.from_result(a),AnalysisSeries.from_result(b)]).check(); self.assertFalse(difference_eligible(model)[0])

    def test_comparison_export_package(self):
        from backend.analyze import AnalysisSeries, ComparisonModel
        from backend.analyze.export import export_comparison
        p=ResultProvenance("r","e","t","qe","pw.x",(),{},"fixture")
        a=ScientificResult("DOSResult",ResultStatus.VALID,p,arrays={"energy":[0,1],"dos":[1,2]})
        model=ComparisonModel("x","dos",[AnalysisSeries.from_result(a,"PBE")]).check()
        with tempfile.TemporaryDirectory() as d:
            from pathlib import Path
            export_comparison(model,Path(d)); self.assertTrue((Path(d)/"comparison.json").is_file()); self.assertTrue((Path(d)/"series_01.csv").is_file())
