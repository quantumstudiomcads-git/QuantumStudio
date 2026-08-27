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
   soc=DEFAULT_PARSERS.parse("DOS_RAW_DATA",plain,method_metadata={"spin_treatment":"SOC"}); self.assertEqual(soc.metadata["spin_semantics"],"SOC"); self.assertIn("dos",soc.arrays); self.assertNotIn("dos_up",soc.arrays)
   for name,text,diagnostic in (("empty.dat","","no numeric"),("wrong.dat","0 1 2 3\n1 2 3 4\n","requires E"),("nan.dat","0 nan\n1 2\n","non-finite"),("truncated.dat","0 1\n","strictly increasing")):
    candidate=root/name; candidate.write_text(text)
    with self.assertRaisesRegex(Exception,diagnostic): DEFAULT_PARSERS.parse("DOS_RAW_DATA",candidate)
   pdos=root/"pdos"; pdos.mkdir(); (pdos/"sample.pdos_atm#2(Si)_wfc#2(p)").write_text("# E ldos pdos m1 m2 m3\n-1 0 1 .1 .2 .3\n0 1 2 .4 .5 .6\n"); (pdos/"sample.pdos_atm#1(Si)_wfc#1(s)").write_text("# E ldos pdos\n-1 0 3\n0 1 4\n")
   parsed=DEFAULT_PARSERS.parse("PDOS_RAW_DATA",pdos); self.assertEqual(parsed.status,ResultStatus.VALID); self.assertEqual([item["label"] for item in parsed.metadata["components"]],["Si(1) — s","Si(2) — p"]); self.assertEqual(parsed.metadata["components"][1]["raw_component_columns"],3); self.assertEqual(parsed.metadata["component_values"][1],[1.0,2.0])
   (pdos/"sample.pdos_atm#3(Si)_wfc#1(s)").write_text("-1 0 1\n.1 1 2\n")
   with self.assertRaisesRegex(Exception,"grids are incompatible"): DEFAULT_PARSERS.parse("PDOS_RAW_DATA",pdos)

 def test_e3_real_format_collinear_dos_and_pdos(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp); dos=root/"fe.dos"; dos.write_text("# E (eV) dosup(E) dosdw(E) Int dos(E) EFermi = 7.174 eV\n-1 1 2 3\n0 4 5 6\n")
   method={"spin_treatment":"COLLINEAR_SPIN"}; result=DEFAULT_PARSERS.parse("DOS_RAW_DATA",dos,method_metadata=method)
   self.assertEqual(result.metadata["spin_semantics"],"COLLINEAR_SPIN"); self.assertEqual(result.arrays["dos_up"].tolist(),[1.,4.]); self.assertEqual(result.arrays["dos_down"].tolist(),[2.,5.]); self.assertEqual(result.scalars["fermi_energy"]["value"],7.174)
   pdos=root/"pdos"; pdos.mkdir(); (pdos/"fe.pdos_atm#1(Fe)_wfc#5(d)").write_text("# E ldosup ldosdw pdosup pdosdw m1u m1d\n-1 10 20 1 2 .1 .2\n0 11 21 3 4 .3 .4\n")
   projected=DEFAULT_PARSERS.parse("PDOS_RAW_DATA",pdos,method_metadata=method)
   self.assertEqual([(c["orbital"],c["spin"]) for c in projected.metadata["components"]],[("d","UP"),("d","DOWN")]); self.assertEqual(projected.metadata["component_values"],[[1.0,3.0],[2.0,4.0]])

 def test_wannier_and_epw_are_conservative(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp); w=root/"x.wout"; w.write_text("Number of Wannier Functions : 4\nFinal State Spread 2.5\nAll done\n"); self.assertEqual(DEFAULT_PARSERS.parse("WANNIER_WOUT",w).status,ResultStatus.VALID)
   e=root/"epw.out"; e.write_text("EPW completed\n"); result=DEFAULT_PARSERS.parse("EPW_SUMMARY",e); self.assertEqual(result.status,ResultStatus.UNVERIFIED); self.assertNotIn("lambda",result.scalars)

 def test_relax_convergence_force_and_wannier_centres(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp); relax=root/"unfinished.out"; relax.write_text("! total energy = -1.0 Ry\nATOMIC_POSITIONS angstrom\nSi 0 0 0\n\nTotal force = 0.0012\nJOB DONE.\n")
   parsed=DEFAULT_PARSERS.parse("QE_RELAX_STDOUT",relax); self.assertEqual(parsed.status,ResultStatus.NOT_CONVERGED); self.assertEqual(parsed.scalars["final_total_force"]["unit"],"Ry per bohr")
   w=root/"seed.wout"; w.write_text("Number of Wannier Functions : 2\nWF centre and spread 1 ( 0.0, 1.0, 2.0 ) 0.5\nWF centre and spread 2 ( 3.0, 4.0, 5.0 ) 0.7\nFinal State Spread 1.2\nAll done\n"); (root/"seed_hr.dat").write_text("header\n2\n5\n")
   wannier=DEFAULT_PARSERS.parse("WANNIER_WOUT",w); self.assertEqual(wannier.arrays["centres_A"].shape,(2,3)); self.assertEqual(wannier.metadata["hr"]["num_rpoints"],5)

 def test_wannier_result_source_prefers_wout_artifact(self):
  from frontend.services.result_service import ResultService
  from types import SimpleNamespace
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp); task=root/"run"; task.mkdir(); (task/"seed.wout").write_text("All done\n")
   source=ResultService()._source(root,{"working_directory":"run"},SimpleNamespace(stdout_path=""),"wannier90_run"); self.assertEqual(source.name,"seed.wout")
