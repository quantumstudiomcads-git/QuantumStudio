import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile
import unittest
from pathlib import Path
import numpy as np
from backend.results.parsers import parse_phonon_dispersion
from backend.compiler.calculation_compiler import CalculationCompiler
from backend.core.calculation_request import CalculationRequest
from frontend.builder.brillouin_zone.path_api import recommended_band_path
from frontend.calculate.typed_parameter_controls import make_control
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QSpinBox
from backend.execution.local import _validate_qgrid_artifacts

class VibrationalE2ClosureTests(unittest.TestCase):
    def test_reciprocal_metric_distance_uses_two_pi_reciprocal_cell(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/"dispersion.freq"
            path.write_text("0 0 0\n1 2 3 4 5 6\n0.5 0 0\n1 2 3 4 5 6\n")
            result=parse_phonon_dispersion(path, cell_A=[[3,0,0],[0,4,0],[0,0,5]], branch_count=6)
            self.assertAlmostEqual(result.arrays["q_distance"][1],np.pi/3)
            self.assertEqual(result.metadata["units"]["q_distance"],"Å^-1")
    def test_qgrid_validator_requires_complete_indexed_set(self):
        with tempfile.TemporaryDirectory() as root:
            directory=Path(root); (directory/"qs.dyn0").write_text("2 2 2\n2\n")
            (directory/"qs.dyn1").write_text("q = ( 0 0 0 )\n")
            self.assertIn("missing", _validate_qgrid_artifacts(directory,{"qe_prefix":"qs","qmesh":[2,2,2]}))
            (directory/"qs.dyn2").write_text("q = ( 0 0 0 )\n")
            self.assertIsNone(_validate_qgrid_artifacts(directory,{"qe_prefix":"qs","qmesh":[2,2,2]}))
    def test_qgrid_validator_rejects_mesh_identity_mismatch(self):
        with tempfile.TemporaryDirectory() as root:
            directory=Path(root); (directory/"qs.dyn0").write_text("2 2 2\n1\n")
            (directory/"qs.dyn1").write_text("q = ( 0 0 0 )\n")
            self.assertIn("q-mesh", _validate_qgrid_artifacts(directory,{"qe_prefix":"qs","qmesh":[3,3,3]}))

    def test_primitive_fcc_si_gets_the_canonical_harmonic_path(self):
        cell=[[0,2.715,2.715],[2.715,0,2.715],[2.715,2.715,0]]
        recommendation=recommended_band_path({"cell":cell,"periodic":[True,True,True]})
        self.assertEqual(recommendation.bravais_label,"Face-centred cubic primitive")
        self.assertEqual([segment.start.label for segment in recommendation.segments]+[recommendation.segments[-1].end.label],["Γ","X","W","K","Γ","L"])
    def test_public_dos_threshold_and_mesh_reach_the_ph_task(self):
        request=CalculationRequest(structure={"cell":[[0,2.715,2.715],[2.715,0,2.715],[2.715,2.715,0]],"periodic":[True,True,True],"atoms":[{"element":"Si","x":0,"y":0,"z":0},{"element":"Si","x":1.3575,"y":1.3575,"z":1.3575}]},selected_calculations=["phonon_dos"],parameters={"accuracy":"standard","qmesh":[2,2,2],"tr2_ph":"1e-12","dos_mesh":[16,16,16],"postprocessing":True,"phonon_path":[{"label":"Γ","coordinates":[0,0,0],"points":24},{"label":"X","coordinates":[0,.5,0],"points":24}]})
        plan=CalculationCompiler(request).compile(); task=next(item for item in plan.tasks if item.semantic_task_type=="qe_ph")
        self.assertEqual(task.parameters["qmesh"],[2,2,2]); self.assertEqual(float(task.parameters["tr2_ph"]),1e-12)
        self.assertTrue(any(item.semantic_task_type=="qe_matdyn" and item.metadata.get("purpose")=="phonon_dos" for item in plan.tasks))
        self.assertFalse(any(item.metadata.get("purpose")=="phonon_dispersion" for item in plan.tasks))
    def test_dos_mesh_uses_the_shared_typed_grid_control(self):
        app=QApplication.instance() or QApplication([])
        control=make_control("dos_mesh",[16,16,16])
        self.assertTrue(hasattr(control,"_mesh_boxes")); self.assertTrue(all(isinstance(box,QSpinBox) for box in control._mesh_boxes))
        self.assertEqual([box.value() for box in control._mesh_boxes],[16,16,16])

if __name__ == "__main__": unittest.main()


class VibrationalE2UTests(unittest.TestCase):
    def _request(self, u):
        return CalculationRequest(
            id=f"e2u-{u}",
            structure={"cell":[[4,0,0],[0,4,0],[0,0,20]],"periodic":[True,True,False],"atoms":[{"element":"Ta","x":0,"y":0,"z":0},{"element":"S","x":1,"y":1,"z":2}]},
            selected_calculations=["phonon_dos"],
            parameters={
                "functional":"PBE", "spin_treatment":"COLLINEAR_SPIN",
                "starting_magnetization":{"Ta":0.5,"S":0.0},
                "occupations":"smearing", "smearing":"mv", "degauss":0.02,
                "ecutwfc":40, "ecutrho":320, "kpoints":[3,3,1],
                "qmesh":[2,2,1], "tr2_ph":1e-12, "dos_mesh":[16,16,1],
                "hubbard_projector":"atomic",
                "hubbard_terms":([] if u == 0 else [{"species":"Ta","manifold":"5d","u_eV":2.27}]),
                "phonon_path":[{"label":"Γ","coordinates":[0,0,0],"points":4},{"label":"M","coordinates":[0.5,0,0],"points":4},{"label":"Γ","coordinates":[0,0,0],"points":4}],
                "pseudopotentials":{"Ta":{"filename":"Ta.UPF","pseudo_type":"USPP"},"S":{"filename":"S.UPF","pseudo_type":"USPP"}},
            },
        )

    def test_hubbard_state_is_part_of_scf_and_phonon_signatures(self):
        u0=CalculationCompiler(self._request(0)).compile()
        u2=CalculationCompiler(self._request(2.27)).compile()
        self.assertNotEqual(u0.task_for_calculation("scf").parameter_signature, u2.task_for_calculation("scf").parameter_signature)
        self.assertNotEqual(u0.task_for_calculation("qe_ph").parameter_signature, u2.task_for_calculation("qe_ph").parameter_signature)
        self.assertEqual(u2.task_for_calculation("qe_ph").depends_on_task_ids, (u2.task_for_calculation("scf").id,))

    def test_hubbard_input_and_ordinary_phonon_contract(self):
        from backend.compiler.execution_plan import ExecutionPlan
        from backend.engines.qe import QuantumEspressoAdapter
        plan=CalculationCompiler(self._request(2.27)).compile()
        generated=QuantumEspressoAdapter().compile_plan(plan)
        scf=next(t for t in generated.tasks if t.metadata["semantic_task_type"] == "scf")
        ph=next(t for t in generated.tasks if t.metadata["semantic_task_type"] == "qe_ph")
        self.assertIn("HUBBARD (atomic)", scf.input_text)
        self.assertIn("U Ta-5d 2.27", scf.input_text)
        self.assertNotIn("epsil = .true.", ph.input_text)
        self.assertIn("nq1 = 2", ph.input_text)
        self.assertIn("nq2 = 2", ph.input_text)
        self.assertIn("nq3 = 1", ph.input_text)

    def test_low_memory_profile_changes_only_qe_solver_controls(self):
        from backend.engines.qe import QuantumEspressoAdapter
        plan=CalculationCompiler(self._request(2.27)).compile()
        standard=QuantumEspressoAdapter().compile_plan(plan)
        low=QuantumEspressoAdapter().compile_plan(plan, execution_profile="LOW_MEMORY")
        scf_standard=next(t for t in standard.tasks if t.metadata["semantic_task_type"] == "scf")
        scf_low=next(t for t in low.tasks if t.metadata["semantic_task_type"] == "scf")
        self.assertEqual(plan.task_for_calculation("scf").parameter_signature, plan.task_for_calculation("scf").parameter_signature)
        self.assertIn("diagonalization = 'cg'", scf_low.input_text)
        self.assertIn("mixing_ndim = 4", scf_low.input_text)
        self.assertIn("disk_io = 'medium'", scf_low.input_text)
        self.assertNotIn("diagonalization = 'cg'", scf_standard.input_text)
        self.assertIn("U Ta-5d 2.27", scf_low.input_text)
        self.assertIn("nspin = 2", scf_low.input_text)
        self.assertIn("ecutwfc = 40", scf_low.input_text)

    def test_qe_76_dfpt_u_restrictions_fail_during_preparation(self):
        bad=self._request(2.27)
        bad.parameters["hubbard_projector"]="ortho-atomic"
        with self.assertRaisesRegex(ValueError, "atomic"):
            CalculationCompiler(bad).compile()
        bad= self._request(2.27)
        bad.parameters["spin_treatment"]="SOC"
        bad.parameters["soc"]=True
        with self.assertRaisesRegex(ValueError, "noncollinear or SOC"):
            CalculationCompiler(bad).compile()
        bad=self._request(2.27)
        bad.parameters["hubbard_terms"]=[{"species":"Ta","manifold":"5d","u_eV":2.27},{"species":"Ta","manifold":"6s","u_eV":0.0}]
        with self.assertRaisesRegex(ValueError, "one Hubbard channel"):
            CalculationCompiler(bad).compile()

    def test_matched_harmonic_chain_has_one_scf_and_isolated_u_state(self):
        for u in (0,2.27):
            plan=CalculationCompiler(self._request(u)).compile()
            self.assertEqual(sum(t.calculation_id == "scf" for t in plan.tasks), 1)
            self.assertEqual([t.calculation_id for t in plan.tasks], ["scf","qe_ph","qe_q2r","qe_matdyn_dos"])
            q2r=plan.task_for_calculation("qe_q2r")
            self.assertEqual(q2r.parameters["zasr"], "crystal")
            self.assertEqual(q2r.depends_on_task_ids, (plan.task_for_calculation("qe_ph").id,))
            dos=plan.task_for_calculation("qe_matdyn_dos")
            self.assertEqual(dos.metadata["qmesh"], [2,2,1])
