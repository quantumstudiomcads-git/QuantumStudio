"""Portable authority metadata shared by private runtimes and legacy adapters."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum

class SigningUnavailable(RuntimeError): pass



@dataclass(frozen=True)
class AuthorityStatus:
    state: "AuthorityState"
    mode: str
    kid: str | None
    public_key_fingerprint: str | None
    message: str
    public_key: bytes | None = None
    last_authorized_use_at: str | None = None



class AuthorityState(str, Enum):
    UNINITIALIZED = "UNINITIALIZED"
    METADATA_INVALID = "METADATA_INVALID"
    PROTECTED_KEY_MISSING = "PROTECTED_KEY_MISSING"
    PROTECTED_KEY_PRESENT_UNVERIFIED = "PROTECTED_KEY_PRESENT_UNVERIFIED"
    LAST_AUTHORIZED_USE_SUCCEEDED = "LAST_AUTHORIZED_USE_SUCCEEDED"
    LAST_AUTHORIZED_USE_FAILED = "LAST_AUTHORIZED_USE_FAILED"
    TEST_ONLY_EPHEMERAL = "TEST_ONLY_EPHEMERAL"
    RUNTIME_KEY_VERIFIED = "RUNTIME_KEY_VERIFIED"

