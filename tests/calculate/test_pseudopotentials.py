import json, sys, tempfile, unittest
from pathlib import Path
from backend.pseudopotentials import *
from backend.pseudopotentials.models import sha256
from backend.pseudopotentials.compatibility import compatibility
from backend.pseudopotentials.providers import provider_library
from backend.compiler.calculation_compiler import CalculationCompiler
from backend.core.calculation_request import CalculationRequest
from backend.core.execution_contract import CommandSpec
from backend.execution import GeneratedTask, GeneratedWorkflow, LocalExecutionManager, LocalToolConfiguration

S={"periodic":[True,True,True],"cell":[[3,0,0],[0,3,0],[0,0,3]],"atoms":[{"element":"Si","x":0,"y":0,"z":0}]}
class PseudoTests(unittest.TestCase):
 def test_upf_metadata_compatibility_and_cutoffs(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp,"Si.UPF"); p.write_text("<PP_HEADER element=\"Si\" functional=\"PBE\" pseudo_type=\"NC\" relativistic=\"full\" has_so=\"T\" z_valence=\"4\" cutoff_wfc=\"50\" cutoff_rho=\"200\"/>")
   r=inspect_upf(p); self.assertEqual(r.xc_functional,"pbe"); self.assertTrue(r.has_spin_orbit); self.assertEqual(compatibility("hse06",r).state,CompatibilityState.COMPATIBLE_SEMILOCAL_PARENT); self.assertEqual(compatibility("pbe",r,True).state,CompatibilityState.COMPATIBLE); self.assertEqual(recommended_cutoffs([r]),{"ecutwfc":50.,"ecutrho":200.,"complete":True})
 def test_registry_provider_filters_and_hash(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp,"Te.UPF"); p.write_text("<PP_HEADER element=\"Te\" functional=\"BLYP\" pseudo_type=\"PAW\" relativistic=\"scalar\"/>")
   reg=PseudoLibraryRegistry(); reg.register(provider_library("sssp_precision",tmp,version="1.3")); records=reg.index("sssp_precision"); manifest=Path(tmp,"manifest.json"); manifest.write_text(json.dumps({"pseudopotentials":[{"filename":"Te.UPF","sha256":records[0].sha256,"cutoff_wfc":70,"cutoff_rho":560}]})); self.assertEqual(reg.index_manifest("sssp_precision",manifest)[0].recommended_ecutrho_ry,560.0); self.assertEqual(reg.find("Te",pseudo_type="PAW")[0].library_id,"sssp_precision"); first=records[0].sha256; p.write_text(p.read_text()+" changed"); self.assertNotEqual(first,inspect_upf(p).sha256); self.assertIsNotNone(reg.unregister("sssp_precision")); self.assertIn("gbrv",PROVIDER_LIBRARY_IDS)
 def test_missing_species_soc_and_signature(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp,"Si.UPF"); p.write_text("<PP_HEADER element=\"Si\" functional=\"PBE\" pseudo_type=\"NC\" relativistic=\"scalar\"/>")
   record=inspect_upf(p); missing,findings=validate_pseudo_set("b3lyp",True,["Si","Sb"],PseudoSet({"Si":record})); self.assertEqual(missing,("Sb",)); self.assertEqual(findings["Si"].state,CompatibilityState.WARNING_RELATIVITY)
   a=CalculationRequest(S,["scf"],parameters={"pseudopotentials":{"Si":{"filename":"Si.UPF","sha256":"a"}}}); b=a.copy_with(parameters={"pseudopotentials":{"Si":{"filename":"Si.UPF","sha256":"b"}}}); self.assertNotEqual(CalculationCompiler(a).compile().tasks[0].parameter_signature,CalculationCompiler(b).compile().tasks[0].parameter_signature)
 def test_generic_preflight_rejects_changed_provenanced_pseudo(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp); pseudo=root/"Si.UPF"; pseudo.write_text("original"); digest=sha256(pseudo); (root/"task").mkdir(); (root/"manifest.json").write_text(json.dumps({"request_id":"r","pseudopotentials":{"Si":{"source":str(pseudo),"sha256":digest}}})); pseudo.write_text("modified")
   flow=GeneratedWorkflow("r",root,(GeneratedTask("task","task","test","python","task",CommandSpec(sys.executable)),)); errors=LocalExecutionManager(LocalToolConfiguration(tool_paths={"python":sys.executable})).preflight(flow); self.assertTrue(any("SHA-256" in error for error in errors))
