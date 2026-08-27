import tempfile, unittest
from pathlib import Path
from backend.results import DEFAULT_PARSERS, ResultStatus, ResultStore

SCF="""!    total energy              =   -10.00000000 Ry
     the Fermi energy is    5.4321 ev
     total magnetization       =     1.00
     convergence has been achieved
     JOB DONE.
"""

class ResultTests(unittest.TestCase):
 def test_scf_status_provenance_and_store_arrays(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp); raw=root/"scf.out"; raw.write_text(SCF)
   result=DEFAULT_PARSERS.parse("QE_SCF_STDOUT",raw,request_id="r",execution_id="e",task_id="scf")
   self.assertEqual(result.status,ResultStatus.VALID); self.assertAlmostEqual(result.scalars["total_energy"]["value"],-136.05693122994)
   workflow=root/"workflow"; workflow.mkdir(); store=ResultStore(workflow,"e"); store.save(result); loaded=store.load(result.result_id); self.assertEqual(loaded.provenance.execution_id,"e"); self.assertEqual(loaded.metadata["contract_version"],"v0.21-e1"); raw.write_text("changed"); self.assertEqual(store.validate_sources(loaded),ResultStatus.STALE)
 def test_nonconverged_and_raw_parsers(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp); out=root/"out"; out.write_text("! total energy = -1.0 Ry\n")
   self.assertEqual(DEFAULT_PARSERS.parse("QE_SCF_STDOUT",out).status,ResultStatus.NOT_CONVERGED)
   fixtures=(("DOS_RAW_DATA","dos.dat","DOSResult","# raw\n0.0 1.0\n1.0 2.0\n"),("BAND_STRUCTURE_RAW_DATA","bands.dat","BandStructureResult","nbnd= 2, nks= 2\n0.0 0.0 0.0\n-1.0 1.0\n0.5 0.0 0.0\n-0.5 1.5\n"),("PHONON_DOS_RAW_DATA","phdos.dat","PhononDOSResult","# raw\n0.0 1.0\n1.0 2.0\n"))
   for artifact, filename, kind, content in fixtures:
    source=root/filename; source.write_text(content); result=DEFAULT_PARSERS.parse(artifact,source); self.assertEqual(result.result_type,kind); self.assertEqual(result.status,ResultStatus.VALID)
 def test_scf_v021_optional_scalars_units_and_completion_evidence(self):
  with tempfile.TemporaryDirectory() as tmp:
   source=Path(tmp)/"scf.out"
   source.write_text("number of electrons = 8.500D+00\niteration # 1\niteration # 12\n! total energy = -1.2345E+01 Ry\nthe Fermi energy is -2.50e-01 ev\ntotal magnetization = -1.00 Bohr mag/cell\nabsolute magnetization = 2.00 Bohr mag/cell\nestimated scf accuracy < 1.0E-09 Ry\nconvergence has been achieved\nJOB DONE.\n")
   result=DEFAULT_PARSERS.parse("QE_SCF_STDOUT",source)
   self.assertEqual(result.status,ResultStatus.VALID); self.assertTrue(result.metadata["job_done"]); self.assertTrue(result.metadata["converged"])
   self.assertAlmostEqual(result.scalars["total_energy"]["value"],-12.345*13.605693122994); self.assertEqual(result.scalars["total_energy"]["unit"],"eV")
   self.assertEqual(result.scalars["number_of_electrons"],{"value":8.5,"unit":"electrons"}); self.assertEqual(result.scalars["electronic_iterations"],{"value":12,"unit":"iterations"})
   self.assertEqual(result.scalars["total_magnetization"]["unit"],"Bohr magneton/cell"); self.assertEqual(result.scalars["absolute_magnetization"]["unit"],"Bohr magneton/cell")
  with tempfile.TemporaryDirectory() as tmp:
   source=Path(tmp)/"minimal.out"; source.write_text("! total energy = -1 Ry\nconvergence has been achieved\nJOB DONE.\n")
   result=DEFAULT_PARSERS.parse("QE_SCF_STDOUT",source); self.assertEqual(result.status,ResultStatus.VALID)
   for key in ("fermi_energy","total_magnetization","absolute_magnetization"): self.assertNotIn(key,result.scalars)
  with tempfile.TemporaryDirectory() as tmp:
   source=Path(tmp)/"nonconverged.out"; source.write_text("! total energy = -1 Ry\nJOB DONE.\n")
   result=DEFAULT_PARSERS.parse("QE_SCF_STDOUT",source); self.assertEqual(result.status,ResultStatus.NOT_CONVERGED); self.assertTrue(result.metadata["job_done"]); self.assertFalse(result.metadata["converged"])
   source.write_text("! total energy = -1 Ry\nconvergence has been achieved\nError in routine electrons\n")
   self.assertEqual(DEFAULT_PARSERS.parse("QE_SCF_STDOUT",source).status,ResultStatus.PARSE_FAILED)
  with tempfile.TemporaryDirectory() as tmp:
   source=Path(tmp)/"truncated.out"; source.write_text("convergence has been achieved\nJOB DONE.\n")
   result=DEFAULT_PARSERS.parse("QE_SCF_STDOUT",source); self.assertEqual(result.status,ResultStatus.PARTIAL); self.assertNotIn("total_energy",result.scalars)

 def test_registry_is_unambiguous(self):
  self.assertEqual(DEFAULT_PARSERS.validate(),("BADER_ACF","BAND_STRUCTURE_RAW_DATA","DOS_RAW_DATA","EPW_SUMMARY","FERMI_SURFACE_BXSF","HUBBARD_PARAMETER_RAW_DATA","LOWDIN_POPULATION","PDOS_RAW_DATA","PHONON_DOS_RAW_DATA","QE_RELAX_STDOUT","QE_SCF_STDOUT","VOLUMETRIC_RAW_DATA","WANNIER_WOUT"))
