import unittest
import backend.calculations
from backend.core.calculation_request import CalculationRequest
from backend.compiler.calculation_compiler import CalculationCompiler
from backend.engines.epw.adapter import EPWWorkflowAdapter
S={'atoms':[{'element':'C','x':0,'y':0,'z':0}],'cell':[[2,0,0],[0,2,0],[0,0,10]],'periodic':[True,True,False]}
P={'pseudopotentials':{'C':'C.UPF'},'num_wann':2,'num_bands':4,'projections':['C:pz'],'mp_grid':[2,2,1],'kpoints':[2,2,1],'nk_coarse':[2,2,1],'nq_coarse':[1,1,1],'nk_fine':[4,4,1],'nq_fine':[2,2,1]}
class EPWTests(unittest.TestCase):
 def test_dag_artifacts_and_inputs(self):
  plan=CalculationCompiler(CalculationRequest(structure=S,selected_calculations=['electron_phonon'],parameters=P)).compile(); ts={t.semantic_task_type:t for t in plan.tasks}; self.assertEqual(ts['epw_run'].depends_on_task_ids,(ts['wannier90_run'].id,ts['qe_ph_epw'].id)); self.assertIn('qe_dvscf',ts['epw_run'].artifact_inputs)
  out={t.calculation_id:t for t in EPWWorkflowAdapter().compile_plan(plan)}; self.assertIn("elph = .true.",out['epw_run'].input_text); self.assertIn("wannierize = .false.",out['epw_run'].input_text); self.assertIn("calculation = 'nscf'",out['qe_pw_nscf'].input_text)
 def test_mesh_mismatch_fails(self):
  p=dict(P); p['nk_coarse']=[3,2,1]
  with self.assertRaisesRegex(Exception,'mp_grid'): CalculationCompiler(CalculationRequest(structure=S,selected_calculations=['electron_phonon'],parameters=p)).compile()
if __name__=='__main__': unittest.main()
