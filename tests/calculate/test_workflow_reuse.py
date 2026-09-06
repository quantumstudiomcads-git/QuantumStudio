import tempfile
import unittest
from pathlib import Path

from backend.execution.reuse import ArtifactReuseBinding, ReuseError, ReusePlanner, require_reusable_artifact


class WorkflowReuseTests(unittest.TestCase):
    def setUp(self):
        self.parent = {"structure_fingerprint":"s", "pseudo_sha256":"p", "functional":"pbe", "cutoffs":(60,240), "spin":"scalar", "charge":0, "scf_mesh":(8,8,8), "occupations":"mp:.04", "coarse_k_mesh":(12,12,12), "coarse_q_mesh":(3,3,3), "nbnd":14, "num_wann":9, "subspace_method":"SCDM_ERFC", "scdm_fit_identity":"fit", "wannier_engine":"QE_EP6/W90-3.1"}

    def test_q_change_reuses_electronic_and_wannier_but_invalidates_phonon(self):
        child = {**self.parent, "coarse_q_mesh":(6,6,6)}
        plan = ReusePlanner().plan(parent_execution_id="p", child_request_id="c", parent_identity=self.parent, child_identity=child, source_tasks={"scf":"scf", "electronic":"electronic", "wannier":"wannier", "dfpt":"dfpt"})
        self.assertEqual(set(plan.reused_task_ids), {"scf", "electronic", "wannier"})
        self.assertIn("dfpt", plan.invalidated_tasks)
        self.assertIn("epw_coarse_state", plan.invalidated_tasks)

    def test_scientific_change_rejects_scf_reuse(self):
        child = {**self.parent, "pseudo_sha256":"changed"}
        plan = ReusePlanner().plan(parent_execution_id="p", child_request_id="c", parent_identity=self.parent, child_identity=child, source_tasks={"scf":"scf"})
        self.assertEqual(plan.reused_task_ids, ())
        self.assertFalse(plan.evidence["scf"]["compatible"])

    def test_artifact_selection_is_logical_and_unambiguous(self):
        from types import SimpleNamespace
        parent_artifacts = {
            "QE_SAVE": SimpleNamespace(logical_name="QE_SAVE", artifact_type="QE_SAVE", producer_task_id="scf", sha256="abc"),
        }
        requirement = SimpleNamespace(logical_name="QE_SAVE", artifact_type="QE_SAVE", materialization_policy=SimpleNamespace(value="COPY_ON_WRITE"))
        bindings = ReusePlanner().select_artifact_bindings(
            parent_execution_id="p", parent_artifacts=parent_artifacts,
            child_requirements=(("ph", requirement),), compatible_task_ids=("ph",), compatibility_fingerprint="ham",
        )
        self.assertEqual(bindings[0].source_logical_name, "QE_SAVE")
        self.assertEqual(bindings[0].materialization_policy, "COPY_ON_WRITE")

    def test_artifact_binding_rejects_ambiguous_sources(self):
        from types import SimpleNamespace
        record = SimpleNamespace(logical_name="QE_SAVE", artifact_type="QE_SAVE", producer_task_id="scf", sha256="abc")
        requirement = SimpleNamespace(logical_name="QE_SAVE", artifact_type="QE_SAVE", materialization_policy=SimpleNamespace(value="COPY"))
        with self.assertRaises(ReuseError):
            ReusePlanner().select_artifact_bindings(
                parent_execution_id="p", parent_artifacts={"one": record, "two": record},
                child_requirements=(("ph", requirement),), compatible_task_ids=("ph",), compatibility_fingerprint="ham",
            )

    def test_branch_realizes_qe_save_as_isolated_reference(self):
        from backend.core.execution_contract import CommandSpec, ExecutionMode
        from backend.execution.artifacts import ArtifactRegistry
        from backend.execution.branch import BranchExecutionBuilder
        from backend.execution.generated import GeneratedTask, GeneratedWorkflow
        from backend.execution.models import TaskState
        from backend.execution.persistence import ExecutionStore

        with tempfile.TemporaryDirectory() as value:
            root = Path(value); parent_root = root / "parent"; target_root = root / "target"; child_root = root / "child"
            for directory in (parent_root / "scf", target_root / "scf", target_root / "ph"):
                directory.mkdir(parents=True, exist_ok=True)
            save = parent_root / "qe_out" / "pb.save"; save.mkdir(parents=True); (save / "data").write_text("accepted")
            (parent_root / "manifest.json").write_text('{"request_id":"parent"}')
            (parent_root / "scf" / "scf.in").write_text("scf")
            (target_root / "scf" / "scf.in").write_text("scf")
            (target_root / "ph" / "ph.in").write_text("ph")
            (target_root / "manifest.json").write_text('{"request_id":"q6"}')
            command = CommandSpec("tool", execution_mode=ExecutionMode.SUBPROCESS)
            scf = GeneratedTask("scf", "scf", "test", "tool", "scf", command, input_files=("scf.in",), artifact_declarations=({"logical_name":"QE_SAVE","relative_path":"../qe_out/pb.save","artifact_type":"QE_SAVE"},))
            ph = GeneratedTask("ph", "qe_ph_epw", "test", "tool", "ph", command, dependencies=("scf",), input_files=("ph.in",), artifact_requirements=({"logical_name":"QE_SAVE","relative_path":"../qe_out/pb.save","artifact_type":"QE_SAVE","materialization_policy":"COPY_ON_WRITE"},))
            parent_workflow = GeneratedWorkflow("parent", parent_root, (scf,))
            parent_store = ExecutionStore(parent_root); parent_record = parent_store.create(parent_workflow)
            parent_record.tasks["scf"].state = TaskState.COMPLETED; parent_store.save(parent_record)
            parent_registry = ArtifactRegistry(parent_root, parent_record.execution_id)
            parent_registry.register_external(logical_name="QE_SAVE", artifact_type="QE_SAVE", producer_task_id="scf", source_path=save, relative_path="../qe_out/pb.save", compatibility_fingerprint="ham")
            target = GeneratedWorkflow("q6", target_root, (scf, ph))
            binding = ArtifactReuseBinding("ph", "QE_SAVE", "QE_SAVE", parent_record.execution_id, "scf", "QE_SAVE", "QE_SAVE", parent_registry.load()["QE_SAVE"].sha256, "ham", "COPY_ON_WRITE", True)
            plan = ReusePlanner().plan(parent_execution_id=parent_record.execution_id, child_request_id="q6", parent_identity=self.parent, child_identity=self.parent, source_tasks={"scf":("scf", "scf")}, artifact_bindings=(binding,))
            child_workflow, child_record, child_registry = BranchExecutionBuilder().create(target, plan, parent_record, parent_registry, branch_root=child_root)
            self.assertEqual(child_record.tasks["scf"].state, TaskState.COMPLETED)
            self.assertEqual(child_record.tasks["scf"].completion_origin, "REUSED_ARTIFACT")
            self.assertEqual(child_registry.load()["QE_SAVE"].origin, "REFERENCE")
            materialized = child_root / "qe_out" / "pb.save" / "data"
            self.assertEqual(materialized.read_text(), "accepted")
            materialized.write_text("child")
            self.assertEqual((save / "data").read_text(), "accepted")
            reloaded = ExecutionStore(child_root).load(child_record.execution_id)
            self.assertEqual(reloaded.parent_execution_id, parent_record.execution_id)
            self.assertEqual(reloaded.tasks["scf"].completion_origin, "REUSED_ARTIFACT")

    def test_plan_rejects_duplicate_child_requirement_bindings(self):
        binding = ArtifactReuseBinding("ph", "QE_SAVE", "QE_SAVE", "p", "scf", "QE_SAVE", "QE_SAVE", "a", "h")
        with self.assertRaises(ReuseError):
            ReusePlanner().plan(
                parent_execution_id="p", child_request_id="c", parent_identity=self.parent, child_identity=self.parent,
                source_tasks={"scf":"scf"}, artifact_bindings=(binding, binding),
            )

    def test_referenced_artifact_requires_all_guards(self):
        require_reusable_artifact(completed=True, registered=True, hash_verified=True, compatible=True)
        with self.assertRaises(ReuseError):
            require_reusable_artifact(completed=True, registered=True, hash_verified=False, compatible=True)
