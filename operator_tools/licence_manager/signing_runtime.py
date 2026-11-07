"""Private-host signing boundary: no transport, business policy, or key persistence."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import fields
import json
import os
import re
from typing import Mapping, Protocol

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from backend.licensing.canonical import b64url_decode, b64url_encode, canonical_json
from backend.licensing.configuration import (
    ConfigurationError, Environment, deployment_environment, validate_switches,
)
from backend.licensing.models import DeviceIdentity, DeviceLease
from backend.licensing.verifier import LeaseVerifier, issue_lease, public_key_bytes
from .signing_contract import AuthorityState, AuthorityStatus, SigningUnavailable


class LicenceSigner(Protocol):
    """Only authorized issuance supplies payloads; this is not a public signing API."""
    @property
    def environment(self) -> Environment: ...
    @property
    def mode(self) -> str: ...
    @property
    def kid(self) -> str: ...
    @property
    def public_key(self) -> bytes: ...
    def sign_licence(self, payload: Mapping) -> dict: ...
    def status(self) -> AuthorityStatus: ...


# Existing DeviceLease fields plus the already signed operator provenance fields.
_PAYLOAD_FIELDS = {item.name for item in fields(DeviceLease)} - {"kid"}
_PAYLOAD_FIELDS |= {"subject_id", "approved_application_ref", "product", "channel", "policy_profile", "issuer_label"}


def _failure(code):
    return SigningUnavailable("Signing authority unavailable: " + code)


def _unique(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError
        result[name] = value
    return result


def _key_bytes(value):
    raw = b64url_decode(value)
    if len(raw) != 32 or b64url_encode(raw) != value:
        raise ValueError
    return raw


def _payload_snapshot(payload):
    if not isinstance(payload, Mapping) or set(payload) - _PAYLOAD_FIELDS:
        raise _failure("invalid-payload")
    try:
        snapshot = deepcopy(dict(payload))
        if type(snapshot.get("schema_version")) is not int or snapshot["schema_version"] != 1:
            raise ValueError
        DeviceLease.from_payload({**snapshot, "kid": "validation-only"})
        canonical_json(snapshot)
        return snapshot
    except (ValueError, TypeError, KeyError, OverflowError):
        raise _failure("invalid-payload") from None


def require_signer_environment(signer: LicenceSigner):
    """Fail before signing or recovering if a signer belongs to another profile."""
    try:
        values = getattr(signer, "_bound_deployment", os.environ)
        environment = deployment_environment(values)
        validate_switches(values, environment)
        if signer.environment is not environment:
            raise ValueError
        if environment is Environment.LOCAL:
            if signer.mode != "TEST" or not re.fullmatch(r"test-lic-[A-Za-z0-9._-]{1,80}", signer.kid):
                raise ValueError
        elif signer.mode != environment.value.upper() or not re.fullmatch(r"lic-[a-z0-9][a-z0-9._-]{0,63}", signer.kid):
            raise ValueError
    except (ConfigurationError, ValueError, TypeError, AttributeError):
        raise _failure("environment-mismatch") from None


def verify_licence_envelope(payload, envelope, *, kid, public_key):
    """Independent verification boundary before an envelope can be persisted/published."""
    try:
        expected = _payload_snapshot(payload)
        result = deepcopy(dict(envelope))
        if set(result) != set(expected) | {"kid", "signature"} or result["kid"] != kid:
            raise ValueError
        covered = {name: value for name, value in result.items() if name not in {"kid", "signature"}}
        if canonical_json(covered) != canonical_json(expected):
            raise ValueError
        device = DeviceIdentity(expected["device_id"], b"", expected["device_public_key_hash"])
        LeaseVerifier({kid: public_key}).verify(result, device)
        return result
    except (ValueError, TypeError, KeyError, OverflowError):
        raise _failure("signature-verification-failed") from None


def sign_verified_licence(signer: LicenceSigner, payload):
    require_signer_environment(signer)
    snapshot = _payload_snapshot(payload)
    # Keep an independent copy: a transport/adapter cannot alter the authorized request.
    try:
        envelope = signer.sign_licence(deepcopy(snapshot))
    except SigningUnavailable:
        raise
    except Exception:
        # Never propagate a provider/crypto exception containing configuration values.
        raise _failure("signing-failed") from None
    return verify_licence_envelope(snapshot, envelope, kid=signer.kid, public_key=signer.public_key)


class RuntimeEd25519Signer:
    """Persistent identity supplied by a private runtime secret, held only in memory.

    No generation, files, database, logging, fallback, or export of private bytes.
    Issuer identity is the existing signed kid, not a new licence-schema field.
    """
    def __init__(self, environ=None, *, bind_environment=False):
        values = os.environ if environ is None else environ
        try:
            environment = deployment_environment(values)
            validate_switches(values, environment)
            if (values.get("BETA_ENVIRONMENT") not in ("staging", "production")
                    or environment not in (Environment.STAGING, Environment.PRODUCTION)):
                raise ValueError
        except (ConfigurationError, ValueError, TypeError):
            raise _failure("invalid-environment") from None
        issuer = values.get("QS_LICENCE_SIGNING_ISSUER_ID")
        if not isinstance(issuer, str) or not re.fullmatch(r"lic-[a-z0-9][a-z0-9._-]{0,63}", issuer):
            raise _failure("invalid-issuer")
        try:
            public = _key_bytes(values.get("QS_LICENCE_SIGNING_PUBLIC_KEY"))
        except (ValueError, TypeError):
            raise _failure("invalid-public-key") from None
        try:
            record = json.loads(values.get("QS_LICENCE_SIGNING_KEY", ""), object_pairs_hook=_unique)
            if (not isinstance(record, dict)
                    or set(record) != {"schema_version", "environment", "domain", "algorithm", "private_key"}
                    or type(record["schema_version"]) is not int or record["schema_version"] != 1
                    or record["environment"] != environment.value or record["domain"] != "licence"
                    or record["algorithm"] != "Ed25519"):
                raise ValueError
            raw = _key_bytes(record["private_key"])
            key = Ed25519PrivateKey.from_private_bytes(raw)
            if public_key_bytes(key) != public:
                raise ValueError
            # Fail at composition if the pair cannot sign and verify, then verify each envelope again.
            probe = canonical_json({"purpose": "quantum-studio:licence-signing-self-test:v1", "kid": issuer})
            key.public_key().verify(key.sign(probe), probe)
        except Exception:
            raise _failure("invalid-private-key") from None
        self._environment, self._kid, self._public_key, self._key = environment, issuer, public, key
        if bind_environment:
            # Binding runtimes have no process-wide environment. Retain PUBLIC mode only.
            self._bound_deployment = {"BETA_ENVIRONMENT": environment.value}

    @property
    def environment(self): return self._environment
    @property
    def mode(self): return self.environment.value.upper()
    @property
    def kid(self): return self._kid
    @property
    def public_key(self): return self._public_key

    def status(self):
        import hashlib
        return AuthorityStatus(AuthorityState.RUNTIME_KEY_VERIFIED, self.mode, self.kid,
            hashlib.sha256(self.public_key).hexdigest(), "Runtime key and public pin verified.", self.public_key)

    def sign_licence(self, payload):
        require_signer_environment(self)
        snapshot = _payload_snapshot(payload)
        try:
            envelope = issue_lease(snapshot, self._key, kid=self.kid)
        except Exception:
            raise _failure("signing-failed") from None
        return verify_licence_envelope(snapshot, envelope, kid=self.kid, public_key=self.public_key)


def configured_licence_signer():
    """Explicit local TEST selection, otherwise strict runtime authority; no fallback."""
    try:
        environment = deployment_environment()
        validate_switches(os.environ, environment)
    except ConfigurationError:
        raise _failure("invalid-environment") from None
    if environment is Environment.LOCAL:
        if os.environ.get("QS_TEST_LICENSING") != "1":
            raise _failure("local-test-opt-in-required")
        from .signing import TestEphemeralAuthority
        return TestEphemeralAuthority()
    return RuntimeEd25519Signer()
