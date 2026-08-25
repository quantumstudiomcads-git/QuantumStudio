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

    def test_sampled_gap_direct_indirect_and_unresolved(self):
        from backend.analyze.electronic import analyze_band_edges
        p=ResultProvenance("r","e","t","qe","bands.x",(),{},"fixture")
        r=ScientificResult("BandStructureResult",ResultStatus.VALID,p,arrays={"energies":[[0,4],[1,3]]},metadata={"occupied_band_count":1,"kpoints":[[0,0,0],[.5,0,0]]})
        a=analyze_band_edges(r); self.assertEqual(a.status,"VALID"); self.assertEqual(a.classification,"DIRECT_SAMPLED_PATH")
        unknown=ScientificResult("BandStructureResult",ResultStatus.VALID,p,arrays={"energies":[[0,2],[1,3]]})
        self.assertEqual(analyze_band_edges(unknown).status,"UNRESOLVED_OCCUPANCY")

    def test_effective_mass_requires_cell_and_returns_diagnostic(self):
        from backend.analyze.electronic import fit_effective_mass, BandEdge
        p=ResultProvenance("r","e","t","qe","bands.x",(),{},"fixture")
        r=ScientificResult("BandStructureResult",ResultStatus.VALID,p,arrays={"energies":[[0,1],[.1,1],[.4,1]],"kpoints":[[0,0,0],[.01,0,0],[.02,0,0]]},metadata={"cell":[[10,0,0],[0,10,0],[0,0,10]]})
        fit=fit_effective_mass(r,BandEdge(.0,0,0),points_each_side=2); self.assertIn(fit.status,{"VALID","INSUFFICIENT_POINTS"})


    def test_a7_repeated_gamma_and_degenerate_edges(self):
        from backend.analyze.electronic import analyze_band_edges
        p=ResultProvenance("r","e","t","qe","bands.x",(),{},"fixture")
        result=ScientificResult("BandStructureResult",ResultStatus.VALID,p,
            arrays={"energies":[[1,3],[1,4],[0,2]],"kpoints":[[0,0,0],[.5,0,0],[1,0,0]]},
            metadata={"occupied_band_count":1,"path_labels":{0:"Γ",1:"X",2:"Γ"}})
        analysis=analyze_band_edges(result)
        self.assertEqual(analysis.classification,"DIRECT_SAMPLED_PATH")
        self.assertEqual(len(analysis.degenerate_vbm),2)

    def test_a7_effective_mass_direction_and_preview_samples(self):
        from backend.analyze.electronic import BandEdge, available_fit_directions, fit_effective_mass
        p=ResultProvenance("r","e","t","qe","bands.x",(),{},"fixture")
        # Endpoint gives a one-sided fit; the stored physical k points, never plot index,
        # provide the independent coordinate.
        result=ScientificResult("BandStructureResult",ResultStatus.VALID,p,
            arrays={"energies":[[0.0],[0.01],[0.04],[0.09]],"kpoints":[[0,0,0],[.01,0,0],[.02,0,0],[.03,0,0]]},
            metadata={"cell":[[10,0,0],[0,10,0],[0,0,10]],"path_labels":{0:"Γ"}})
        edge=BandEdge(0.0,0,0,label="Γ"); direction=available_fit_directions(result,edge)[0]
        fit=fit_effective_mass(result,edge,carrier="CBM",direction=direction,points_each_side=3)
        self.assertEqual(fit.status,"VALID"); self.assertGreater(fit.mass_me,0); self.assertEqual(len(fit.sample_energies),3); self.assertEqual(len(fit.fitted_energies),3)

    def test_a7_derived_comparison_and_explicit_strain_trend(self):
        from backend.analyze import AnalysisSeries
        from backend.analyze.electronic import derived_comparison_rows, strain_gap_trend
        p=ResultProvenance("r","e","t","qe","bands.x",(),{},"fixture")
        def result(name,strain,gap):
            return ScientificResult("BandStructureResult",ResultStatus.VALID,ResultProvenance(name,"e"+name,"t","qe","bands.x",(),{},"fixture"),
                arrays={"energies":[[0,gap],[0,gap]],"kpoints":[[0,0,0],[0,0,0]]},metadata={"occupied_band_count":1,"strain":strain,"functional":name})
        a,b=result("PBE",-2,.34),result("HSE06",2,.76)
        rows,delta,warning=derived_comparison_rows([AnalysisSeries.from_result(a,"PBE"),AnalysisSeries.from_result(b,"HSE06")])
        self.assertEqual(len(rows),2); self.assertAlmostEqual(delta,.42); self.assertIsNone(warning)
        points,warnings=strain_gap_trend([AnalysisSeries.from_result(b,"HSE06"),AnalysisSeries.from_result(a,"PBE")])
        self.assertEqual([point["strain_percent"] for point in points],[-2.0,2.0]); self.assertEqual(warnings,())

    def test_a7_band_markers_use_edge_candidates(self):
        from frontend.analyze.plots.bands import BandPlot
        from backend.analyze.electronic import analyze_band_edges
        app=QApplication.instance() or QApplication([])
        p=ResultProvenance("r","e","t","qe","bands.x",(),{},"fixture")
        result=ScientificResult("BandStructureResult",ResultStatus.VALID,p,arrays={"path_coordinate":[0,1],"energies":[[0,2],[0,3]],"kpoints":[[0,0,0],[.5,0,0]]},metadata={"occupied_band_count":1})
        plot=BandPlot(); analysis=analyze_band_edges(result); plot.configure_electronic_analysis(analysis,show_edges=True); plot.set_result(result); app.processEvents()
        self.assertGreaterEqual(len(plot.axes.collections),len(analysis.degenerate_vbm)+len(analysis.degenerate_cbm)); plot.close()
