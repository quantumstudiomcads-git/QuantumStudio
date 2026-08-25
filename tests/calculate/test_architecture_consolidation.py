import unittest
from backend.calculations.semantics import CalculationKind, InputCardinality, SEMANTICS
from backend.compiler.architecture import canonical_artifact, task_family, validate_calculation_architecture, validate_task_artifacts
from backend.compiler.calculation_compiler import CalculationCompiler
from backend.core.calculation_request import CalculationRequest
from backend.core.execution_contract import CommandSpec, ExecutionMode
from backend.compiler.generated_workflow import execution_readiness_for_task, manifest_contract_errors, manifest_task_contract
from backend.engines.registry import ENGINES, task_generation_support
from frontend.calculations.catalog import CALCULATIONS
from tests.calculate.test_wannier_workflow import STRUCTURE, PARAMS
from tests.calculate.test_epw_workflow import P as EPW_PARAMS, S as EPW_STRUCTURE
from tests.calculate.test_boltztrap2_workflow import P as BTP2_PARAMS, S as BTP2_STRUCTURE
from tests.calculate.test_negf_workflow import settings, transport
from backend.compiler.negf import compile_transport_workflow
class ArchitectureConsolidationTests(unittest.TestCase):
 def test_all_147_semantics_kinds_cardinality_and_acyclic_dependencies(self):
  report=validate_calculation_architecture(); self.assertEqual(report.public_count,147); self.assertEqual(report.semantic_count,147); self.assertEqual(report.errors,()); self.assertEqual(SEMANTICS["scf"].kind,CalculationKind.PRIMITIVE); self.assertEqual(SEMANTICS["bands"].kind,CalculationKind.WORKFLOW); self.assertEqual(SEMANTICS["band_gap"].kind,CalculationKind.DERIVED); self.assertEqual(SEMANTICS["formation_energy"].kind,CalculationKind.MULTI_SYSTEM); self.assertEqual(SEMANTICS["parameter_sweep"].kind,CalculationKind.META); self.assertEqual(SEMANTICS["transmission"].input_cardinality,InputCardinality.DEVICE_TRANSPORT)
 def test_engine_registry_and_structured_command_contract(self):
  self.assertEqual(set(ENGINES),{"quantum_espresso","wannier90","epw","boltztrap2","negf"}); self.assertEqual(CommandSpec("pw.x",stdin_file="scf.in",stdout_file="scf.out").execution_mode,ExecutionMode.SUBPROCESS); self.assertEqual(CommandSpec("wannier90",("-pp","seed"),execution_mode=ExecutionMode.SUBPROCESS).arguments,("-pp","seed"));
  with self.assertRaises(ValueError): CommandSpec("pw.x",("<","scf.in"))
  plan=CalculationCompiler(CalculationRequest(structure=STRUCTURE,selected_calculations=["bands"],parameters={"pseudopotentials":{"C":"C.UPF"}})).compile(); self.assertEqual(task_generation_support(plan.tasks[-1]).value,"DEFERRED")
 def test_cross_engine_artifact_contracts_and_signature_isolation(self):
  w=CalculationCompiler(CalculationRequest(structure=STRUCTURE,selected_calculations=["wannierization"],parameters=PARAMS)).compile(); e=CalculationCompiler(CalculationRequest(structure=EPW_STRUCTURE,selected_calculations=["electron_phonon"],parameters=EPW_PARAMS)).compile(); b=CalculationCompiler(CalculationRequest(structure=BTP2_STRUCTURE,selected_calculations=["seebeck"],parameters=BTP2_PARAMS)).compile(); n=compile_transport_workflow(transport(),settings())
  for plan in (w,e,b,n): self.assertEqual(validate_task_artifacts(plan.tasks),())
  wn=next(x for x in w.tasks if x.semantic_task_type=="qe_pw_nscf"); en=next(x for x in e.tasks if x.semantic_task_type=="qe_pw_nscf"); bn=next(x for x in b.tasks if x.semantic_task_type=="qe_pw_nscf_btp2"); self.assertNotEqual(wn.parameter_signature,bn.parameter_signature); self.assertNotEqual(wn.parameter_signature,en.parameter_signature); self.assertEqual(canonical_artifact("wannier_hr"),"WANNIER_HAMILTONIAN"); self.assertEqual(task_family("qe_pw_nscf_btp2"),"qe_pw_nscf"); self.assertEqual(task_family("negf_self_energy_left"),"negf_self_energy")
 def test_common_manifest_contract_is_c6_ready(self):
  plan=CalculationCompiler(CalculationRequest(structure=STRUCTURE,selected_calculations=["wannierization"],parameters=PARAMS)).compile(); manifest={"tasks":[manifest_task_contract(task,working_directory=f"{index:03d}",input_file="input.in") for index,task in enumerate(plan.tasks,1)]}; self.assertEqual(manifest_contract_errors(manifest),())
 def test_public_support_remains_honest(self):
  state={item.id:item.status for item in CALCULATIONS}; self.assertEqual(state["transmission"],"planned"); self.assertEqual(state["scf"],"ready"); self.assertEqual(SEMANTICS["formation_energy"].input_cardinality,InputCardinality.MULTI_STRUCTURE)
