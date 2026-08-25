"""Cross-engine C5A adapter for public Wannierization plans; generation only."""
from __future__ import annotations
import json, os, tempfile
from pathlib import Path
from backend.engines.qe.adapter import QuantumEspressoAdapter, _safe_identifier, structure_fingerprint
from backend.engines.qe.models import QEInputGenerationError, QEOutputExistsError, QETaskInput
from backend.engines.qe.writer import pw_input
from backend.engines.wannier90.models import WannierInputSettings
from backend.engines.wannier90.writer import pw2wannier90_input, win_input

class Wannier90WorkflowAdapter:
    engine_id = "wannier90"
    def __init__(self, pseudopotentials=None, *, pseudo_dir="../pseudos"):
        self.qe = QuantumEspressoAdapter(pseudopotentials, pseudo_dir=pseudo_dir)
    def compile_plan(self, plan):
        if "wannierization" not in plan.selected_calculations:
            raise QEInputGenerationError("Wannier90WorkflowAdapter requires a public wannierization request.")
        context, pseudos = self.qe._context_for(plan), self.qe._pseudopotentials_for(plan.structure, plan)
        generated = []
        for index, task in enumerate(plan.tasks, 1):
            directory = f"{index:03d}_{_safe_identifier(task.semantic_task_type or task.calculation_id, 'task')}"
            if task.semantic_task_type == "scf":
                text, filename, executable = pw_input("scf", task.parameters, plan.structure, context, pseudos), "scf.in", "pw.x"
            elif task.semantic_task_type == "qe_pw_nscf":
                text, filename, executable = pw_input("qe_pw_nscf", task.parameters, plan.structure, context, pseudos), "nscf_wannier.in", "pw.x"
            elif task.semantic_task_type in {"wannier90_preprocess", "wannier90_run"}:
                settings = task.parameters["wannier"]
                text, filename, executable = win_input(settings, plan.structure), f"{task.parameters['seedname']}.win", "wannier90.x"
            elif task.semantic_task_type == "qe_pw2wannier90":
                seed = task.parameters["seedname"]
                text, filename, executable = pw2wannier90_input(context.prefix, context.outdir, seed), "pw2wannier90.in", "pw2wannier90.x"
            else:
                raise QEInputGenerationError(f"Unsupported task in Wannierization plan: {task.semantic_task_type}.")
            generated.append(QETaskInput(task.id, task.calculation_id, executable, filename, filename.removesuffix('.in') + '.out', directory, text, tuple(task.depends_on_task_ids), {"engine_id": task.engine_id, "semantic_task_type": task.semantic_task_type, "parameter_signature": task.parameter_signature, "artifact_inputs": list(task.artifact_inputs), "artifact_outputs": list(task.artifact_outputs), "command": task.metadata.get("command"), "qe_prefix": context.prefix, "qe_outdir": context.outdir}))
        manifest = {"engine_id": "multi_engine", "request_id": plan.calculation_id, "structure_fingerprint": structure_fingerprint(plan.structure), "workflow_context": {"prefix": context.prefix, "outdir": context.outdir, "pseudo_dir": context.pseudo_dir}, "tasks": [{"task_id": task.task_id, "calculation_id": task.calculation_id, "semantic_task_type": task.metadata["semantic_task_type"], "engine_id": task.metadata["engine_id"], "executable": task.executable, "dependencies": list(task.depends_on_task_ids), "artifact_inputs": task.metadata["artifact_inputs"], "artifact_outputs": task.metadata["artifact_outputs"], "input_filename": task.input_filename, "working_directory": task.working_directory} for task in generated]}
        return generated, manifest
    def write_plan(self, plan, output_root, *, overwrite=False):
        if overwrite: raise QEOutputExistsError("C5A does not overwrite existing generated workflows.")
        tasks, manifest = self.compile_plan(plan)
        root = Path(output_root); root.mkdir(parents=True, exist_ok=True); destination = root / _safe_identifier(plan.calculation_id, "request")
        if destination.exists(): raise QEOutputExistsError(f"Workflow output already exists: {destination}")
        staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.staging-", dir=root))
        try:
            for task in tasks:
                task_dir = staging / task.working_directory; task_dir.mkdir(); (task_dir / task.input_filename).write_text(task.input_text, encoding="utf-8")
            (staging / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            os.replace(staging, destination)
        except Exception:
            for child in sorted(staging.rglob("*"), reverse=True):
                child.unlink() if child.is_file() else child.rmdir()
            if staging.exists(): staging.rmdir()
            raise
        return destination
