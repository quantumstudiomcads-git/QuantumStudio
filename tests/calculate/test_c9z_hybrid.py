import os, unittest
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from backend.compiler.calculation_compiler import CalculationCompiler
from backend.core.calculation_request import CalculationRequest
from backend.engines.qe import QuantumEspressoAdapter
from backend.engines.qe.hybrid_bands import hybrid_band_contract
from frontend.calculate.functional_pseudo_dialog import FunctionalPseudoDialog

S={"periodic":[True,True,True],"cell":[[3,0,0],[0,3,0],[0,0,3]],"atoms":[{"element":"Si","x":0,"y":0,"z":0}]}
PATH=[{"label":"G","coordinates":[0,0,0],"points":2},{"label":"X","coordinates":[.5,0,0],"points":2}]
class C9ZTests(unittest.TestCase):
 def test_hybrid_contract_and_dag(self):
  contract=hybrid_band_contract(PATH,[2,1,1],[True,True,True]); self.assertEqual(len(contract["visible_points"]),3); self.assertEqual(len(contract["exx_support_points"]),6); self.assertEqual(contract["exx_support_points"][3],(.5,0.,0.))
  request=CalculationRequest(S,["bands"],parameters={"postprocessing":True,"xc_functional":"hse06","kpath":PATH,"exx_q_mesh":[2,1,1],"soc":True,"pseudopotentials":{"Si":"Si.UPF"}}); plan=CalculationCompiler(request).compile(); self.assertEqual([task.semantic_task_type for task in plan.tasks],["scf","qe_bands"]); generated=QuantumEspressoAdapter().compile_plan(plan); text=generated.tasks[0].input_text; self.assertIn("input_dft = 'HSE'",text); self.assertIn("ADDITIONAL_K_POINTS crystal\n",text); self.assertEqual(text.count("K_POINTS automatic"),1); self.assertNotIn("calculation = 'bands'",text); self.assertIn("noncolin = .true.",text); self.assertIn("lspinorb = .true.",text); self.assertEqual(generated.tasks[0].metadata["task_metadata"]["hybrid_band"]["method"],"direct_exx_additional_k_points")
 def test_b3lyp_and_hybrid_blocks(self):
  request=CalculationRequest(S,["bands"],parameters={"postprocessing":True,"xc_functional":"b3lyp","kpath":PATH,"exx_q_mesh":[1,1,1],"pseudopotentials":{"Si":"Si.UPF"}}); text=QuantumEspressoAdapter().compile_plan(CalculationCompiler(request).compile()).tasks[0].input_text; self.assertIn("input_dft = 'B3LYP'",text); self.assertNotIn("screening_parameter",text)
  with self.assertRaisesRegex(ValueError,"ph.x"): CalculationCompiler(CalculationRequest(S,["phonons"],parameters={"xc_functional":"hse06"})).compile()
 def test_functional_dialog(self):
  app=QApplication.instance() or QApplication([]); dialog=FunctionalPseudoDialog({"xc_functional":"hse06","kpoints":[4,4,1]},["Si"]); self.assertEqual(dialog.family.currentText(),"Hybrid"); self.assertEqual(dialog.functional.currentData(),"hse06"); values=dialog.values(); self.assertEqual(values["exx_fraction"],.25); self.assertEqual(values["screening_parameter"],.106); dialog.family.setCurrentText("GGA"); self.assertEqual({dialog.functional.itemData(i) for i in range(dialog.functional.count())},{"pbe","pw91","blyp"})
