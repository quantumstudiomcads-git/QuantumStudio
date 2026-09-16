"""Signed cross-platform software-update contracts.

This package is intentionally separate from licensing.  It contains no licence
keys, entitlement checks, project state, or scientific execution logic.
"""
from .client import UpdateClient, UpdateCheckResult
from .manifest import ReleaseManifest, parse_manifest
from .models import UpdateError, UpdateErrorCode, UpdateState
from .signing import UpdateSigner, UpdateVerifier

__all__ = [
    "ReleaseManifest", "UpdateCheckResult", "UpdateClient", "UpdateError",
    "UpdateErrorCode", "UpdateSigner", "UpdateState", "UpdateVerifier",
    "parse_manifest",
]
