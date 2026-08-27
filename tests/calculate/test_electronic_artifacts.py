import tempfile
import unittest
from pathlib import Path
import numpy as np
from backend.results.electronic import parse_bxsf, parse_bader_acf, parse_lowdin, parse_hubbard_parameters

class ElectronicArtifactTests(unittest.TestCase):
    def test_qe_bxsf_parser_preserves_grid_and_crossing_band(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"al_fs.bxsf"
            path.write_text("""BEGIN_INFO
 Fermi Energy:    0.5000
END_INFO
BEGIN_BLOCK_BANDGRID_3D
 band_energies
 BANDGRID_3D_BANDS
 1
 2 1 1
 0 0 0
 1 0 0
 0 1 0
 0 0 1
 BAND: 1
 0.1 0.9
 END_BANDGRID_3D
 END_BLOCK_BANDGRID_3D
""")
            result=parse_bxsf(path)
            self.assertEqual(result.result_type, "FermiSurfaceResult")
            self.assertEqual(result.arrays["energies"].shape, (1,2,1,1))
            self.assertEqual(result.metadata["bands_crossing_fermi"], [1])
            self.assertTrue(np.isfinite(result.arrays["energies"]).all())

    def test_bader_parser_uses_pseudovalence_charge_sign(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"ACF.dat"
            path.write_text(" 1 0 0 0 3.5 0.2 10.0\n 2 1 1 1 4.5 0.3 11.0\n")
            result=parse_bader_acf(path,species=["Si","Si"],z_valence=[4,4])
            np.testing.assert_allclose(result.arrays["net_charge"],[0.5,-0.5])
            self.assertEqual(result.metadata["source_density"], "pseudo-valence charge density")

    def test_lowdin_parser_keeps_projected_populations_unnormalized(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"projwfc.out"
            path.write_text(" Atom # 1 (Si): total charge = 3.20\n Atom # 2 (Si): Lowdin charge = 3.10\n")
            result=parse_lowdin(path)
            self.assertEqual(result.result_type, "LowdinPopulationResult")
            np.testing.assert_allclose(result.arrays["population"],[3.2,3.1])
            self.assertTrue(result.metadata["basis_incompleteness"])

if __name__ == "__main__":
    unittest.main()

class ElectronicWorkflowTests(unittest.TestCase):
    def test_fermi_surface_expands_uniform_nscf_and_fs(self):
        from backend.core.calculation_request import CalculationRequest
        from backend.compiler.calculation_compiler import CalculationCompiler
        request=CalculationRequest(structure={'atoms':[],'cell':[],'periodic':[True,True,True]}, selected_calculations=['fermi_surface'], parameters={'postprocessing':True,'fermi_surface':{'mesh':[4,4,4]}})
        plan=CalculationCompiler(request).compile()
        self.assertEqual([task.semantic_task_type for task in plan.tasks],['scf','qe_pw_nscf','qe_fs'])
        self.assertEqual(plan.tasks[-1].tool_id,'fs.x')
        self.assertEqual(plan.tasks[-1].metadata['result_type'],'FermiSurfaceResult')

    def test_hubbard_u_expands_to_hp(self):
        from backend.core.calculation_request import CalculationRequest
        from backend.compiler.calculation_compiler import CalculationCompiler
        request=CalculationRequest(structure={'atoms':[],'cell':[],'periodic':[True,True,True]}, selected_calculations=['hubbard_u'], parameters={'postprocessing':True,'hubbard_u':{'qmesh':[2,2,2]}})
        plan=CalculationCompiler(request).compile()
        self.assertEqual(plan.tasks[-1].semantic_task_type,'qe_hp')
        self.assertEqual(plan.tasks[-1].tool_id,'hp.x')

class DerivedElectronicResultTests(unittest.TestCase):
    def _bands(self):
        from backend.results.models import ScientificResult, ResultStatus, ResultProvenance
        import numpy as np
        return ScientificResult("BandStructureResult", ResultStatus.VALID, ResultProvenance("r","e","t","qe","bands.x",(),{},"fixture"), arrays={"path_coordinate":np.arange(5.),"energies":np.array([[-1.,1.],[-.8,1.2],[-.6,1.5],[-.8,1.2],[-1.,1.]])}, metadata={"occupied_band_count":1,"kpoints":[[0,0,0],[.1,0,0],[.2,0,0],[.3,0,0],[.4,0,0]],"cell":[[5,0,0],[0,5,0],[0,0,5]]})
    def test_band_gap_and_effective_mass_are_structured_derived_results(self):
        from backend.results.derived import derive_band_gap, derive_effective_mass
        source=self._bands(); gap=derive_band_gap(source); mass=derive_effective_mass(source,fit_points=3)
        self.assertEqual(gap.result_type,"BandGapResult")
        self.assertIn("sampled_gap",gap.scalars)
        self.assertEqual(mass.result_type,"EffectiveMassResult")
        self.assertIn(mass.status.value,{"VALID","PARTIAL"})


class HubbardArtifactTests(unittest.TestCase):
    def test_hp_final_u_table_parser(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"hp.out"
            path.write_text(" Hubbard U parameters:\n site n. type label spin new_type new_label manifold Hubbard U (eV)\n   1      1   Fe    1      1        Fe       3d     3.0000\n =-------------------------------------------------------------------------------=\n")
            result=parse_hubbard_parameters(path)
            self.assertEqual(result.result_type,"HubbardParameterResult")
            np.testing.assert_allclose(result.arrays["U_eV"],[3.0])

class DerivedPresentationTests(unittest.TestCase):
    def test_derived_results_export_nonempty(self):
        from backend.results.derived import derive_band_gap, derive_effective_mass
        from backend.analyze.export import export_csv
        source=DerivedElectronicResultTests()._bands()
        with tempfile.TemporaryDirectory() as d:
            for result,name in ((derive_band_gap(source),'gap.csv'),(derive_effective_mass(source,fit_points=3),'mass.csv')):
                target=export_csv(result,Path(d)/name)
                self.assertGreater(target.stat().st_size,0)
    def test_derived_plot_has_finite_artists(self):
        from PySide6.QtWidgets import QApplication
        from backend.results.derived import derive_band_gap, derive_effective_mass
        from frontend.analyze.plots.derived_electronic import DerivedElectronicPlot
        source=DerivedElectronicResultTests()._bands(); application=QApplication.instance() or QApplication([])
        for result in (derive_band_gap(source),derive_effective_mass(source,fit_points=3)):
            plot=DerivedElectronicPlot(); plot.set_result(result); application.processEvents()
            self.assertTrue(plot.axes.lines or plot.axes.collections)
            plot.close()

class BaderClosureTests(unittest.TestCase):
    def test_bader_parser_rejects_malformed_and_count_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"ACF.dat"; path.write_text("1 0 0 0 bad 0.2 1.0\n")
            with self.assertRaises(ValueError): parse_bader_acf(path, expected_atom_count=1)
            path.write_text("1 0 0 0 3.5 0.2 1.0\n")
            with self.assertRaises(ValueError): parse_bader_acf(path, expected_atom_count=2)
    def test_bader_result_and_charge_transfer_export(self):
        from backend.results.derived import derive_charge_transfer
        from backend.analyze.export import export_csv
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"ACF.dat"; path.write_text("1 0 0 0 3.5 0.2 1.0\n2 1 1 1 4.5 0.3 1.1\n")
            bader=parse_bader_acf(path,species=["Si","Si"],z_valence=[4,4]); transfer=derive_charge_transfer(bader)
            np.testing.assert_allclose(transfer.arrays["charge_transfer"],bader.arrays["net_charge"])
            self.assertAlmostEqual(bader.metadata["charge_conservation_difference"],0.0)
            self.assertGreater(export_csv(bader,Path(d)/"bader.csv").stat().st_size,0)
            self.assertGreater(export_csv(transfer,Path(d)/"transfer.csv").stat().st_size,0)
    def test_charge_transfer_compiles_without_duplicate_bader(self):
        from backend.core.calculation_request import CalculationRequest
        from backend.compiler.calculation_compiler import CalculationCompiler
        request=CalculationRequest(structure={'atoms':[],'cell':[],'periodic':[True,True,True]}, selected_calculations=['charge_transfer'], parameters={'postprocessing':True})
        plan=CalculationCompiler(request).compile(); ids=[task.calculation_id for task in plan.tasks]
        self.assertEqual(ids.count('qe_bader'),1); self.assertEqual(ids.count('qe_pp_bader'),1)
