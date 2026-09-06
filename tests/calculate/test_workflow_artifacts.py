import tempfile
import unittest
from pathlib import Path

from backend.core.execution_contract import CommandSpec, ExecutionMode
from backend.execution.artifacts import ArtifactError, ArtifactRegistry, ArtifactResolver, MaterializationPolicy, TaskArtifactDeclaration
from backend.execution.generated import GeneratedTask, GeneratedWorkflow


def task(task_id, directory, *, dependencies=(), declarations=(), requirements=()):
    return GeneratedTask(task_id, task_id, "test", "tool", directory,
        CommandSpec("tool", execution_mode=ExecutionMode.SUBPROCESS), dependencies=dependencies,
        artifact_declarations=tuple(declarations), artifact_requirements=tuple(requirements))


class WorkflowArtifactTests(unittest.TestCase):
    def test_register_and_materialize_hashed_file(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value); (root / "producer").mkdir(); (root / "consumer").mkdir()
            source = root / "producer" / "seed.nnkp"; source.write_text("contents")
            producer = task("producer", "producer", declarations=({"logical_name":"WANNIER_NNKP","relative_path":"seed.nnkp","artifact_type":"WANNIER_NNKP"},))
            consumer = task("consumer", "consumer", dependencies=("producer",), requirements=({"logical_name":"WANNIER_NNKP","relative_path":"seed.nnkp","artifact_type":"WANNIER_NNKP","materialization_policy":"COPY"},))
            workflow = GeneratedWorkflow("request", root, (producer, consumer))
            registry = ArtifactRegistry(root, "execution"); ArtifactResolver(workflow, registry).validate(); registry.register(producer, ArtifactResolver.declarations(producer))
            ArtifactResolver(workflow, registry).materialize(consumer)
            record = registry.load()["WANNIER_NNKP"]
            self.assertEqual(record.sha256, __import__("hashlib").sha256((root / "consumer" / "seed.nnkp").read_bytes()).hexdigest())

    def test_copy_on_write_directory_isolated_from_source(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value); (root / "producer" / "state.save").mkdir(parents=True); (root / "consumer").mkdir()
            source = root / "producer" / "state.save" / "data"; source.write_text("parent")
            producer = task("producer", "producer", declarations=({"logical_name":"QE_SAVE","relative_path":"state.save","artifact_type":"QE_SAVE"},))
            consumer = task("consumer", "consumer", dependencies=("producer",), requirements=({"logical_name":"QE_SAVE","relative_path":"../qe_out/state.save","artifact_type":"QE_SAVE","materialization_policy":"COPY_ON_WRITE"},))
            (root / "qe_out").mkdir()
            workflow = GeneratedWorkflow("request", root, (producer, consumer))
            registry = ArtifactRegistry(root, "execution"); registry.register(producer, ArtifactResolver.declarations(producer))
            ArtifactResolver(workflow, registry).materialize(consumer)
            child = root / "qe_out" / "state.save" / "data"
            self.assertEqual(child.read_text(), "parent")
            child.write_text("child")
            self.assertEqual(source.read_text(), "parent")

    def test_missing_or_ambiguous_producer_is_rejected(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value); [ (root / name).mkdir() for name in ("a", "b", "c") ]
            declaration = {"logical_name":"A","relative_path":"a","artifact_type":"FILE"}
            requirement = {"logical_name":"A","relative_path":"a","artifact_type":"FILE"}
            first, second = task("a", "a", declarations=(declaration,)), task("b", "b", declarations=(declaration,))
            consumer = task("c", "c", dependencies=("a", "b"), requirements=(requirement,))
            with self.assertRaises(ArtifactError): ArtifactResolver(GeneratedWorkflow("r", root, (first, second, consumer)), ArtifactRegistry(root, "e")).validate()


    def test_hardlink_policy_isolated_for_mutable_consumers(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value); (root / "producer").mkdir(); (root / "consumer").mkdir()
            source = root / "producer" / "state.dat"; source.write_text("parent")
            producer = task("producer", "producer", declarations=({"logical_name":"STATE","relative_path":"state.dat","artifact_type":"FILE"},))
            consumer = task("consumer", "consumer", dependencies=("producer",), requirements=({"logical_name":"STATE","relative_path":"state.dat","artifact_type":"FILE","materialization_policy":"HARDLINK"},))
            workflow = GeneratedWorkflow("request", root, (producer, consumer))
            registry = ArtifactRegistry(root, "execution"); registry.register(producer, ArtifactResolver.declarations(producer))
            ArtifactResolver(workflow, registry).materialize(consumer)
            child = root / "consumer" / "state.dat"; child.write_text("child")
            self.assertEqual(source.read_text(), "parent")
