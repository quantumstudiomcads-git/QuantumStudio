"""Generic compatibility-backed branching of persisted workflow executions."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping


class ReuseError(ValueError):
    pass


@dataclass(frozen=True)
class ReuseBinding:
    task_id: str
    source_execution_id: str
    source_task_id: str
    artifact_ids: tuple[str, ...] = ()
    compatibility: str = ""


@dataclass(frozen=True)
class ArtifactReuseBinding:
    """One unambiguous parent artifact selected for a child requirement.

    Source selection is intentionally by declared logical identity and type,
    never by a filename or a workspace path.
    """

    child_task_id: str
    child_requirement_name: str
    child_artifact_type: str
    source_execution_id: str
    source_task_id: str
    source_logical_name: str
    source_artifact_type: str
    source_sha256: str
    compatibility_fingerprint: str
    materialization_policy: str = "REFERENCE"
    mutable_consumer: bool = False
    reuse_reason: str = "SCIENTIFICALLY_COMPATIBLE"
    @property
    def child_requirement(self) -> str:
        return self.child_requirement_name

    @property
    def artifact_type(self) -> str:
        return self.child_artifact_type

    @property
    def source_artifact_id(self) -> str:
        return self.source_logical_name


@dataclass(frozen=True)
class WorkflowReusePlan:
    parent_execution_id: str
    child_request_id: str
    branch_reason: str
    reusable_task_bindings: tuple[ReuseBinding, ...]
    invalidated_tasks: tuple[str, ...]
    evidence: Mapping[str, object] = field(default_factory=dict)
    artifact_bindings: tuple[ArtifactReuseBinding, ...] = ()

    @property
    def reused_task_ids(self):
        return tuple(item.task_id for item in self.reusable_task_bindings)

    def binding_for_requirement(self, task_id: str, logical_name: str) -> ArtifactReuseBinding:
        matches = tuple(
            item for item in self.artifact_bindings
            if item.child_task_id == task_id and item.child_requirement_name == logical_name
        )
        if len(matches) != 1:
            raise ReuseError(
                f"{task_id}: requirement {logical_name!r} has {len(matches)} reusable artifact bindings; expected one."
            )
        return matches[0]


_IDENTITY_FIELDS = {
    "scf": ("structure_fingerprint", "pseudo_sha256", "functional", "cutoffs", "spin", "charge", "scf_mesh", "occupations"),
    "electronic": ("structure_fingerprint", "pseudo_sha256", "functional", "cutoffs", "scf_mesh", "coarse_k_mesh", "nbnd"),
    "wannier": ("structure_fingerprint", "pseudo_sha256", "coarse_k_mesh", "nbnd", "num_wann", "subspace_method", "scdm_fit_identity", "wannier_engine"),
    "dfpt": ("structure_fingerprint", "pseudo_sha256", "functional", "cutoffs", "spin", "coarse_q_mesh"),
}


def _compatible(parent, child, category):
    fields = _IDENTITY_FIELDS[category]
    differences = {name: (parent.get(name), child.get(name)) for name in fields if parent.get(name) != child.get(name)}
    return not differences, differences


class ReusePlanner:
    """Build an explicit branch plan from scientific identities and task categories."""

    def plan(self, *, parent_execution_id, child_request_id, parent_identity, child_identity,
             source_tasks, branch_reason="SCIENTIFIC_CONVERGENCE", artifact_bindings: Iterable[ArtifactReuseBinding] = (), parent_artifacts=None, child_requirements=(), compatibility_fingerprint=""):
        bindings, invalidated, evidence = [], [], {}
        for task_id, source_spec in source_tasks.items():
            if isinstance(source_spec, tuple):
                category, source_task_id = source_spec
            elif isinstance(source_spec, Mapping):
                category = source_spec["category"]
                source_task_id = source_spec.get("source_task_id", task_id)
            else:
                category, source_task_id = source_spec, task_id
            compatible, differences = _compatible(parent_identity, child_identity, category)
            evidence[task_id] = {"category": category, "source_task_id": source_task_id, "compatible": compatible, "differences": differences}
            if compatible:
                bindings.append(ReuseBinding(task_id, parent_execution_id, source_task_id, compatibility=category))
            else:
                invalidated.append(task_id)
        if parent_identity.get("coarse_q_mesh") != child_identity.get("coarse_q_mesh"):
            invalidated.extend(["phonon_dataset", "epw_coarse_state", "epw_fine", "epc_result", "eliashberg_result", "tc_result"])
        artifact_bindings = tuple(artifact_bindings)
        if not artifact_bindings and parent_artifacts is not None and child_requirements:
            artifact_bindings = self.select_artifact_bindings(
                parent_execution_id=parent_execution_id, parent_artifacts=parent_artifacts,
                child_requirements=child_requirements,
                compatible_task_ids=tuple(item[0] for item in child_requirements),
                compatibility_fingerprint=compatibility_fingerprint,
            )
        seen = set()
        for binding in artifact_bindings:
            key = (binding.child_task_id, binding.child_requirement_name)
            if key in seen:
                raise ReuseError(f"Ambiguous source artifacts for child requirement {key!r}.")
            seen.add(key)
            if not binding.source_sha256:
                raise ReuseError("Artifact reuse binding must include the registered source SHA256.")
            if not binding.child_requirement_name or not binding.source_logical_name:
                raise ReuseError("Artifact reuse binding must identify both child and source artifacts.")
            if binding.source_execution_id != parent_execution_id:
                raise ReuseError("Artifact reuse binding must originate from the selected parent execution.")
        return WorkflowReusePlan(
            parent_execution_id, child_request_id, branch_reason, tuple(bindings),
            tuple(dict.fromkeys(invalidated)), evidence=evidence, artifact_bindings=artifact_bindings,
        )

    def select_artifact_bindings(self, *, parent_execution_id: str, parent_artifacts,
                                 child_requirements, compatible_task_ids, compatibility_fingerprint: str):
        """Select exactly one registered source by logical identity/type."""
        allowed = set(compatible_task_ids)
        selected = []
        for child_task_id, requirement in child_requirements:
            if child_task_id not in allowed:
                continue
            matches = [record for record in parent_artifacts.values()
                       if record.logical_name == requirement.logical_name
                       and record.artifact_type == requirement.artifact_type]
            if len(matches) != 1:
                raise ReuseError(
                    f"{child_task_id}: requirement {requirement.logical_name!r} / "
                    f"{requirement.artifact_type!r} has {len(matches)} registered parent sources."
                )
            source = matches[0]
            selected.append(ArtifactReuseBinding(
                child_task_id=child_task_id,
                child_requirement_name=requirement.logical_name,
                child_artifact_type=requirement.artifact_type,
                source_execution_id=parent_execution_id,
                source_task_id=source.producer_task_id,
                source_logical_name=source.logical_name,
                source_artifact_type=source.artifact_type,
                source_sha256=source.sha256,
                compatibility_fingerprint=compatibility_fingerprint,
                materialization_policy=requirement.materialization_policy.value,
                mutable_consumer=requirement.materialization_policy.value == "COPY_ON_WRITE",
            ))
        return tuple(selected)


def require_reusable_artifact(*, completed, registered, hash_verified, compatible):
    if not all((completed, registered, hash_verified, compatible)):
        raise ReuseError("Referenced artifact failed completion, registration, hash, or compatibility validation.")
