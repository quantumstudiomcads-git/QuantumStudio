import tempfile, unittest
from pathlib import Path
import numpy as np
from backend.results.parsers import parse_volumetric_cube, ResultParseError
from backend.results.models import ResultProvenance,ResultStatus,ScientificResult
from backend.results.store import ResultStore
from backend.results.volumetric import field_slice,field_profile
from backend.analyze.volumetric import export_volumetric_npz,export_slice_csv,export_profile_csv
from backend.compiler.calculation_compiler import CalculationCompiler
from backend.core.calculation_request import CalculationRequest
import backend.calculations
CUBE="""comment\ncomment\n 1 0 0 0\n 2 1 0 0\n 2 0 2 0\n 2 0 0 3\n 1 1 0 0 0\n 0 1 2 3 4 5\n 6 7\n"""
def result():
 p=ResultProvenance("r","e","t","qe","pp.x",(),{},"fixture")
 return ScientificResult("VolumetricResult",ResultStatus.VALID,p,arrays={"values":np.arange(8,dtype=float).reshape(2,2,2)},metadata={"cell":[[2,0,0],[0,4,0],[0,0,6]],"origin":[0,0,0],"unit":"u","quantity_kind":"SPIN_DENSITY","signed":True})
class VolumetricE4Tests(unittest.TestCase):
 def test_cube_array_order_cell_and_units(self):
  with tempfile.TemporaryDirectory() as td:
   path=Path(td)/"field.cube"; path.write_text(CUBE); r=parse_volumetric_cube(path,field_metadata={"kind":"charge","periodic":[True,False,True]}); self.assertEqual(r.arrays["values"].shape,(2,2,2)); self.assertEqual(r.arrays["values"][1,0,1],5); self.assertEqual(r.metadata["periodic"],[True,False,True]); self.assertAlmostEqual(r.metadata["cell"][0][0],2*.529177210903)
 def test_spin_sign_and_elf_diagnostic(self):
  with tempfile.TemporaryDirectory() as td:
   path=Path(td)/"field.cube"; path.write_text(CUBE.replace("0 1 2 3 4 5\n 6 7","-1 0 .5 1.2 4 5\n 6 7")); spin=parse_volumetric_cube(path,field_metadata={"kind":"spin"}); elf=parse_volumetric_cube(path,field_metadata={"kind":"elf"}); self.assertLess(float(spin.arrays["values"].min()),0); self.assertTrue(elf.metadata["parser_diagnostics"])

 def test_bad_cube_is_conservative(self):
  with tempfile.TemporaryDirectory() as td:
   path=Path(td)/"bad.cube"; path.write_text(CUBE.replace("6 7","6"));
   with self.assertRaises(ResultParseError): parse_volumetric_cube(path,field_metadata={"kind":"charge"})
 def test_slices_profiles_and_periodic_boundary(self):
  r=result(); self.assertTrue(np.array_equal(field_slice(r,"XY",.5).values,[[1,3],[5,7]])); self.assertTrue(np.array_equal(field_slice(r,"XZ",.5).values,[[2,3],[6,7]])); self.assertTrue(np.array_equal(field_slice(r,"YZ",.5).values,[[4,5],[6,7]])); self.assertTrue(np.array_equal(field_slice(r,"XY",1.0).values,field_slice(r,"XY",0.0).values)); p=field_profile(r,"Z"); self.assertTrue(np.allclose(p["values"],[3,4])); self.assertTrue(np.allclose(p["distance_A"],[0,3]))
 def test_store_and_exports(self):
  with tempfile.TemporaryDirectory() as td:
   r=result(); store=ResultStore(td,"e"); store.save(r); loaded=store.load(r.result_id); self.assertTrue(np.array_equal(loaded.arrays["values"],r.arrays["values"])); npz=export_volumetric_npz(r,Path(td)/"f.npz"); sl=export_slice_csv(r,Path(td)/"s.csv"); pr=export_profile_csv(r,Path(td)/"p.csv"); self.assertTrue(all(x.stat().st_size>0 for x in (npz,sl,pr)))
 def test_pp_dags_and_spin_guard(self):
  s={"name":"S","periodic":[True,True,True],"cell":[[3,0,0],[0,3,0],[0,0,3]],"atoms":[{"element":"Si","x":0,"y":0,"z":0}]}; p={"postprocessing":True,"pseudopotentials":{"Si":"Si.UPF"}}
  for ident,kind in (("charge_density","charge"),("electron_localization","elf"),("electrostatic_potential","potential")):
   plan=CalculationCompiler(CalculationRequest(id=ident,structure=s,selected_calculations=[ident],parameters=p)).compile(); task=plan.tasks[-1]; self.assertEqual(task.semantic_task_type,"qe_pp"); self.assertEqual(task.metadata["field"]["kind"],kind)
  with self.assertRaises(Exception): CalculationCompiler(CalculationRequest(id="spin",structure=s,selected_calculations=["spin_density"],parameters=p)).compile()

