"""Deterministic in-memory authority used only by B4 tests and local fakes."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ..models import DeviceIdentity, DeviceRegistrationRequest, DeviceRegistrationResponse, PlanId, SessionClaim
from ..plans import plan_template
from ..verifier import issue_lease
from .base import ConnectorError, LicensingConnector


class DeviceLimitReached(ConnectorError): code = "device_limit_reached"
class SessionLimitReached(ConnectorError): code = "session_limit_reached"
class TrialAlreadyConsumed(ConnectorError): code = "trial_already_consumed"


@dataclass
class _Account:
    plan_id: PlanId
    devices: dict[str, DeviceIdentity] = field(default_factory=dict)
    seats: dict[str, str] = field(default_factory=dict)


class InMemoryLicensingConnector(LicensingConnector):
    def __init__(self, *, now=lambda: 1_800_000_000, issuer: Ed25519PrivateKey | None = None, kid: str = "test-ephemeral"):
        self.now = now
        self.issuer = issuer or Ed25519PrivateKey.generate()
        self.kid = kid
        self.accounts: dict[str, _Account] = {}
        self.sessions: dict[str, SessionClaim] = {}
        self.used_trials: set[tuple[str, str]] = set()
        self._sequence = 0

    @property
    def trusted_keys(self) -> dict[str, bytes]:
        from ..verifier import public_key_bytes
        return {self.kid: public_key_bytes(self.issuer)}

    def set_plan(self, account_id: str, plan_id: str | PlanId) -> None:
        self.accounts.setdefault(account_id, _Account(PlanId(plan_id))).plan_id = PlanId(plan_id)

    def assign_seat(self, account_id: str, device_id: str, seat_id: str) -> None:
        """Deterministic named-seat fixture; organization seats are never anonymous."""
        account = self.accounts[account_id]
        if not plan_template(account.plan_id).named_seats:
            raise ValueError("Only named-seat plans may assign seats.")
        if device_id not in account.devices or not isinstance(seat_id, str) or not seat_id:
            raise ValueError("A registered device and non-empty seat ID are required.")
        if seat_id in account.seats.values() and account.seats.get(device_id) != seat_id:
            raise ValueError("A seat may be assigned to one named device identity.")
        account.seats[device_id] = seat_id

    def issue_trial_once(self, account_id: str, trial_plan: str | PlanId) -> None:
        plan = PlanId(trial_plan)
        if plan not in {PlanId.FREE_STARTER, PlanId.PLUS_TRIAL}:
            raise ValueError("Only trial plans can be issued once.")
        key = (account_id, plan.value)
        if key in self.used_trials:
            raise TrialAlreadyConsumed("This account has already consumed that trial.")
        self.used_trials.add(key)
        self.set_plan(account_id, plan)

    def register_device(self, request: DeviceRegistrationRequest) -> DeviceRegistrationResponse:
        account = self.accounts.setdefault(request.account_id, _Account(PlanId.FREE_STARTER))
        if request.device.device_id not in account.devices and len(account.devices) >= plan_template(account.plan_id).registered_device_limit:
            raise DeviceLimitReached("The registered device limit has been reached.")
        account.devices[request.device.device_id] = request.device
        return DeviceRegistrationResponse(request.device.device_id, self.refresh_device_lease(request.account_id, request.device.device_id))

    def refresh_device_lease(self, account_id: str, device_id: str) -> Mapping[str, Any]:
        account = self.accounts[account_id]
        device = account.devices[device_id]
        template = plan_template(account.plan_id)
        now = int(self.now())
        self._sequence += 1
        payload = {
            "licence_id": "lic_" + account_id, "account_id": account_id, "subject_type": "organization" if template.named_seats else "individual",
            "plan_id": account.plan_id.value, "device_id": device.device_id, "device_public_key_hash": device.public_key_hash,
            "issued_at": now, "not_before": now - 1, "expires_at": now + 7 * 24 * 60 * 60,
            "offline_until": now + 24 * 60 * 60, "entitlement_version": self._sequence,
            "feature_entitlements": sorted(template.features), "calculation_entitlements": sorted(template.calculations),
            "registered_device_limit": template.registered_device_limit, "concurrent_session_limit": template.concurrent_session_limit,
            "offline_device_limit": 1, "nonce": f"mock-{self._sequence}",
            "trial_type": account.plan_id.value if account.plan_id in {PlanId.FREE_STARTER, PlanId.PLUS_TRIAL} else None,
            "seat_id": account.seats.get(device_id), "organization_id": "org_" + account_id if template.named_seats else None,
            "seat_count": template.included_named_seats or None,
        }
        return issue_lease(payload, self.issuer, kid=self.kid)

    def get_entitlement_status(self, account_id: str, device_id: str) -> Mapping[str, Any]:
        return self.refresh_device_lease(account_id, device_id)

    def open_session(self, account_id: str, device_id: str, *, seat_id: str | None = None) -> SessionClaim:
        account = self.accounts[account_id]
        if device_id not in account.devices:
            raise ConnectorError("Device is not registered.")
        template = plan_template(account.plan_id)
        active = [claim for claim in self.sessions.values() if claim.expires_at >= int(self.now()) and claim.seat_id == seat_id]
        if len(active) >= template.concurrent_session_limit:
            raise SessionLimitReached("The concurrent-session limit has been reached.")
        self._sequence += 1
        claim = SessionClaim(f"session-{self._sequence}", device_id, seat_id, int(self.now()) + 3600)
        self.sessions[claim.session_id] = claim
        return claim

    def refresh_session(self, session_id: str) -> SessionClaim:
        current = self.sessions[session_id]
        claim = SessionClaim(current.session_id, current.device_id, current.seat_id, int(self.now()) + 3600)
        self.sessions[session_id] = claim
        return claim

    def close_session(self, session_id: str) -> None:
        self.sessions.pop(session_id, None)

    def deactivate_device(self, account_id: str, device_id: str) -> None:
        self.accounts[account_id].devices.pop(device_id, None)
