import json, tempfile, unittest
from pathlib import Path
from backend.compiler.negf import compile_transport_workflow
from backend.engines.negf import ArtifactReference, CentralRegionModel, ElectrodeModel, HamiltonianSource, HamiltonianSourceMode, NEGFSettings, NEGFWorkflowAdapter, PrincipalLayer, SpinMode, TransportComponent, TransportInput, TransportModelError
from backend.engines.negf.models import ComponentRole, TRANSPORT_HAMILTONIAN, TRANSPORT_OVERLAP, WANNIER_HAMILTONIAN
S={"atoms":[{"element":"C","x":0,"y":0,"z":0}],"cell":[[2,0,0],[0,2,0],[0,0,10]],"periodic":[True,True,False]}
def artifact(kind,name): return ArtifactReference(kind,name)
def source(name,overlap=None): return HamiltonianSource(HamiltonianSourceMode.WANNIER90,artifact(WANNIER_HAMILTONIAN,name),overlap)
def layer(name,overlap=False): return PrincipalLayer((2.,0.,0.),1,artifact(TRANSPORT_HAMILTONIAN,name+"-onsite"),artifact(TRANSPORT_HAMILTONIAN,name+"-coupling"),artifact(TRANSPORT_OVERLAP,name+"-onsite-s") if overlap else None,artifact(TRANSPORT_OVERLAP,name+"-coupling-s") if overlap else None)
def transport(nonorthogonal=False):
 overlap=artifact(TRANSPORT_OVERLAP,"central-s") if nonorthogonal else None
 left=ElectrodeModel(TransportComponent("left",ComponentRole.LEFT_ELECTRODE,S,source("left")),layer("left"),0.,300.); right=ElectrodeModel(TransportComponent("right",ComponentRole.RIGHT_ELECTRODE,S,source("right")),layer("right"),0.,300.)
 central=CentralRegionModel(TransportComponent("central",ComponentRole.CENTRAL_REGION,S,source("central",overlap)),artifact(TRANSPORT_HAMILTONIAN,"lc"),artifact(TRANSPORT_HAMILTONIAN,"cr"),overlap)
 return TransportInput("synthetic-two-probe","X",left,central,right,(False,True,False),{"origin":"C5D test"})
def settings(**kwargs):
 values={"energy_min_ev":-2.,"energy_max_ev":2.,"energy_points":401,"eta_ev":1e-4,"transverse_k_mesh":(1,8,1)}; values.update(kwargs); return NEGFSettings(**values)
class NEGFWorkflowTests(unittest.TestCase):
 def test_typed_three_component_model_and_wannier_contract(self):
  value=transport(); self.assertEqual(value.central_region.component.hamiltonian_source.hamiltonian.artifact_type,WANNIER_HAMILTONIAN); self.assertEqual(value.central_region.component.hamiltonian_source.basis_kind,"ORTHOGONAL_S_EQUALS_IDENTITY")
  with self.assertRaises(TransportModelError): TransportInput("bad","X",value.left_electrode,value.central_region,value.right_electrode,(True,True,False))
 def test_explicit_dag_artifacts_and_nonorthogonal_basis(self):
  plan=compile_transport_workflow(transport(True),settings()); tasks={x.semantic_task_type:x for x in plan.tasks}; self.assertEqual(tasks["negf_self_energy_left"].depends_on_task_ids,(tasks["negf_electrode_left"].id,)); self.assertEqual(tasks["negf_device_green"].depends_on_task_ids,(tasks["negf_self_energy_left"].id,tasks["negf_self_energy_right"].id)); self.assertEqual(tasks["negf_transmission"].artifact_outputs,("TRANSMISSION_DATA",)); self.assertEqual(tasks["negf_device_green"].parameters["central_region"]["overlap"]["artifact_type"],TRANSPORT_OVERLAP)
 def test_energy_spin_kperp_and_bias_validation(self):
  with self.assertRaises(TransportModelError): settings(energy_min_ev=1.,energy_max_ev=0.)
  with self.assertRaises(TransportModelError): settings(eta_ev=0.)
  with self.assertRaises(TransportModelError): compile_transport_workflow(transport(),settings(transverse_k_mesh=(2,8,1)))
  self.assertEqual(settings(spin_mode=SpinMode.SPIN_RESOLVED,mu_left_ev=.1,mu_right_ev=-.1).effective_degeneracy,1); self.assertEqual(settings(spin_mode=SpinMode.SPIN_DEGENERATE).effective_degeneracy,2); self.assertEqual(settings(spin_mode=SpinMode.SPINOR).effective_degeneracy,1)
 def test_deterministic_configuration_and_export(self):
  first=compile_transport_workflow(transport(),settings()); second=compile_transport_workflow(transport(),settings()); adapter=NEGFWorkflowAdapter(); a,manifest=adapter.compile_plan(first); b,_=adapter.compile_plan(second); self.assertEqual([x.configuration_text for x in a],[x.configuration_text for x in b]); self.assertEqual(manifest["execution_backend"],"not_selected"); self.assertIn("T(E)=Tr",a[-1].configuration_text)
  with tempfile.TemporaryDirectory() as tmp:
   output=adapter.write_plan(first,Path(tmp)); self.assertTrue((output/"006_negf_transmission"/"negf_config.json").exists()); self.assertEqual(json.loads((output/"manifest.json").read_text())["engine_id"],"negf"); self.assertFalse(list(Path(tmp).glob(".synthetic-two-probe.staging-*")))
 def test_public_negf_catalog_entries_remain_planned(self):
  from frontend.calculations.catalog import CALCULATIONS
  state={item.id:item.status for item in CALCULATIONS}; self.assertEqual(state["transmission"],"planned"); self.assertEqual(state["local_dos"],"planned"); self.assertEqual(state["iv_curve"],"planned")
