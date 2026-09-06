import tempfile
import unittest
from pathlib import Path
import numpy as np

import backend.calculations  # registers definitions
from backend.compiler.calculation_compiler import CalculationCompiler
from backend.core.calculation_request import CalculationRequest
from backend.engines.qe.writer import polar_phonon_input
from backend.results import DEFAULT_PARSERS, ResultStatus, ResultStore, ResultProvenance, ScientificResult
from frontend.analyze.workspace import AnalyzeWorkspace
from frontend.analyze.plots.vibrational import PolarTensorPlot
from frontend.core import Project
from PySide6.QtWidgets import QApplication

STRUCTURE={"atoms":[{"element":"X","x":0.0,"y":0.0,"z":0.0},{"element":"X","x":1.0,"y":1.0,"z":1.0}],"cell":[[3,0,0],[0,3,0],[0,0,3]],"periodic":[True,True,True]}
PARAMETERS={"xc_functional":"pbe","spin_treatment":"SCALAR_NONSPIN","occupations":"fixed","ecutwfc":60,"ecutrho":480,"kpoints":{"mode":"automatic","mesh":[6,6,6],"shifts":[0,0,0]},"pseudopotentials":{"X":"X.UPF"},"born_charges":{"tr2_ph":1e-12,"q_point":[0,0,0]}}

class PolarE3BTests(unittest.TestCase):
    def test_public_bec_expands_to_compatible_scf_and_private_polar_task(self):
        plan=CalculationCompiler(CalculationRequest(id="e3b",structure=STRUCTURE,selected_calculations=["born_charges"],parameters=PARAMETERS)).compile()
        self.assertEqual([task.semantic_task_type for task in plan.tasks],["scf","qe_polar_gamma"])
        task=plan.tasks[-1]
        self.assertEqual(task.depends_on_task_ids,(plan.tasks[0].id,))
        self.assertEqual(task.metadata["purpose"],"polar_gamma_dfpt")
        self.assertEqual(task.metadata["response_contract"],{"epsil":True,"zeu":True,"trans":True,"ldisp":False})

    def test_polar_writer_is_gamma_only_and_has_no_raman_flags(self):
        text=polar_phonon_input({"tr2_ph":1e-12,"q_point":[0,0,0],"fildyn":"polar_gamma"},type("C",(),{"prefix":"qs","outdir":"../qe_out"})())
        self.assertIn("epsil = .true.",text); self.assertIn("zeu = .true.",text); self.assertIn("trans = .true.",text); self.assertIn("ldisp = .false.",text)
        self.assertIn("0.0 0.0 0.0",text); self.assertNotIn("lraman",text); self.assertNotIn("elop",text); self.assertNotIn("nq1",text)

    def test_real_like_polar_xml_preserves_nonsymmetric_orientation_and_roundtrips(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); source=root/"polar_gamma.xml"
            source.write_text("""<ROOT><DIELECTRIC_PROPERTIES><EPSILON>2 0.1 0.2 0.3 3 0.4 0.5 0.6 4</EPSILON><ZSTAR><Z_AT_1>1 2 3 4 5 6 7 8 9</Z_AT_1><Z_AT_2>-1 -2 -3 -4 -5 -6 -7 -8 -9</Z_AT_2></ZSTAR></DIELECTRIC_PROPERTIES></ROOT>""")
            result=DEFAULT_PARSERS.parse("QE_POLAR_GAMMA",source,expected_atom_count=2,atom_elements=["X","X"])
            self.assertEqual(result.status,ResultStatus.VALID)
            expected=np.arange(1,10,dtype=float).reshape(3,3)
            np.testing.assert_array_equal(result.arrays["born_effective_charges"][0],expected)
            self.assertEqual(result.metadata["bec_convention"],"[atom, polarization Cartesian alpha, displacement Cartesian beta]")
            self.assertAlmostEqual(result.metadata["charge_sum_norm"],0.0)
            np.testing.assert_allclose(result.metadata["epsilon_infinity"],np.array([[2,.1,.2],[.3,3,.4],[.5,.6,4]]))
            store=ResultStore(root,"execution"); store.save(result); loaded=store.load(result.result_id)
            np.testing.assert_array_equal(loaded.arrays["born_effective_charges"],result.arrays["born_effective_charges"])
            self.assertEqual(loaded.metadata["bec_convention"],result.metadata["bec_convention"])

    def test_polar_analyze_uses_tensor_view_and_explicit_axes(self):
        QApplication.instance() or QApplication([])
        provenance=ResultProvenance("request","execution","polar","quantum_espresso","ph.x",(),{},"qe.ph.polar")
        result=ScientificResult("BornEffectiveChargeResult",ResultStatus.VALID,provenance,arrays={"born_effective_charges":np.arange(18,dtype=float).reshape(2,3,3),"charge_sum_residual":np.zeros((3,3))},metadata={"atom_elements":["Mg","O"],"charge_sum_norm":0.0,"bec_convention":"[atom, polarization Cartesian alpha, displacement Cartesian beta]"})
        workspace=AnalyzeWorkspace(Project("E3B Analyze")); workspace.current_result=result; workspace._show_plot()
        try:
            self.assertIsInstance(workspace.plot,PolarTensorPlot)
            self.assertEqual(workspace.plot.axes.get_xlabel(),"Displacement")
            self.assertEqual(workspace.plot.axes.get_ylabel(),"Polarization")
            self.assertEqual(workspace.plot.tensor_table.rowCount(),3)
            self.assertEqual(workspace.plot.tensor_table.columnCount(),3)
            self.assertEqual(workspace.plot.tensor_table.verticalHeaderItem(0).text(),"Polarization x")
            self.assertEqual(workspace.plot.tensor_table.horizontalHeaderItem(0).text(),"Displacement x")
            self.assertEqual(workspace.plot.tensor_table.item(0, 0).text(),"0.000000")
            workspace.plot.set_atom_index(1)
            self.assertEqual(workspace.plot.tensor_table.item(0, 0).text(),"9.000000")
            workspace._show_table(); self.assertEqual(workspace.table_model.rowCount(),18)
        finally: workspace.close()

    def test_polar_parser_rejects_incomplete_tensor(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/"polar.xml"; source.write_text("<ROOT><EPSILON>1 2</EPSILON></ROOT>")
            with self.assertRaises(Exception): DEFAULT_PARSERS.parse("QE_POLAR_GAMMA",source,expected_atom_count=1)

if __name__ == "__main__": unittest.main()
