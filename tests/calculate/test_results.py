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
   workflow=root/"workflow"; workflow.mkdir(); store=ResultStore(workflow,"e"); store.save(result); loaded=store.load(result.result_id); self.assertEqual(loaded.provenance.execution_id,"e"); raw.write_text("changed"); self.assertEqual(store.validate_sources(loaded),ResultStatus.STALE)
 def test_nonconverged_and_raw_parsers(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp); out=root/"out"; out.write_text("! total energy = -1.0 Ry\n")
   self.assertEqual(DEFAULT_PARSERS.parse("QE_SCF_STDOUT",out).status,ResultStatus.NOT_CONVERGED)
   for artifact, filename, kind in (("DOS_RAW_DATA","dos.dat","DOSResult"),("BAND_STRUCTURE_RAW_DATA","bands.dat","BandStructureResult"),("PHONON_DOS_RAW_DATA","phdos.dat","PhononDOSResult")):
    source=root/filename; source.write_text("# raw\n0.0 1.0\n1.0 2.0\n"); result=DEFAULT_PARSERS.parse(artifact,source); self.assertEqual(result.result_type,kind); self.assertEqual(result.status,ResultStatus.VALID)
 def test_registry_is_unambiguous(self):
  self.assertEqual(DEFAULT_PARSERS.validate(),("BAND_STRUCTURE_RAW_DATA","DOS_RAW_DATA","PHONON_DOS_RAW_DATA","QE_SCF_STDOUT"))
