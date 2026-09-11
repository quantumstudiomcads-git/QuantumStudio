"""Ed25519 signed device-lease issuance helpers and fail-closed verifier."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .canonical import b64url_decode, b64url_encode, canonical_json
from .models import DeviceIdentity, DeviceLease

LEASE_SCHEMA_VERSION = 1


class LeaseValidationError(ValueError):
    """A signed lease is malformed, untrusted, or not valid for this device."""


def public_key_hash(public_key: bytes) -> str:
    return hashlib.sha256(public_key).hexdigest()


def public_key_bytes(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def device_identity_from_private_key(private_key: Ed25519PrivateKey) -> DeviceIdentity:
    public_key = public_key_bytes(private_key)
    digest = public_key_hash(public_key)
    return DeviceIdentity(device_id="dev_" + digest[:32], public_key=public_key, public_key_hash=digest)


def signing_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return exactly the fields covered by the signature, excluding signature itself."""
    values = dict(payload)
    values.pop("signature", None)
    return values


def issue_lease(payload: Mapping[str, Any], private_key: Ed25519PrivateKey, *, kid: str) -> dict[str, Any]:
    """Issue an envelope for tests, mocks, and future server-side issuers.

    The desktop application never creates a production signing key or invokes
    this with one; test mocks receive an ephemeral private key by injection.
    """
    values = dict(payload)
    values["schema_version"] = LEASE_SCHEMA_VERSION
    values["kid"] = str(kid)
    DeviceLease.from_payload(values)
    values["signature"] = b64url_encode(private_key.sign(canonical_json(signing_payload(values))))
    return values


@dataclass(frozen=True)
class LeaseVerification:
    lease: DeviceLease
    envelope: Mapping[str, Any]


class LeaseVerifier:
    """Verify versioned signed envelopes against an explicit trusted-key set."""

    def __init__(self, trusted_public_keys: Mapping[str, bytes]):
        self._trusted = dict(trusted_public_keys)

    def verify(self, envelope: Mapping[str, Any], device: DeviceIdentity) -> LeaseVerification:
        if not isinstance(envelope, Mapping):
            raise LeaseValidationError("Lease envelope must be an object.")
        values = dict(envelope)
        try:
            signature = b64url_decode(values.pop("signature"))
            lease = DeviceLease.from_payload(values)
        except (KeyError, TypeError, ValueError) as error:
            raise LeaseValidationError("Licence data is invalid or incomplete.") from error
        if lease.schema_version != LEASE_SCHEMA_VERSION:
            raise LeaseValidationError("Unsupported licence schema version.")
        trusted = self._trusted.get(lease.kid)
        if trusted is None:
            raise LeaseValidationError("Unknown licence signing key.")
        try:
            Ed25519PublicKey.from_public_bytes(trusted).verify(signature, canonical_json(values))
        except (InvalidSignature, ValueError) as error:
            raise LeaseValidationError("Licence signature is invalid.") from error
        if lease.device_id != device.device_id or lease.device_public_key_hash != device.public_key_hash:
            raise LeaseValidationError("Licence belongs to a different registered device.")
        return LeaseVerification(lease=lease, envelope=dict(envelope))
