from __future__ import annotations
import json, tempfile, unittest
from pathlib import Path
import backend.calculations
from backend.compiler.calculation_compiler import CalculationCompiler
from backend.core.calculation_request import CalculationRequest
from backend.engines.wannier90 import Wannier90WorkflowAdapter, WannierInputError

STRUCTURE={"atoms":[{"element":"C","x":0.,"y":0.,"z":0.}],"cell":[[2.46,0,0],[0,2.46,0],[0,0,15]],"periodic":[True,True,True]}
PARAMS={"pseudopotentials":{"C":"C.UPF"},"num_wann":4,"num_bands":8,"projections":["C:pz"],"mp_grid":[2,2,1],"dis_win_min":-8,"dis_win_max":8,"spinors":True}
def plan(structure=STRUCTURE, params=PARAMS):
 return CalculationCompiler(CalculationRequest(id="w90-test",structure=structure,selected_calculations=["wannierization"],parameters=params)).compile()
class WannierWorkflowTests(unittest.TestCase):
 def test_private_cross_engine_dag_signatures_and_artifacts(self):
  result=plan(); self.assertEqual([t.semantic_task_type for t in result.tasks],["scf","qe_pw_nscf","wannier90_preprocess","qe_pw2wannier90","wannier90_run"])
  scf,nscf,pp,pw2,run=result.tasks
  self.assertEqual(nscf.depends_on_task_ids,(scf.id,)); self.assertIn("qe_wavefunctions",nscf.artifact_outputs)
  self.assertEqual(pp.depends_on_task_ids,(nscf.id,)); self.assertIn("wannier_nnkp",pp.artifact_outputs)
  self.assertEqual(pw2.depends_on_task_ids,(nscf.id,pp.id)); self.assertIn("wannier_mmn",pw2.artifact_outputs)
  self.assertEqual(run.depends_on_task_ids,(pp.id,pw2.id)); self.assertIn("wannier_hr",run.artifact_outputs)
  self.assertNotEqual(nscf.parameter_signature, "")
 def test_input_text_mesh_geometry_and_pw2_contract(self):
  tasks, manifest=Wannier90WorkflowAdapter().compile_plan(plan()); by={t.calculation_id:t for t in tasks}
  self.assertIn("calculation = 'nscf'",by["qe_pw_nscf"].input_text); self.assertIn("nbnd = 8",by["qe_pw_nscf"].input_text); self.assertIn("K_POINTS automatic\n2 2 1 0 0 0",by["qe_pw_nscf"].input_text)
  self.assertIn("mp_grid = 2 2 1",by["wannier90_preprocess"].input_text); self.assertIn("begin kpoints",by["wannier90_preprocess"].input_text); self.assertIn("C 0 0 0",by["wannier90_preprocess"].input_text)
  self.assertIn("write_amn = .true.",by["qe_pw2wannier90"].input_text); self.assertEqual(manifest["tasks"][-1]["engine_id"],"wannier90")
 def test_validation_determinism_persistence_and_snapshot(self):
  bad=dict(PARAMS); bad.pop("projections")
  with self.assertRaises(WannierInputError): plan(params=bad)
  original=plan(); restored=CalculationCompiler(CalculationRequest.from_persistence_dict(CalculationRequest(id="w90-test",structure=STRUCTURE,selected_calculations=["wannierization"],parameters=PARAMS).to_persistence_dict())).compile()
  first,_=Wannier90WorkflowAdapter().compile_plan(original); second,_=Wannier90WorkflowAdapter().compile_plan(restored); self.assertEqual([x.input_text for x in first],[x.input_text for x in second])
  changed=json.loads(json.dumps(STRUCTURE)); changed["atoms"][0]["x"]=99; self.assertNotIn("99",first[0].input_text)
  with tempfile.TemporaryDirectory() as tmp:
   output=Wannier90WorkflowAdapter().write_plan(original,tmp); self.assertTrue((output/"005_wannier90_run").exists()); self.assertTrue((output/"manifest.json").exists())
 def test_nscf_signature_changes_with_wannier_mesh(self):
  first=next(t for t in plan().tasks if t.semantic_task_type=="qe_pw_nscf")
  alternative=dict(PARAMS); alternative["mp_grid"]=[3,2,1]
  second=next(t for t in plan(params=alternative).tasks if t.semantic_task_type=="qe_pw_nscf")
  self.assertNotEqual(first.parameter_signature,second.parameter_signature)
  first_inputs,_=Wannier90WorkflowAdapter().compile_plan(plan())
  win=next(t.input_text for t in first_inputs if t.calculation_id=="wannier90_preprocess")
  self.assertEqual(win.split("begin kpoints\n",1)[1].split("end kpoints",1)[0].strip().splitlines(),["0 0 0","0 0.5 0","0.5 0 0","0.5 0.5 0"])

if __name__=="__main__": unittest.main()
