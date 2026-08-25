import tempfile, unittest
from pathlib import Path
from backend.results import DEFAULT_PARSERS, ResultStatus

class ResultCoverageTests(unittest.TestCase):
 def test_relax_final_geometry_and_pdos_channels(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp); relax=root/"relax.out"; relax.write_text("! total energy = -1.0 Ry\nATOMIC_POSITIONS angstrom\nSi 0 0 0\n\n! total energy = -2.0 Ry\nCELL_PARAMETERS angstrom\n4 0 0\n0 4 0\n0 0 4\nATOMIC_POSITIONS angstrom\nSi 1 1 1\n\nconvergence has been achieved\n")
   result=DEFAULT_PARSERS.parse("QE_RELAX_STDOUT",relax); self.assertEqual(result.status,ResultStatus.VALID); self.assertEqual(result.metadata["final_structure"]["atoms"][0]["x"],1.0); self.assertTrue(result.metadata["vc_relax"])
   pdos=root/"pdos"; pdos.mkdir(); (pdos/"pdos_atm#1(Si)_wfc#1(s)").write_text("0 1\n1 2\n"); (pdos/"pdos_atm#2(O)_wfc#1(p)").write_text("0 3\n1 4\n")
   parsed=DEFAULT_PARSERS.parse("PDOS_RAW_DATA",pdos); self.assertEqual(len(parsed.metadata["components"]),2)
 def test_wannier_and_epw_are_conservative(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp); w=root/"x.wout"; w.write_text("Number of Wannier Functions : 4\nFinal State Spread 2.5\nAll done\n"); self.assertEqual(DEFAULT_PARSERS.parse("WANNIER_WOUT",w).status,ResultStatus.VALID)
   e=root/"epw.out"; e.write_text("EPW completed\n"); result=DEFAULT_PARSERS.parse("EPW_SUMMARY",e); self.assertEqual(result.status,ResultStatus.UNVERIFIED); self.assertNotIn("lambda",result.scalars)
