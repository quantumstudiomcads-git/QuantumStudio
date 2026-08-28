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

class ProjectionClosureTests(unittest.TestCase):
    def test_lowdin_collinear_spin_rows_and_moments(self):
        from backend.results.derived import derive_magnetic_moments
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"projwfc.out"; p.write_text("""Lowdin Charges:
 Atom # 1: total charge = 3.8, s = 1.0, p = 2.8
               spin up = 2.1, s = 0.6, p = 1.5
               spin down = 1.7, s = 0.4, p = 1.3
               polarization = 0.4, s = 0.2, p = 0.2
""")
            low=parse_lowdin(p,species=["Fe"],expected_atom_count=1,method_metadata={"spin_treatment":"COLLINEAR_SPIN"})
            np.testing.assert_allclose(low.arrays["spin_difference"],[.2,.2])
            moment=derive_magnetic_moments(low)
            np.testing.assert_allclose(moment.arrays["projected_local_moment"],[.4])
    def test_orbital_projection_dimensions_and_labels(self):
        from backend.results.electronic import parse_orbital_projection
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"orbital.projwfc_up"; p.write_text("1 1 Si 3S 1 0 0\n 1 1 0.5\n 1 2 0.25\n")
            result=parse_orbital_projection(p)
            self.assertEqual(result.result_type,"OrbitalCharacterResult"); self.assertEqual(result.arrays["projection_weight"].shape,(2,)); self.assertEqual(result.metadata["projector_labels"],["3S","3S"])
    def test_projection_results_persist_with_numeric_arrays(self):
        from backend.results.models import ResultProvenance, ResultStatus, ScientificResult
        from backend.results.store import ResultStore
        provenance=ResultProvenance("request", "execution", "task", "qe", "projwfc.x", (), {}, "fixture")
        results=(
            ScientificResult("LowdinPopulationResult", ResultStatus.VALID, provenance,
                            arrays={"population": np.array([1.0, 2.0])}),
            ScientificResult("MagneticMomentResult", ResultStatus.VALID, provenance,
                            arrays={"projected_local_moment": np.array([2.5])}),
            ScientificResult("OrbitalCharacterResult", ResultStatus.VALID, provenance,
                            arrays={"projection_weight": np.array([0.2, 0.8]), "band_index": np.array([1, 2])}),
        )
        with tempfile.TemporaryDirectory() as d:
            store=ResultStore(d, "execution")
            for result in results: store.save(result)
            for result in results:
                loaded=store.load(result.result_id)
                self.assertEqual(loaded.result_type, result.result_type)
                for key, value in result.arrays.items(): np.testing.assert_allclose(loaded.arrays[key], value)

    def test_projection_plots_and_exports_are_nonempty(self):
        from backend.results.models import ResultProvenance, ResultStatus, ScientificResult
        from backend.analyze.export import export_csv
        from frontend.analyze.plots.projection import ProjectionPlot
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([]); p=ResultProvenance("r","e","t","qe","projwfc.x",(),{},"fixture")
        results=[ScientificResult("LowdinPopulationResult",ResultStatus.VALID,p,arrays={"atom_index":np.array([1,1]),"projector_index":np.array([1,2]),"l":np.array([0,1]),"population":np.array([1.,2.])},metadata={"species":["Si","Si"],"projector_labels":["s","p"]}), ScientificResult("MagneticMomentResult",ResultStatus.VALID,p,arrays={"atom_index":np.array([1]),"projected_local_moment":np.array([1.2])},metadata={"species":["Fe"]}), ScientificResult("OrbitalCharacterResult",ResultStatus.VALID,p,arrays={"k_index":np.array([1,2]),"band_index":np.array([1,1]),"energy_eV":np.array([-.5,-.4]),"projection_weight":np.array([.2,.8]),"atom_index":np.array([1,1]),"projector_index":np.array([1,1]),"l":np.array([0,0]),"m":np.array([0,0])},metadata={"species":["Si","Si"],"projector_labels":["3S","3S"]})]
        with tempfile.TemporaryDirectory() as d:
            for i,result in enumerate(results):
                w=ProjectionPlot(); w.set_result(result); self.assertTrue(w.axes.lines or w.axes.patches or w.axes.collections); self.assertGreater(export_csv(result,Path(d)/f"{i}.csv").stat().st_size,0); w.close()

class FermiAndBandChargeClosureTests(unittest.TestCase):
    def test_private_fermi_nscf_and_band_charge_tasks_are_adapter_supported(self):
        from backend.engines.qe.adapter import QuantumEspressoAdapter
        self.assertTrue(QuantumEspressoAdapter.is_supported("qe_pw_nscf_fermi_surface"))
        self.assertTrue(QuantumEspressoAdapter.is_supported("qe_pp_band_decomposed"))

    def test_fermi_surface_result_persists_grid_arrays(self):
        from backend.results.models import ResultProvenance, ResultStatus, ScientificResult
        from backend.results.store import ResultStore
        provenance=ResultProvenance("r", "e", "t", "qe", "fs.x", (), {}, "fixture")
        result=ScientificResult("FermiSurfaceResult", ResultStatus.VALID, provenance, arrays={"energies":np.arange(8.,dtype=float).reshape(1,2,2,2)}, metadata={"grid_dimensions":[2,2,2],"fermi_energy_eV":1.0})
        with tempfile.TemporaryDirectory() as d:
            store=ResultStore(d,"e"); store.save(result); loaded=store.load(result.result_id)
            np.testing.assert_array_equal(loaded.arrays["energies"], result.arrays["energies"])
            self.assertEqual(loaded.metadata["grid_dimensions"],[2,2,2])

    def test_band_decomposed_writer_uses_qe_plot_num_seven(self):
        from backend.engines.qe.postprocessing import post_input
        from backend.engines.qe.models import QEWorkflowContext
        text=post_input("qe_pp", {"plot_kind":"band_decomposed_charge","kpoint":2,"kband":3,"artifact":"state.cube"}, QEWorkflowContext("r","prefix","outdir","pseudos"))
        self.assertIn("plot_num = 7", text)
        self.assertIn("kpoint = 2", text)
        self.assertIn("kband = 3", text)

class QEProjectionHandoffTests(unittest.TestCase):
    def test_qe_projection_tasks_share_prefix_and_outdir_contract(self):
        from backend.core.calculation_request import CalculationRequest
        from backend.compiler.calculation_compiler import CalculationCompiler
        request=CalculationRequest(structure={'atoms':[],'cell':[],'periodic':[True,True,True]}, selected_calculations=['mulliken_population'], parameters={'postprocessing':True,'spin':True,'spin_treatment':'COLLINEAR_SPIN'})
        plan=CalculationCompiler(request).compile()
        # Adapter validation is intentionally skipped for the empty fixture; the
        # compiler contract still requires a single shared QE restart namespace.
        scf, proj=plan.tasks[0], plan.tasks[-1]
        self.assertEqual(scf.artifact_outputs, ('qe_charge_density','qe_save'))
        self.assertIn('qe_save', proj.artifact_inputs)
        self.assertEqual(proj.depends_on_task_ids, (scf.id,))

class ProjectionWorkflowTests(unittest.TestCase):
    def test_lowdin_and_magnetic_public_routes(self):
        from backend.core.calculation_request import CalculationRequest
        from backend.compiler.calculation_compiler import CalculationCompiler
        for cid, purpose in (("mulliken_population","lowdin_population"),("magnetic_moment","magnetic_moment")):
            plan=CalculationCompiler(CalculationRequest(structure={'atoms':[],'cell':[],'periodic':[True,True,True]},selected_calculations=[cid],parameters={'postprocessing':True})).compile()
            self.assertEqual(plan.tasks[-1].semantic_task_type,"qe_lowdin"); self.assertEqual(plan.tasks[-1].metadata["purpose"],purpose)
    def test_orbital_character_public_route_uses_path_and_projwfc(self):
        from backend.core.calculation_request import CalculationRequest
        from backend.compiler.calculation_compiler import CalculationCompiler
        path=[{'label':'G','coordinates':[0,0,0],'points':2},{'label':'X','coordinates':[.5,0,0],'points':2}]
        plan=CalculationCompiler(CalculationRequest(structure={'atoms':[],'cell':[],'periodic':[True,True,True]},selected_calculations=['orbital_texture'],parameters={'postprocessing':True,'kpath':path})).compile()
        self.assertEqual([t.semantic_task_type for t in plan.tasks],['scf','qe_pw_bands','qe_bands','qe_projwfc']); self.assertEqual(plan.tasks[-1].metadata['purpose'],'orbital_character')
