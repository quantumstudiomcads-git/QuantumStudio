import tempfile, unittest
from pathlib import Path
from backend.results import DEFAULT_PARSERS, ResultStatus

class ResultCoverageTests(unittest.TestCase):
 def test_relax_final_geometry_and_pdos_channels(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp); relax=root/"relax.out"; relax.write_text("! total energy = -1.0 Ry\nATOMIC_POSITIONS angstrom\nSi 0 0 0\n\n! total energy = -2.0 Ry\nCELL_PARAMETERS angstrom\n4 0 0\n0 4 0\n0 0 4\nATOMIC_POSITIONS angstrom\nSi 1 1 1\n\nconvergence has been achieved\n")
   result=DEFAULT_PARSERS.parse("QE_RELAX_STDOUT",relax); self.assertEqual(result.status,ResultStatus.VALID); self.assertEqual(result.metadata["final_structure"]["atoms"][0]["x"],1.0); self.assertTrue(result.metadata["vc_relax"])
   pdos=root/"pdos"; pdos.mkdir(); (pdos/"pdos_atm#1(Si)_wfc#1(s)").write_text("0 0 1\n1 1 2\n"); (pdos/"pdos_atm#2(O)_wfc#1(p)").write_text("0 0 3\n1 1 4\n")
   parsed=DEFAULT_PARSERS.parse("PDOS_RAW_DATA",pdos); self.assertEqual(len(parsed.metadata["components"]),2)
 def test_e2_dos_and_pdos_contracts_and_diagnostics(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp); dos=root/"dos.dat"; dos.write_text("# E (eV) dos(E) Int dos(E) EFermi = 1.25 eV\n-1 1 0\n0 2 1\n1 3 3\n")
   result=DEFAULT_PARSERS.parse("DOS_RAW_DATA",dos); self.assertEqual(result.status,ResultStatus.VALID); self.assertEqual(result.metadata["fermi_energy_eV"],1.25); self.assertEqual(result.metadata["normalization"],"PER_CELL"); self.assertEqual(result.arrays["integrated_dos"].tolist(),[0.,1.,3.])
   bad=root/"bad.dat"; bad.write_text("0 1\n0 2\n")
   with self.assertRaisesRegex(Exception,"strictly increasing"): DEFAULT_PARSERS.parse("DOS_RAW_DATA",bad)
   plain=root/"plain.dat"; plain.write_text("-1 1\n0 2\n")
   self.assertNotIn("fermi_energy_eV",DEFAULT_PARSERS.parse("DOS_RAW_DATA",plain).metadata)
   for name,text,diagnostic in (("empty.dat","","no numeric"),("wrong.dat","0 1 2 3\n1 2 3 4\n","requires E"),("nan.dat","0 nan\n1 2\n","non-finite"),("truncated.dat","0 1\n","strictly increasing")):
    candidate=root/name; candidate.write_text(text)
    with self.assertRaisesRegex(Exception,diagnostic): DEFAULT_PARSERS.parse("DOS_RAW_DATA",candidate)
   pdos=root/"pdos"; pdos.mkdir(); (pdos/"sample.pdos_atm#2(Si)_wfc#2(p)").write_text("# E ldos pdos m1 m2 m3\n-1 0 1 .1 .2 .3\n0 1 2 .4 .5 .6\n"); (pdos/"sample.pdos_atm#1(Si)_wfc#1(s)").write_text("# E ldos pdos\n-1 0 3\n0 1 4\n")
   parsed=DEFAULT_PARSERS.parse("PDOS_RAW_DATA",pdos); self.assertEqual(parsed.status,ResultStatus.VALID); self.assertEqual([item["label"] for item in parsed.metadata["components"]],["Si(1) — s","Si(2) — p"]); self.assertEqual(parsed.metadata["components"][1]["raw_component_columns"],3); self.assertEqual(parsed.metadata["component_values"][1],[1.0,2.0])
   (pdos/"sample.pdos_atm#3(Si)_wfc#1(s)").write_text("-1 0 1\n.1 1 2\n")
   with self.assertRaisesRegex(Exception,"grids are incompatible"): DEFAULT_PARSERS.parse("PDOS_RAW_DATA",pdos)

 def test_wannier_and_epw_are_conservative(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp); w=root/"x.wout"; w.write_text("Number of Wannier Functions : 4\nFinal State Spread 2.5\nAll done\n"); self.assertEqual(DEFAULT_PARSERS.parse("WANNIER_WOUT",w).status,ResultStatus.VALID)
   e=root/"epw.out"; e.write_text("EPW completed\n"); result=DEFAULT_PARSERS.parse("EPW_SUMMARY",e); self.assertEqual(result.status,ResultStatus.UNVERIFIED); self.assertNotIn("lambda",result.scalars)
