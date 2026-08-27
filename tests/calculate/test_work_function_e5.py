import unittest
import numpy as np
from backend.analyze.work_function import slab_axis,derive_work_function,macroscopic_average
from backend.results.models import ScientificResult,ResultStatus,ResultProvenance
def make(potential,periodic=[True,True,False],execution="e",fermi=1.):
 p=ResultProvenance("r",execution,"pp","qe","pp.x",(),{},"fixture",structure_fingerprint="fp"); meta={"quantity_kind":"ELECTROSTATIC_POTENTIAL","periodic":periodic,"cell":[[4,0,0],[0,4,0],[0,0,20]],"electronic_method":{"spin_treatment":"SCALAR_NONSPIN"},"workflow_provenance":{"structure_fingerprint":"fp"}}; field=np.tile(np.asarray(potential,float)[None,None,:],(2,2,1)); pot=ScientificResult("VolumetricResult",ResultStatus.VALID,p,arrays={"values":field},metadata=meta); s=ScientificResult("GroundStateResult",ResultStatus.VALID,ResultProvenance("r",execution,"scf","qe","pw.x",(),{},"fixture",structure_fingerprint="fp"),scalars={} if fermi is None else {"fermi_energy":{"value":fermi,"unit":"eV"}},metadata={"electronic_method":{"spin_treatment":"SCALAR_NONSPIN"},"workflow_provenance":{"structure_fingerprint":"fp"}}); return pot,s
class WorkFunctionE5Tests(unittest.TestCase):
 def test_axis_detection(self):
  self.assertEqual(slab_axis([True,True,False]),2); self.assertEqual(slab_axis([False,True,True]),0); self.assertEqual(slab_axis([True,False,True]),1);
  with self.assertRaises(ValueError): slab_axis([True,True,True])
 def test_two_synthetic_plateaus_and_gauge_invariance(self):
  # slab atoms at center; circular vacuum spans cell boundary and plateau is 4 eV in Ry
  values=np.full(100,4/13.605693122994); values[40:60]=0; pot,scf=make(values,fermi=1.); atoms=[{"x":0,"y":0,"z":10}]
  first=derive_work_function(pot,scf,atoms,minimum_width_A=5,max_std_eV=.01,max_slope_eV_per_A=.01); self.assertEqual(first["status"],ResultStatus.VALID); self.assertAlmostEqual(first["work_functions_eV"][0],3,places=6);
  shifted,shifted_scf=make(values+10/13.605693122994,fermi=11.); second=derive_work_function(shifted,shifted_scf,atoms,minimum_width_A=5,max_std_eV=.01,max_slope_eV_per_A=.01); self.assertAlmostEqual(second["work_functions_eV"][0],3,places=6)
 def test_missing_fermi_wrong_state_and_slope_rejected(self):
  values=np.linspace(4/13.605693122994,5/13.605693122994,100); pot,scf=make(values); atoms=[{"x":0,"y":0,"z":10}]
  self.assertEqual(derive_work_function(pot,scf,atoms,max_slope_eV_per_A=.001)["status"],ResultStatus.PARTIAL); _,none=make(values,fermi=None); self.assertEqual(derive_work_function(pot,none,atoms)["status"],ResultStatus.PARTIAL); _,other=make(values,execution="other");
  with self.assertRaises(ValueError): derive_work_function(pot,other,atoms)
 def test_macroscopic_uses_physical_window(self):
  profile={"potential_eV":np.tile([0.,1.],50),"distance_A":np.arange(100)*.1}; smooth=macroscopic_average(profile,1.0); self.assertLess(np.std(smooth),.2)


 def test_manual_selection_and_charged_slab_policy(self):
  values=np.full(100,4/13.605693122994); values[40:60]=0; pot,scf=make(values); atoms=[{"x":0,"y":0,"z":10}]
  manual=derive_work_function(pot,scf,atoms,manual_interval=(.75,.25)); self.assertEqual(manual["status"],ResultStatus.VALID); self.assertEqual(manual["selection_mode"],"MANUAL")
  scf.metadata["tot_charge"]=1; blocked=derive_work_function(pot,scf,atoms); self.assertEqual(blocked["status"],ResultStatus.PARTIAL); self.assertIn("net-charged",blocked["diagnostics"][0])
