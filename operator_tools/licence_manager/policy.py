"""Entitlement profiles derived from the canonical public catalogue and backend registry."""
from __future__ import annotations

from dataclasses import dataclass

from backend.calculations import registry
from frontend.calculations.catalog import CALCULATIONS
from frontend.calculations.reconciliation import ExecutionSupport, reconcile_catalog
from backend.licensing.plans import CORE_FEATURES
from .models import Profile


@dataclass(frozen=True)
class Entitlements:
    features: tuple[str, ...]
    calculations: tuple[str, ...]
    ready_count: int
    partial_count: int
    excluded_planned_count: int
    external_count: int


def derive_profile(profile: Profile | str) -> Entitlements:
    selected = Profile(profile)
    report = reconcile_catalog(CALCULATIONS, registry, strict=True)
    ready = tuple(sorted(d.id for d in report.descriptors if d.execution_support is ExecutionSupport.IMPLEMENTED))
    executable_partial = tuple(sorted(d.id for d in report.descriptors if d.execution_support is ExecutionSupport.PARTIAL and d.backend_supported))
    if selected is Profile.PROFESSOR_BETA:
        calculations = ready
    else:
        calculations = tuple(sorted((*ready, *executable_partial)))
    return Entitlements(tuple(sorted(CORE_FEATURES | {"workspace:device_builder"})), tuple("calc:" + item for item in calculations), len(ready), len(executable_partial), len(report.planned_ids), sum(d.execution_support is ExecutionSupport.EXTERNAL_BACKEND_REQUIRED for d in report.descriptors))
