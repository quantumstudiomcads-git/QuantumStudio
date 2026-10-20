"""Central entitlement policy; implementation readiness always precedes plans."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from .models import DecisionReason, DeviceLease, EntitlementState, ImplementationState, LicenseDecision


def calculation_feature(calculation_id: str) -> str:
    return "calc:" + str(calculation_id)


class EntitlementPolicy:
    def __init__(self, lease: DeviceLease | None = None, *, now: Callable[[], int] | None = None, clock_validation_required: bool = False):
        self.lease = lease
        self._now = now or (lambda: int(datetime.now(timezone.utc).timestamp()))
        self.clock_validation_required = clock_validation_required

    def authorize_read(self, feature_id: str = "data:read") -> LicenseDecision:
        """Projects/results remain readable even after an entitlement expires."""
        return LicenseDecision(True, DecisionReason.ALLOWED, ImplementationState.READY, EntitlementState.INCLUDED, feature_id, self.lease.plan_id if self.lease else None)

    def authorize_feature(self, feature_id: str, *, implementation_state: ImplementationState = ImplementationState.READY) -> LicenseDecision:
        if implementation_state is not ImplementationState.READY:
            return LicenseDecision(False, DecisionReason.NOT_IMPLEMENTED, implementation_state, EntitlementState.UNAVAILABLE, feature_id, remediation="This capability is not implemented in this product build.")
        state = self._lease_state(feature_id)
        if state is not None:
            return state
        assert self.lease is not None
        grants = set(self.lease.feature_entitlements)
        allowed = feature_id in grants or "feature:*" in grants
        return LicenseDecision(allowed, DecisionReason.ALLOWED if allowed else DecisionReason.NOT_ENTITLED, ImplementationState.READY, self._entitlement_kind(), feature_id, self.lease.plan_id, self.lease.expires_at, "Refresh your licence or use a plan that includes this capability." if not allowed else "")

    def authorize_calculation(self, calculation_id: str, implementation_state: ImplementationState) -> LicenseDecision:
        feature_id = calculation_feature(calculation_id)
        if implementation_state is not ImplementationState.READY:
            return LicenseDecision(False, DecisionReason.NOT_IMPLEMENTED, implementation_state, EntitlementState.UNAVAILABLE, feature_id, self.lease.plan_id if self.lease else None, remediation="This calculation is not ready in Quantum Studio.")
        state = self._lease_state(feature_id)
        if state is not None:
            return state
        assert self.lease is not None
        grants = set(self.lease.calculation_entitlements)
        allowed = feature_id in grants or "calc:*" in grants
        return LicenseDecision(allowed, DecisionReason.ALLOWED if allowed else DecisionReason.NOT_ENTITLED, ImplementationState.READY, self._entitlement_kind(), feature_id, self.lease.plan_id, self.lease.expires_at, "Refresh your licence or choose a plan that includes this calculation." if not allowed else "")

    def validity_decision(self) -> LicenseDecision:
        """Public validity check using the same policy as every feature gate."""
        denied = self._lease_state("licence:validity")
        if denied is not None:
            return denied
        return LicenseDecision(True, DecisionReason.ALLOWED, ImplementationState.READY,
                               self._entitlement_kind(), "licence:validity", self.lease.plan_id, self.lease.expires_at)

    def _lease_state(self, feature_id: str) -> LicenseDecision | None:
        if self.lease is None:
            return LicenseDecision(False, DecisionReason.AUTH_REQUIRED, ImplementationState.READY, EntitlementState.AUTH_REQUIRED, feature_id, remediation="Sign in and refresh a valid Quantum Studio licence.")
        now = self._now()
        if self.clock_validation_required:
            return LicenseDecision(False, DecisionReason.CLOCK_VALIDATION_REQUIRED, ImplementationState.READY, EntitlementState.CLOCK_VALIDATION_REQUIRED, feature_id, self.lease.plan_id, self.lease.expires_at, "Reconnect to validate the system clock and refresh the licence.")
        if now < self.lease.not_before:
            return LicenseDecision(False, DecisionReason.LICENCE_INVALID, ImplementationState.READY, EntitlementState.INVALID, feature_id, self.lease.plan_id, self.lease.expires_at, "This licence is not valid yet.")
        if now > self.lease.expires_at:
            reason = DecisionReason.TRIAL_EXPIRED if self.lease.trial_type else DecisionReason.SUBSCRIPTION_EXPIRED
            return LicenseDecision(False, reason, ImplementationState.READY, EntitlementState.EXPIRED, feature_id, self.lease.plan_id, self.lease.expires_at, "Refresh or renew the licence. Existing projects and results remain available.")
        if self.lease.offline_until is not None and now > self.lease.offline_until:
            return LicenseDecision(False, DecisionReason.OFFLINE_LEASE_EXPIRED, ImplementationState.READY, EntitlementState.EXPIRED, feature_id, self.lease.plan_id, self.lease.expires_at, "Reconnect to refresh the offline licence lease.")
        return None

    def _entitlement_kind(self) -> EntitlementState:
        return EntitlementState.TRIAL if self.lease and self.lease.trial_type else EntitlementState.INCLUDED
