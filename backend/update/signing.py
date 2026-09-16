"""Independent Ed25519 update-signing domain.

Canonical signed bytes are UTF-8 JSON made with sorted keys, compact
separators, `ensure_ascii=False`, and `allow_nan=False`.  The top-level
manifest signature covers every top-level field except `signature`; an artifact
signature covers every artifact field except `signature`.  The `kid` field is
included in both signed payloads to permit key rotation without ambiguity.
"""
from __future__ import annotations

import base64
import json
from typing import Any, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .models import UpdateError, UpdateErrorCode


def canonical_json(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def b64url_decode(value: str) -> bytes:
    if not isinstance(value, str) or not value or any(char.isspace() for char in value):
        raise ValueError("Expected unpadded base64url data.")
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def signing_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(value)
    payload.pop("signature", None)
    return payload


class UpdateSigner:
    """Publisher-side signer. Production private material is injected, never stored."""

    def __init__(self, private_key: Ed25519PrivateKey, *, kid: str):
        if not kid:
            raise ValueError("Update signing key id is required.")
        self.private_key, self.kid = private_key, kid

    @classmethod
    def from_base64url(cls, encoded: str, *, kid: str) -> "UpdateSigner":
        return cls(Ed25519PrivateKey.from_private_bytes(b64url_decode(encoded)), kid=kid)

    def public_key_bytes(self) -> bytes:
        return self.private_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)

    def sign(self, payload: Mapping[str, Any]) -> str:
        return b64url_encode(self.private_key.sign(canonical_json(signing_payload(payload))))

    def sign_envelope(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        envelope = dict(payload)
        envelope["kid"] = self.kid
        envelope["signature"] = self.sign(envelope)
        return envelope


class UpdateVerifier:
    """Fail-closed verifier for the update key ring, distinct from licensing."""

    def __init__(self, trusted_public_keys: Mapping[str, bytes]):
        self._trusted = dict(trusted_public_keys)

    def verify(self, envelope: Mapping[str, Any]) -> None:
        try:
            kid, signature = str(envelope["kid"]), b64url_decode(str(envelope["signature"]))
            trusted = self._trusted[kid]
            Ed25519PublicKey.from_public_bytes(trusted).verify(signature, canonical_json(signing_payload(envelope)))
        except (KeyError, InvalidSignature, ValueError, TypeError) as error:
            raise UpdateError(UpdateErrorCode.SIGNATURE_INVALID, "Update metadata signature is invalid or untrusted.") from error
