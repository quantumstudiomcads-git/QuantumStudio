"""Quantum ESPRESSO C4 adapter: plan translation, preview, and export only."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Mapping

from backend.engines.base import EngineAdapter
from backend.engines.qe.models import (
    InvalidQEParameterError,
    MissingPseudopotentialError,
    QEGeneration,
    QEInputGenerationError,
    QEOutputExistsError,
    QETaskInput,
    QEWorkflowContext,
    PseudopotentialSelection,
    UnsupportedQECalculationError,
)
from backend.engines.qe.writer import phonon_input, pw_input
from backend.engines.qe.postprocessing import post_input, pw_bands_input
from backend.pseudopotentials import PseudoSet, Relativity, inspect_upf, validate_pseudo_set


ENGINE_ID = "quantum_espresso"
SUPPORTED_CALCULATIONS = frozenset({"scf", "relax", "vc_relax", "phonons", "qe_pw_bands", "qe_pw_nscf", "qe_bands", "qe_dos", "qe_projwfc", "qe_pp", "qe_ph", "qe_q2r", "qe_matdyn", "qe_matdyn_dos", "qe_pw_nscf_dos", "qe_pw_nscf_pdos", "qe_bands", "qe_dos", "qe_projwfc", "qe_pp", "qe_q2r", "qe_ph", "qe_pw_bands"})
DEFERRED_CALCULATIONS = {
    "bands": "C3 has no reliable explicit band-path model; C4 will not guess a path.",
    "dos": "C3 lacks an explicit NSCF -> dos.x workflow stage required for scientifically sound DOS input.",
    "pdos": "C3 lacks explicit NSCF and projwfc.x stages required for projected DOS input.",
    "charge_density": "C3 has no explicit pp.x post-processing task model.",
    "spin_density": "C3 has no explicit pp.x post-processing task model.",
    "phonon_dos": "C3 has no q2r.x/matdyn.x stages required to generate phonon DOS safely.",
    "dielectric": "C3 does not yet define the QE response workflow required for dielectric input.",
    "absorption": "C3 does not yet define the QE response workflow required for absorption input.",
}


def _safe_identifier(value: object, fallback: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_]+", "_", str(value)).strip("_").lower()
    return token or fallback


def structure_fingerprint(structure: Mapping[str, object]) -> str:
    """Hash only scientific geometry, not names, history, or Python identities."""
    payload = {
        "atoms": structure.get("atoms", []),
        "cell": structure.get("cell", []),
        "periodic": structure.get("periodic", []),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class QuantumEspressoAdapter(EngineAdapter):
    """Derive validated QE input files from a C3 ExecutionPlan.

    The adapter knows no Project or Qt state.  It requires explicit logical
    pseudo assignments and accepts runtime-only ``pseudo_dir`` configuration.
    """

    engine_id = ENGINE_ID

    def __init__(self, pseudopotentials: Mapping[str, object] | None = None, *, pseudo_dir: str = "../pseudos"):
        if not isinstance(pseudo_dir, str) or not pseudo_dir.strip():
            raise InvalidQEParameterError("QE pseudo_dir must be a non-empty runtime path.")
        self._pseudo_values = dict(pseudopotentials or {})
        self.pseudo_dir = pseudo_dir

    @classmethod
    def support_reason(cls, calculation_id: str) -> str | None:
        if calculation_id in SUPPORTED_CALCULATIONS:
            return None
        return DEFERRED_CALCULATIONS.get(calculation_id, "No C4 Quantum ESPRESSO writer is defined for this calculation.")

    @classmethod
    def is_supported(cls, calculation_id: str) -> bool:
        return cls.support_reason(calculation_id) is None

    def _context_for(self, plan) -> QEWorkflowContext:
        request_token = _safe_identifier(plan.calculation_id, "request")
        prefix = f"qs_{request_token[:16]}"
        return QEWorkflowContext(
            request_id=plan.calculation_id,
            prefix=prefix,
            outdir="../qe_out",
            pseudo_dir=self.pseudo_dir,
        )

    def _pseudopotentials_for(self, structure: Mapping[str, object], plan) -> dict[str, PseudopotentialSelection]:
        parameter_values = plan.parameters.get("pseudopotentials", {}) if isinstance(plan.parameters, dict) else {}
        if parameter_values is not None and not isinstance(parameter_values, Mapping):
            raise InvalidQEParameterError("Request pseudopotentials must be an element-to-assignment mapping.")
        merged = dict(parameter_values or {})
        merged.update(self._pseudo_values)
        elements = []
        for atom in structure.get("atoms", []):
            element = str(atom.get("element", "")).strip() if isinstance(atom, Mapping) else ""
            if element and element not in elements:
                elements.append(element)
        selections: dict[str, PseudopotentialSelection] = {}
        for element in elements:
            if element not in merged:
                raise MissingPseudopotentialError(f"Missing pseudopotential assignment for element {element!r}.")
            selection = PseudopotentialSelection.from_value(element, merged[element])
            if selection.element != element:
                raise InvalidQEParameterError(
                    f"Pseudopotential assignment for {element!r} declares contradictory element {selection.element!r}."
                )
            selections[element] = selection
        return selections

    def _pseudo_provenance(self, pseudos):
        provenance = {}
        records = {}
        for element, selection in pseudos.items():
            entry = selection.provenance()
            candidate = Path(selection.source) if selection.source else Path(selection.filename)
            if not candidate.is_file():
                configured = Path(self.pseudo_dir) / selection.filename
                if configured.is_file(): candidate = configured
            if candidate.is_file():
                record = inspect_upf(candidate, selection.library_id or "local", selection.library_version or "")
                records[element] = record
                entry.update({"source": record.path, "sha256": record.sha256, "xc_functional": record.xc_functional, "pseudo_type": record.pseudo_type.value, "relativity": record.relativity.value})
            provenance[element] = entry
        return provenance, records

    def _validate_pseudo_compatibility(self, plan, pseudos):
        provenance, records = self._pseudo_provenance(pseudos)
        if records:
            functional = plan.parameters.get("xc_functional", plan.parameters.get("functional", "pbe"))
            spin = plan.parameters.get("spin", {}) if isinstance(plan.parameters, Mapping) else {}
            soc = bool(plan.parameters.get("soc", False) or (isinstance(spin, Mapping) and spin.get("soc", False)))
            missing, findings = validate_pseudo_set(functional, soc, records.keys(), PseudoSet(records))
            if missing: raise MissingPseudopotentialError("Missing pseudopotential metadata for: " + ", ".join(missing))
            mismatches = [element for element, finding in findings.items() if finding.state.value == "WARNING_XC_MISMATCH"]
            if mismatches: raise InvalidQEParameterError("Selected pseudopotential XC is incompatible for: " + ", ".join(mismatches))
            if soc and not any(record.relativity is Relativity.FULLY_RELATIVISTIC for record in records.values()):
                raise InvalidQEParameterError("SOC requires at least one fully relativistic pseudopotential with spin-orbit information.")
        return provenance

    def validate_plan(self, plan) -> None:
        if not hasattr(plan, "tasks") or not hasattr(plan, "structure"):
            raise InvalidQEParameterError("QuantumEspressoAdapter requires an ExecutionPlan.")
        if not isinstance(plan.structure, Mapping):
            raise InvalidQEParameterError("ExecutionPlan structure must be a serialized request snapshot.")
        unsupported = [task.calculation_id for task in plan.tasks if not self.is_supported(task.calculation_id)]
        if unsupported:
            details = "; ".join(f"{item}: {self.support_reason(item)}" for item in unsupported)
            raise UnsupportedQECalculationError("QE input generation is deferred: " + details)
        pseudos = self._pseudopotentials_for(plan.structure, plan)
        self._validate_pseudo_compatibility(plan, pseudos)

    def compile_plan(self, plan) -> QEGeneration:
        self.validate_plan(plan)
        context = self._context_for(plan)
        pseudos = self._pseudopotentials_for(plan.structure, plan)
        pseudo_provenance = self._validate_pseudo_compatibility(plan, pseudos)
        qe_tasks: list[QETaskInput] = []
        for index, task in enumerate(plan.tasks, start=1):
            parameters = dict(task.parameters)
            if task.calculation_id in {"scf", "relax", "vc_relax"}:
                input_text = pw_input(task.calculation_id, parameters, plan.structure, context, pseudos)
                executable, input_filename = "pw.x", f"{task.calculation_id}.in"
            elif task.semantic_task_type == "qe_pw_bands":
                input_text, executable, input_filename = pw_bands_input(parameters, plan.structure, context, pseudos), "pw.x", "bands_pw.in"
            elif task.semantic_task_type == "qe_pw_nscf":
                input_text, executable, input_filename = pw_input("qe_pw_nscf", parameters, plan.structure, context, pseudos), "pw.x", "nscf.in"
            elif task.semantic_task_type in {"qe_bands","qe_dos","qe_projwfc","qe_pp","qe_q2r","qe_matdyn"}:
                input_text, executable, input_filename = post_input(task.semantic_task_type, parameters, context), {"qe_bands":"bands.x","qe_dos":"dos.x","qe_projwfc":"projwfc.x","qe_pp":"pp.x","qe_q2r":"q2r.x","qe_matdyn":"matdyn.x"}[task.semantic_task_type], task.semantic_task_type.removeprefix("qe_") + ".in"
            elif task.semantic_task_type == "qe_ph":
                input_text, executable, input_filename = phonon_input(parameters, context), "ph.x", "phonons.in"
            elif task.calculation_id == "phonons":
                input_text = phonon_input(parameters, context)
                executable, input_filename = "ph.x", "phonons.in"
            else:  # validate_plan makes this branch defensive only.
                raise UnsupportedQECalculationError(self.support_reason(task.calculation_id) or task.calculation_id)
            directory = f"{index:03d}_{_safe_identifier(task.calculation_id, 'task')}"
            qe_tasks.append(QETaskInput(
                task_id=task.id, calculation_id=task.calculation_id, executable=executable,
                input_filename=input_filename, output_filename=input_filename.removesuffix(".in") + ".out",
                working_directory=directory, input_text=input_text,
                depends_on_task_ids=tuple(task.depends_on_task_ids),
                metadata={"engine_id":task.engine_id,"semantic_task_type":task.semantic_task_type,"parameter_signature":task.parameter_signature,"artifact_inputs":list(task.artifact_inputs),"artifact_outputs":list(task.artifact_outputs),"qe_prefix": context.prefix, "qe_outdir": context.outdir, "structure_fingerprint": structure_fingerprint(plan.structure), "pseudopotentials": pseudo_provenance, "task_metadata": task.metadata},
            ))
        manifest = {
            "engine_id": self.engine_id,
            "request_id": plan.calculation_id,
            "structure_fingerprint": structure_fingerprint(plan.structure),
            "workflow_context": {"prefix": context.prefix, "outdir": context.outdir, "pseudo_dir": context.pseudo_dir},
            "pseudopotentials": pseudo_provenance,
            "tasks": [
                {"task_id": task.task_id, "calculation_id": task.calculation_id, "dependencies": list(task.depends_on_task_ids), "executable": task.executable, "input_filename": task.input_filename, "output_filename": task.output_filename, "working_directory": task.working_directory, "metadata": task.metadata}
                for task in qe_tasks
            ],
        }
        return QEGeneration(self.engine_id, context, tuple(qe_tasks), manifest)

    def write_plan(self, plan, output_root, *, overwrite: bool = False) -> Path:
        """Write an all-or-nothing derived export; existing request exports are refused.

        ``overwrite`` is deliberately rejected in C4: ownership-safe replacement
        needs executor-era provenance rather than recursive deletion.
        """
        if overwrite:
            raise QEOutputExistsError("C4 does not overwrite existing QE input exports; choose a new output root.")
        generation = self.compile_plan(plan)
        root = Path(output_root).expanduser()
        if root.exists() and not root.is_dir():
            raise QEInputGenerationError(f"QE output root is not a directory: {root}")
        root.mkdir(parents=True, exist_ok=True)
        destination = root / _safe_identifier(plan.calculation_id, "request")
        if destination.exists():
            raise QEOutputExistsError(f"QE output already exists for this request: {destination}")
        staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.staging-", dir=root))
        try:
            for task in generation.tasks:
                task_dir = staging / task.working_directory
                task_dir.mkdir()
                (task_dir / task.input_filename).write_text(task.input_text, encoding="utf-8")
            (staging / "manifest.json").write_text(
                json.dumps(generation.manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            os.replace(staging, destination)
        except Exception:
            # Staging is local, newly created, and never the user-selected root.
            for child in sorted(staging.rglob("*"), reverse=True):
                if child.is_file() or child.is_symlink():
                    child.unlink()
                elif child.is_dir():
                    child.rmdir()
            if staging.exists():
                staging.rmdir()
            raise
        return destination
