"""Central default templates for mock/offline policy interpretation.

Server-signed grants remain authoritative.  These templates intentionally do
not encode prices and are not a production licence issuer.
"""
from __future__ import annotations

from dataclasses import dataclass

from .models import PlanId


@dataclass(frozen=True)
class PlanTemplate:
    plan_id: PlanId
    registered_device_limit: int
    concurrent_session_limit: int
    features: frozenset[str]
    calculations: frozenset[str]
    named_seats: bool = False
    included_named_seats: int = 0


CORE_FEATURES = frozenset({"workspace:builder", "workspace:calculate", "workspace:analyze", "feature:diagnostics_export"})
STUDENT_PRIMITIVES = frozenset({"calc:scf", "calc:nscf", "calc:phonons"})
ALL_READY_CALCULATIONS = frozenset({"calc:*"})


PLAN_TEMPLATES = {
    PlanId.FREE_STARTER: PlanTemplate(PlanId.FREE_STARTER, 1, 1, CORE_FEATURES, frozenset()),
    PlanId.STUDENT: PlanTemplate(PlanId.STUDENT, 1, 1, CORE_FEATURES, STUDENT_PRIMITIVES),
    PlanId.PLUS: PlanTemplate(PlanId.PLUS, 1, 1, CORE_FEATURES, ALL_READY_CALCULATIONS),
    PlanId.PLUS_TRIAL: PlanTemplate(PlanId.PLUS_TRIAL, 1, 1, CORE_FEATURES, ALL_READY_CALCULATIONS),
    PlanId.PRO: PlanTemplate(PlanId.PRO, 2, 1, CORE_FEATURES | {"workspace:device_builder"}, ALL_READY_CALCULATIONS),
    PlanId.ORGANIZATION: PlanTemplate(PlanId.ORGANIZATION, 2, 1, CORE_FEATURES | {"workspace:device_builder"}, ALL_READY_CALCULATIONS, named_seats=True, included_named_seats=5),
    PlanId.ENTERPRISE: PlanTemplate(PlanId.ENTERPRISE, 2, 1, CORE_FEATURES | {"workspace:device_builder"}, ALL_READY_CALCULATIONS, named_seats=True),
}


def plan_template(plan_id: str | PlanId) -> PlanTemplate:
    try:
        return PLAN_TEMPLATES[PlanId(plan_id)]
    except (KeyError, ValueError) as error:
        raise ValueError(f"Unknown plan identifier: {plan_id}") from error
