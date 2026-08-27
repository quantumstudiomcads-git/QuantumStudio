import unittest
from backend.compiler.calculation_compiler import CalculationCompiler
from backend.core.calculation_request import CalculationRequest
from backend.engines.qe import QuantumEspressoAdapter

S={"name":"S","periodic":[True,True,True],"cell":[[3,0,0],[0,3,0],[0,0,3]],"atoms":[{"element":"Si","x":0,"y":0,"z":0}]}
P={"pseudopotentials":{"Si":"Si.UPF"},"postprocessing":True,"kpath":[{"label":"G","coordinates":[0,0,0],"points":10},{"label":"X","coordinates":[.5,0,0],"points":10}]}
def plan(ids, extra=None): return CalculationCompiler(CalculationRequest(structure=S,selected_calculations=ids,parameters={**P,**(extra or {})})).compile()

class QEPostprocessingTests(unittest.TestCase):
 def test_bands_dos_pdos_and_pp_have_private_dags_and_inputs(self):
  b=plan(["bands"]); self.assertEqual([x.semantic_task_type for x in b.tasks],["scf","qe_pw_bands","qe_bands"]); generated=QuantumEspressoAdapter().compile_plan(b); self.assertEqual(generated.tasks[-1].executable,"bands.x"); self.assertIn("K_POINTS crystal_b",generated.tasks[-2].input_text); self.assertEqual(generated.tasks[0].input_text.count("K_POINTS"),1); self.assertEqual(generated.tasks[-2].input_text.count("K_POINTS"),1); self.assertNotIn("K_POINTS gamma",generated.tasks[-2].input_text); self.assertTrue(generated.tasks[-2].input_text.rstrip().endswith("0.5 0 0 1")); self.assertEqual(b.tasks[-1].artifact_outputs,("BAND_STRUCTURE_RAW_DATA",))
  d=plan(["dos","pdos"]); types=[x.semantic_task_type for x in d.tasks]; self.assertIn("qe_dos",types); self.assertIn("qe_projwfc",types); self.assertEqual(sum(x=="scf" for x in types),1); self.assertNotEqual(next(x for x in d.tasks if x.semantic_task_type=="qe_dos").parameter_signature,next(x for x in d.tasks if x.semantic_task_type=="qe_projwfc").parameter_signature)
  pp=plan(["charge_density"]); self.assertEqual(pp.tasks[-1].tool_id,"pp.x"); self.assertIn("plot_num = 0",QuantumEspressoAdapter().compile_plan(pp).tasks[-1].input_text)
 def test_private_nscf_contract_is_purpose_signed_and_reuses_qe_state(self):
  d=plan(["dos","pdos"]); scf=next(x for x in d.tasks if x.semantic_task_type=="scf"); nscf=[x for x in d.tasks if x.semantic_task_type=="qe_pw_nscf"]
  self.assertEqual({x.metadata["purpose"] for x in nscf},{"dos","pdos"}); self.assertNotEqual(nscf[0].parameter_signature,nscf[1].parameter_signature)
  for task in nscf:
   contract=task.metadata["private_nscf_contract"]; self.assertEqual(task.depends_on_task_ids,(scf.id,)); self.assertEqual(contract["parent_scf_task_id"],scf.id); self.assertEqual(contract["state_inputs"],["qe_charge_density","qe_save"]); self.assertTrue(contract["requires_shared_prefix_outdir"]); self.assertEqual(task.structure_reference,"request_snapshot")
  generated=QuantumEspressoAdapter().compile_plan(d); generated_nscf=[x for x in generated.tasks if x.metadata["semantic_task_type"]=="qe_pw_nscf"]; self.assertEqual({x.metadata["qe_prefix"] for x in generated_nscf},{generated.context.prefix}); self.assertEqual({x.metadata["qe_outdir"] for x in generated_nscf},{generated.context.outdir}); self.assertEqual({x.metadata["qe_pseudo_dir"] for x in generated_nscf},{"../pseudos"})

 def test_e2_dos_parameters_and_public_nscf_status(self):
  from frontend.calculations.catalog import CALCULATIONS
  first=plan(["dos"],{"energy_window":[-8,7],"delta_e":0.05}); second=plan(["dos"],{"energy_window":[-8,7],"delta_e":0.10})
  terminal=next(item for item in first.tasks if item.semantic_task_type=="qe_dos"); changed=next(item for item in second.tasks if item.semantic_task_type=="qe_dos")
  self.assertNotEqual(terminal.parameter_signature,changed.parameter_signature)
  input_text=next(item for item in QuantumEspressoAdapter().compile_plan(first).tasks if item.metadata["semantic_task_type"]=="qe_dos").input_text
  self.assertIn("Emin = -8",input_text); self.assertIn("Emax = 7",input_text); self.assertIn("DeltaE = 0.05",input_text)
  self.assertEqual(next(item for item in CALCULATIONS if item.id=="nscf").status,"partial")

 def test_e3_method_writer_and_hubbard_propagation(self):
  from backend.engines.qe.writer import electronic_method
  collinear=plan(["dos","pdos"],{"spin_treatment":"COLLINEAR_SPIN","starting_magnetization":{"Si":0.5},"hubbard_terms":[{"species":"Si","manifold":"3d","u_eV":3.0}]})
  generated=QuantumEspressoAdapter().compile_plan(collinear)
  for task in generated.tasks:
   if task.metadata["semantic_task_type"] in {"scf","qe_pw_nscf"}: self.assertIn("nspin = 2",task.input_text); self.assertIn("starting_magnetization(1) = 0.5",task.input_text); self.assertIn("HUBBARD (ortho-atomic)",task.input_text); self.assertIn("U Si-3d 3",task.input_text)
  self.assertEqual(electronic_method({"spin_treatment":"SOC"}),"SOC")
  with self.assertRaises(Exception): electronic_method({"spin_treatment":"COLLINEAR_SPIN","soc":True})
  with self.assertRaises(Exception): QuantumEspressoAdapter().compile_plan(plan(["dos"],{"hubbard_terms":[{"species":"X","manifold":"3d","u_eV":3.0}]}))
  with self.assertRaisesRegex(ValueError, "SOC PDOS projector/spinor decomposition"):
   plan(["pdos"], {"spin_treatment":"SOC"})
  first=next(x for x in collinear.tasks if x.semantic_task_type=="qe_pw_nscf").parameter_signature; changed=plan(["dos"],{"spin_treatment":"COLLINEAR_SPIN","starting_magnetization":{"Si":0.5},"hubbard_terms":[{"species":"Si","manifold":"3d","u_eV":4.0}]}).tasks[-2].parameter_signature; self.assertNotEqual(first,changed)

 def test_e3_hubbard_request_persistence_round_trip(self):
  request=CalculationRequest(id="e3-u",structure=S,selected_calculations=["dos"],parameters={**P,"spin_treatment":"COLLINEAR_SPIN","hubbard_terms":[{"species":"Si","manifold":"3d","u_eV":3.0}],"hubbard_projector":"ortho-atomic"})
  restored=CalculationRequest.from_persistence_dict(request.to_persistence_dict())
  self.assertEqual(restored.parameters["hubbard_terms"],[{"species":"Si","manifold":"3d","u_eV":3.0}]); self.assertEqual(restored.parameters["hubbard_projector"],"ortho-atomic"); self.assertEqual(restored.parameters["spin_treatment"],"COLLINEAR_SPIN")

 def test_spin_validation_phonon_chain_and_commands(self):
  with self.assertRaises(Exception): plan(["spin_density"])
  ph=plan(["phonon_dos"]); self.assertEqual([x.semantic_task_type for x in ph.tasks],["scf","qe_ph","qe_q2r","qe_matdyn"]); generated=QuantumEspressoAdapter().compile_plan(ph); self.assertEqual([x.executable for x in generated.tasks][-3:],["ph.x","q2r.x","matdyn.x"])
  for item in generated.tasks: self.assertNotIn("<",item.executable)
 def test_missing_band_path_is_typed(self):
  with self.assertRaises(Exception): plan(["bands"],{"kpath":None})
