"""B5 workflow-local QE pseudopotential materialization regressions."""
from __future__ import annotations

import hashlib
import re
import sys
import tempfile
import unittest
from pathlib import Path

import backend.calculations  # noqa: F401
from backend.compiler.calculation_compiler import CalculationCompiler
from backend.core.calculation_request import CalculationRequest
from backend.engines.qe import InvalidQEParameterError, QuantumEspressoAdapter
from backend.engines.qe.materialization import PseudopotentialMaterializationError
from backend.execution import LocalExecutionManager, LocalToolConfiguration, normalize_adapter_tasks


def write_pseudo(root: Path, element: str, suffix: str = "") -> Path:
    payload = f'<UPF version="2"><PP_HEADER element="{element}" functional="PBE" pseudo_type="NC" relativistic="scalar-relativistic"/></UPF>{suffix}'
    path = root / f"{element}.UPF"
    path.write_text(payload, encoding="utf-8")
    return path


def make_plan(root: Path, elements: tuple[str, ...]):
    atoms = [{"element": element, "x": float(index), "y": 0.0, "z": 0.0} for index, element in enumerate(elements)]
    pseudos, sources = {}, {}
    for element in elements:
        source = write_pseudo(root, element)
        sources[element] = source
        pseudos[element] = {"filename": source.name, "source": str(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "functional": "PBE"}
    request = CalculationRequest(id="b5", structure={"name": "B5", "atoms": atoms, "cell": [[5, 0, 0], [0, 5, 0], [0, 0, 5]], "periodic": [True, True, True]}, selected_calculations=["scf"], parameters={"pseudopotentials": pseudos, "xc_functional": "pbe"})
    return CalculationCompiler(request).compile(), sources


class WorkflowPseudoMaterializationTests(unittest.TestCase):
    def test_copy_relative_path_and_multi_species(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); plan, sources = make_plan(root, ("Si", "O"))
            output = QuantumEspressoAdapter().write_plan(plan, root / "workflows")
            pseudo_root = output / "pseudos"
            self.assertEqual({path.name for path in pseudo_root.iterdir()}, {"Si.UPF", "O.UPF"})
            input_text = (output / "001_scf" / "scf.in").read_text(encoding="utf-8")
            pseudo_dir = re.search(r"pseudo_dir = '([^']+)'", input_text).group(1)
            self.assertEqual((output / "001_scf" / pseudo_dir).resolve(), pseudo_root.resolve())
            for source in sources.values():
                self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), hashlib.sha256((pseudo_root / source.name).read_bytes()).hexdigest())
            manifest = __import__("json").loads((output / "manifest.json").read_text())
            self.assertEqual(set(manifest["materialized_pseudopotentials"]), {"Si", "O"})

    def test_missing_or_changed_source_rejects_transactionally(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); plan, sources = make_plan(root, ("Si",)); sources["Si"].unlink()
            with self.assertRaises(PseudopotentialMaterializationError):
                QuantumEspressoAdapter().write_plan(plan, root / "workflows")
            self.assertFalse((root / "workflows" / "b5").exists())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); plan, sources = make_plan(root, ("Si",)); write_pseudo(sources["Si"].parent, "Si", "changed")
            with self.assertRaises(InvalidQEParameterError):
                QuantumEspressoAdapter().write_plan(plan, root / "workflows")

    def test_preflight_catches_deleted_workflow_pseudo(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); plan, _ = make_plan(root, ("Si",)); adapter = QuantumEspressoAdapter()
            output = adapter.write_plan(plan, root / "workflows")
            (output / "pseudos" / "Si.UPF").unlink()
            workflow = normalize_adapter_tasks("b5", output, adapter.tasks_from_manifest(output))
            errors = LocalExecutionManager(LocalToolConfiguration(tool_paths={"pw.x": sys.executable})).preflight(workflow)
            self.assertIn("Generated pseudopotential file is missing: Si.UPF", errors)
            adapter.materialize_existing_workflow(output)
            self.assertFalse(LocalExecutionManager(LocalToolConfiguration(tool_paths={"pw.x": sys.executable})).preflight(workflow))


if __name__ == "__main__":
    unittest.main()
