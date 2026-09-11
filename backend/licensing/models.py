"""Typed, Qt-free licensing contracts.

All timestamps are UTC Unix seconds.  The values are deliberately explicit so
that a future licensing service can evolve without the desktop parsing opaque
provider-specific payloads.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class PlanId(str, Enum):
    FREE_STARTER = "free_starter"
    STUDENT = "student"
    PLUS = "plus"
    PLUS_TRIAL = "plus_trial"
    PRO = "pro"
    ORGANIZATION = "organization"
    ENTERPRISE = "enterprise"


class ImplementationState(str, Enum):
    READY = "ready"
    PARTIAL = "partial"
    PLANNED = "planned"
    UNSUPPORTED = "unsupported"


class EntitlementState(str, Enum):
    INCLUDED = "included"
    NOT_INCLUDED = "not_included"
    TRIAL = "trial"
    EXPIRED = "expired"
    INVALID = "invalid"
    UNAVAILABLE = "unavailable"
    AUTH_REQUIRED = "auth_required"
    CLOCK_VALIDATION_REQUIRED = "clock_validation_required"


class DecisionReason(str, Enum):
    ALLOWED = "allowed"
    NOT_IMPLEMENTED = "not_implemented"
    NOT_ENTITLED = "not_entitled"
    TRIAL_EXPIRED = "trial_expired"
    SUBSCRIPTION_EXPIRED = "subscription_expired"
    DEVICE_LIMIT_REACHED = "device_limit_reached"
    SESSION_LIMIT_REACHED = "session_limit_reached"
    OFFLINE_LEASE_EXPIRED = "offline_lease_expired"
    AUTH_REQUIRED = "auth_required"
    LICENCE_INVALID = "licence_invalid"
    CLOCK_VALIDATION_REQUIRED = "clock_validation_required"
    DEVICE_REVOKED = "device_revoked"
    SEAT_UNAVAILABLE = "seat_unavailable"
    NETWORK_UNAVAILABLE = "network_unavailable"
    SERVER_REJECTED = "server_rejected"


@dataclass(frozen=True)
class LicenseDecision:
    allowed: bool
    reason: DecisionReason
    implementation_state: ImplementationState
    entitlement_state: EntitlementState
    feature_id: str
    plan_id: str | None = None
    expires_at: int | None = None
    remediation: str = ""


@dataclass(frozen=True)
class DeviceIdentity:
    device_id: str
    public_key: bytes
    public_key_hash: str


@dataclass(frozen=True)
class DeviceLease:
    schema_version: int
    licence_id: str
    account_id: str
    subject_type: str
    plan_id: str
    device_id: str
    device_public_key_hash: str
    issued_at: int
    not_before: int
    expires_at: int
    offline_until: int | None
    entitlement_version: int
    feature_entitlements: tuple[str, ...]
    calculation_entitlements: tuple[str, ...]
    registered_device_limit: int
    concurrent_session_limit: int
    offline_device_limit: int | None
    nonce: str
    kid: str
    seat_id: str | None = None
    organization_id: str | None = None
    trial_type: str | None = None
    usage_class: str | None = None
    seat_count: int | None = None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "DeviceLease":
        required = {
            "schema_version", "licence_id", "account_id", "subject_type", "plan_id",
            "device_id", "device_public_key_hash", "issued_at", "not_before", "expires_at",
            "entitlement_version", "feature_entitlements", "calculation_entitlements",
            "registered_device_limit", "concurrent_session_limit", "nonce", "kid",
        }
        missing = sorted(required - set(payload))
        if missing:
            raise ValueError("Missing signed lease fields: " + ", ".join(missing))
        def positive_int(name: str, allow_zero: bool = False) -> int:
            value = payload[name]
            if isinstance(value, bool) or not isinstance(value, int) or (value < 0 if allow_zero else value <= 0):
                raise ValueError(f"Lease field '{name}' must be a valid integer.")
            return value
        def optional_int(name: str) -> int | None:
            value = payload.get(name)
            if value is None:
                return None
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"Lease field '{name}' must be a valid integer or null.")
            return value
        def text(name: str, *, optional: bool = False) -> str | None:
            value = payload.get(name)
            if optional and value is None:
                return None
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Lease field '{name}' must be a non-empty string.")
            return value
        def grants(name: str) -> tuple[str, ...]:
            value = payload[name]
            if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
                raise ValueError(f"Lease field '{name}' must be a list of feature identifiers.")
            return tuple(sorted(set(value)))
        lease = cls(
            schema_version=positive_int("schema_version"), licence_id=text("licence_id"),
            account_id=text("account_id"), subject_type=text("subject_type"), plan_id=text("plan_id"),
            device_id=text("device_id"), device_public_key_hash=text("device_public_key_hash"),
            issued_at=positive_int("issued_at"), not_before=positive_int("not_before", allow_zero=True),
            expires_at=positive_int("expires_at"), offline_until=optional_int("offline_until"),
            entitlement_version=positive_int("entitlement_version"),
            feature_entitlements=grants("feature_entitlements"),
            calculation_entitlements=grants("calculation_entitlements"),
            registered_device_limit=positive_int("registered_device_limit"),
            concurrent_session_limit=positive_int("concurrent_session_limit"),
            offline_device_limit=optional_int("offline_device_limit"), nonce=text("nonce"), kid=text("kid"),
            seat_id=text("seat_id", optional=True), organization_id=text("organization_id", optional=True),
            trial_type=text("trial_type", optional=True), usage_class=text("usage_class", optional=True),
            seat_count=optional_int("seat_count"),
        )
        if lease.not_before > lease.expires_at or lease.issued_at > lease.expires_at:
            raise ValueError("Lease time bounds are invalid.")
        if lease.offline_until is not None and lease.offline_until > lease.expires_at:
            raise ValueError("Offline validity cannot exceed lease expiry.")
        return lease


@dataclass(frozen=True)
class DeviceRegistrationRequest:
    account_id: str
    device: DeviceIdentity
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DeviceRegistrationResponse:
    device_id: str
    signed_lease: Mapping[str, Any]


@dataclass(frozen=True)
class SessionClaim:
    session_id: str
    device_id: str
    seat_id: str | None
    expires_at: int
