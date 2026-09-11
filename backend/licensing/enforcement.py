"""Non-visual authorization boundary for calculation workflow preparation."""
from __future__ import annotations

from .models import ImplementationState, LicenseDecision


class EntitlementDenied(RuntimeError):
    def __init__(self, decision: LicenseDecision):
        self.decision = decision
        detail = decision.remediation or decision.reason.value.replace("_", " ")
        super().__init__(f"{decision.feature_id}: {detail}")


def implementation_state_from_catalog(status: str, *, executable_while_partial: bool = False) -> ImplementationState:
    status = str(status).lower()
    if status == "ready" or (status == "partial" and executable_while_partial):
        return ImplementationState.READY
    if status == "partial":
        return ImplementationState.PARTIAL
    if status == "planned":
        return ImplementationState.PLANNED
    return ImplementationState.UNSUPPORTED


class CalculationAuthorizationBoundary:
    """Checks all selected public intents before any workflow compiler is called."""
    def __init__(self, licensing_service):
        self.licensing_service = licensing_service

    def authorize(self, descriptors) -> tuple[LicenseDecision, ...]:
        decisions = []
        for descriptor in descriptors:
            state = implementation_state_from_catalog(
                descriptor.info.status,
                executable_while_partial=descriptor.info.executable_while_partial,
            )
            decision = self.licensing_service.authorize_calculation(descriptor.id, state)
            decisions.append(decision)
            if not decision.allowed:
                raise EntitlementDenied(decision)
        return tuple(decisions)
