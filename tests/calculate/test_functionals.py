import unittest
from backend.dft.functionals import resolve, hybrid_capability
from backend.engines.qe.writer import pw_input
from backend.engines.qe.models import QEWorkflowContext, PseudopotentialSelection
S={"periodic":[True,True,True],"cell":[[3,0,0],[0,3,0],[0,0,3]],"atoms":[{"element":"Si","x":0,"y":0,"z":0}]}
C=QEWorkflowContext("r","p","./out","./pseudos")
P={"Si":PseudopotentialSelection("Si","Si.UPF")}
class FunctionalTests(unittest.TestCase):
 def test_exact_mappings_and_hybrid_writer(self):
  self.assertEqual([resolve(x).qe_input_dft for x in ("pz","pbe","pw91","blyp","hse06","b3lyp")],["PZ","PBE","PW91","BLYP","HSE","B3LYP"])
  with self.assertRaises(ValueError): resolve("gga")
  h=pw_input("scf",{"xc_functional":"hse06","kpoints":{"mesh":[4,4,1]},"ecutwfc":60,"ecutrho":480},S,C,P); self.assertIn("input_dft = 'HSE'",h); self.assertIn("exx_fraction = 0.25",h); self.assertIn("screening_parameter = 0.106",h); self.assertIn("ace = .true.",h); self.assertIn("nqx3 = 1",h)
  b=pw_input("scf",{"xc_functional":"b3lyp","kpoints":{"mesh":[2,2,1]}},S,C,P); self.assertIn("input_dft = 'B3LYP'",b); self.assertNotIn("screening_parameter",b)
 def test_hybrid_capability_gate(self):
  self.assertEqual(hybrid_capability("hse06",["phonons"]),"UNSUPPORTED_BY_QE_PHONON"); self.assertEqual(hybrid_capability("hse06",["dos"]),"NOT_YET_IMPLEMENTED")
