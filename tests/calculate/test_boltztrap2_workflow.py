import json
import tempfile
import unittest
from pathlib import Path

import backend.calculations
from backend.compiler.calculation_compiler import CalculationCompiler
from backend.core.calculation_request import CalculationRequest
from backend.engines.boltztrap2 import BoltzTraP2WorkflowAdapter, BTP2SettingsError

S={"atoms":[{"element":"C","x":0.,"y":0.,"z":0.}],"cell":[[2.46,0,0],[0,2.46,0],[0,0,15]],"periodic":[True,True,False]}
P={"pseudopotentials":{"C":"C.UPF"},"transport_k_mesh":[8,8,1],"num_bands":8,"temperatures":[300.,600.],"chemical_potential_range":[-0.5,0.5,11],"interpolation":{"energy_window_ev":[-5,5]}}

def plan(selected, params=P, structure=S):
    return CalculationCompiler(CalculationRequest(id="btp2-test",structure=structure,selected_calculations=selected,parameters=params)).compile()

class BoltzTraP2WorkflowTests(unittest.TestCase):
    def test_bands_dag_and_electronic_bands_contract(self):
        result=plan(["boltztrap_bands"]); self.assertEqual([t.semantic_task_type for t in result.tasks],["scf","qe_pw_nscf_btp2","btp2_interpolate"])
        scf,nscf,interpolate=result.tasks; self.assertEqual(nscf.depends_on_task_ids,(scf.id,)); self.assertEqual(nscf.artifact_outputs,("ElectronicBandsData",)); self.assertEqual(interpolate.artifact_inputs,("ElectronicBandsData",)); self.assertEqual(interpolate.artifact_outputs,("BTP2_INTERPOLATED_BANDS",)); self.assertFalse(nscf.metadata["electronic_bands_data_contract"]["populated_during_execution"])

    def test_transport_intents_and_tau_semantics(self):
        result=plan(["seebeck","electrical_conductivity","thermal_conductivity_electronic","power_factor","carrier_concentration"]); transport=result.tasks[-1]
        self.assertEqual(transport.semantic_task_type,"btp2_transport"); self.assertEqual(transport.depends_on_task_ids,(result.tasks[-2].id,)); self.assertEqual(set(transport.artifact_outputs),{"SEEBECK_DATA","SIGMA_OVER_TAU","KAPPA_E_OVER_TAU","POWER_FACTOR_OVER_TAU","CARRIER_CONCENTRATION_DATA"})
        absolute=dict(P,relaxation_time_model="CONSTANT_RELAXATION_TIME",relaxation_time=1e-14,effective_thickness=6.0)
        self.assertEqual(set(plan(["electrical_conductivity","thermal_conductivity_electronic","power_factor"],absolute).tasks[-1].artifact_outputs),{"SIGMA","KAPPA_E","POWER_FACTOR"})
        for bad in (dict(P,relaxation_time_model="CONSTANT_RELAXATION_TIME",relaxation_time=0),dict(P,relaxation_time_model="EPW_SCATTERING_TIME")):
            with self.assertRaises(BTP2SettingsError): plan(["electrical_conductivity"],bad)

    def test_signatures_are_incompatible_with_wannier_and_epw_and_share_scf(self):
        btp2=next(t for t in plan(["boltztrap_bands"]).tasks if t.semantic_task_type=="qe_pw_nscf_btp2")
        from tests.calculate.test_wannier_workflow import plan as wannier_plan
        from tests.calculate.test_epw_workflow import P as EPW_P, S as EPW_S
        wannier=next(t for t in wannier_plan().tasks if t.semantic_task_type=="qe_pw_nscf")
        epw=next(t for t in CalculationCompiler(CalculationRequest(structure=EPW_S,selected_calculations=["electron_phonon"],parameters=EPW_P)).compile().tasks if t.semantic_task_type=="qe_pw_nscf")
        self.assertNotEqual(btp2.parameter_signature,wannier.parameter_signature); self.assertNotEqual(btp2.parameter_signature,epw.parameter_signature)
        combo=plan(["boltztrap_bands","seebeck"]); self.assertEqual(sum(t.semantic_task_type=="scf" for t in combo.tasks),1)

    def test_2d_policy_persistence_snapshot_config_and_transaction(self):
        with self.assertRaisesRegex(BTP2SettingsError,"transport_k_mesh"): plan(["seebeck"],dict(P,transport_k_mesh=[8,8,2]))
        with self.assertRaisesRegex(BTP2SettingsError,"effective_thickness"): plan(["electrical_conductivity"],dict(P,relaxation_time_model="CONSTANT_RELAXATION_TIME",relaxation_time=1e-14))
        original=plan(["seebeck"]); restored=CalculationCompiler(CalculationRequest.from_persistence_dict(CalculationRequest(id="btp2-test",structure=S,selected_calculations=["seebeck"],parameters=P).to_persistence_dict())).compile()
        one,manifest=BoltzTraP2WorkflowAdapter().compile_plan(original); two,_=BoltzTraP2WorkflowAdapter().compile_plan(restored); self.assertEqual([x.input_text for x in one],[x.input_text for x in two]); self.assertIn("normalization_warning",json.loads(one[-1].input_text)); self.assertEqual(manifest["tasks"][-1]["engine_id"],"boltztrap2")
        changed=json.loads(json.dumps(S)); changed["atoms"][0]["x"]=99; self.assertNotIn("99",one[0].input_text)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); output=BoltzTraP2WorkflowAdapter().write_plan(original,root); self.assertTrue((output/"003_btp2_interpolate"/"btp2_config.json").exists()); self.assertTrue((output/"004_btp2_transport"/"btp2_transport.json").exists()); self.assertTrue((output/"manifest.json").exists())
            with self.assertRaises(Exception): BoltzTraP2WorkflowAdapter().write_plan(original,root)
            self.assertFalse(list(root.glob(".btp2-test.staging-*")))
            blocked=root/"blocked"; blocked.write_text("x")
            with self.assertRaises(Exception): BoltzTraP2WorkflowAdapter().write_plan(original,blocked)
            self.assertFalse(list(root.glob(".btp2-test.staging-*")))

    def test_zt_and_mobility_remain_deferred(self):
        from frontend.calculations.catalog import CALCULATIONS
        status={item.id:item.status for item in CALCULATIONS}; self.assertEqual(status["zt"],"planned"); self.assertEqual(status["mobility"],"planned")

if __name__=="__main__": unittest.main()
