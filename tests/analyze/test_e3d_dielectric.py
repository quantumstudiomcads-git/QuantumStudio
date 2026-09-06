import unittest
from pathlib import Path
import numpy as np
from backend.results.parsers import parse_phonon_dielectric
from backend.compiler.calculation_compiler import CalculationCompiler
from backend.core.calculation_request import CalculationRequest

class E3DDielectricTests(unittest.TestCase):
    def test_real_qe_lperm_result_has_static_sum_and_excludes_acoustic(self):
        result=parse_phonon_dielectric("/tmp/e3d_mgo_lperm.out", activity_text=Path("/tmp/e3d_mgo_lperm.stdout").read_text())
        self.assertEqual(result.result_type, "PhononDielectricResult")
        np.testing.assert_allclose(result.arrays["epsilon_static"], result.arrays["epsilon_infinity"] + result.arrays["epsilon_ionic"])
        self.assertEqual(result.arrays["included_mode_mask"].tolist(), [False,False,False,True,True,True])
        self.assertLess(result.metadata["epsilon_ionic_sum_residual_norm"], 1e-5)

    def test_dielectric_request_has_one_shared_polar_and_analytic_gamma_tasks(self):
        structure={"atoms":[{"element":"Mg","position":[0,0,0]},{"element":"O","position":[2.105,2.105,2.105]}],"cell":[[0,2.105,2.105],[2.105,0,2.105],[2.105,2.105,0]],"pbc":[True,True,True]}
        params={"xc_functional":"pbe","spin_treatment":"SCALAR_NONSPIN","occupations":"fixed","ecutwfc":60,"ecutrho":480,"kpoints":{"mode":"automatic","mesh":[6,6,6],"shifts":[0,0,0]},"pseudopotentials":{"Mg":"Mg.UPF","O":"O.UPF"},"dielectric_phonon":{"tr2_ph":1e-12}}
        plan=CalculationCompiler(CalculationRequest(id="e3d-test",structure=structure,selected_calculations=["dielectric_phonon"],parameters=params)).compile()
        polar=[t for t in plan.tasks if t.calculation_id=="qe_polar_gamma"]; dielectric=[t for t in plan.tasks if t.metadata.get("purpose")=="phonon_dielectric"]
        self.assertEqual(len(polar),1); self.assertEqual(len(dielectric),1); self.assertEqual(dielectric[0].parameters["direction"],[0.0,0.0,0.0])

if __name__ == "__main__": unittest.main()
