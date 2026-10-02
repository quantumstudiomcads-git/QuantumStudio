"""Separate licence signing authority. Production access is DPAPI-only and provisioned out of band."""
from __future__ import annotations

import hashlib
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.licensing.canonical import b64url_encode
from backend.licensing.verifier import issue_lease, public_key_bytes
from .crypto import dpapi_protect, dpapi_unprotect, ProtectionUnavailable


class SigningUnavailable(RuntimeError): pass


class LicenceSigningKeyStore:
    """Explicit Windows CurrentUser DPAPI storage; no key generation or startup save."""
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load_private_key(self) -> bytes | None:
        if not sys.platform.startswith("win"):
            raise SigningUnavailable("Production licence signing storage is Windows-only.")
        if not self.path.is_file():
            return None
        try:
            return dpapi_unprotect(self.path.read_bytes())
        except (OSError, ProtectionUnavailable) as error:
            raise SigningUnavailable("The CurrentUser-protected licence key is unavailable.") from error

    def store_protected_private_key(self, private_key: bytes) -> None:
        """Store ceremony-supplied key bytes; this method is never called by startup/UI."""
        if not sys.platform.startswith("win"):
            raise SigningUnavailable("Production licence signing storage is Windows-only.")
        if not isinstance(private_key, bytes) or len(private_key) != 32:
            raise ValueError("A raw 32-byte Ed25519 private key is required.")
        if self.path.exists():
            raise SigningUnavailable("Refusing to replace an existing signing key outside a rotation ceremony.")
        encrypted = dpapi_protect(private_key)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix="." + self.path.name + ".", suffix=".tmp", dir=self.path.parent)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(encrypted)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)


@dataclass(frozen=True)
class AuthorityStatus:
    available: bool
    mode: str
    kid: str | None
    public_key_fingerprint: str | None
    message: str


class TestEphemeralAuthority:
    """TEST ONLY ephemeral fixture signer; never selected by production mode."""
    mode = "TEST"
    def __init__(self, kid=None):
        self._key = Ed25519PrivateKey.generate()
        self.kid = kid or "test-lic-" + os.urandom(6).hex()
    @property
    def public_key(self): return public_key_bytes(self._key)
    def status(self): return AuthorityStatus(True, self.mode, self.kid, hashlib.sha256(self.public_key).hexdigest(), "Ephemeral test-only key in memory.")
    def sign_test_fixture_only(self, payload): return issue_lease(payload, self._key, kid=self.kid)


class ProductionAuthority:
    """A future ceremony may place a DPAPI-protected key and matching metadata here."""
    mode = "PRODUCTION"
    def __init__(self, protected_key_path: str | Path, metadata_path: str | Path, *, database=None):
        self.key_path, self.metadata_path = Path(protected_key_path), Path(metadata_path)
        self._database = database

    def issue(self, application_id: str, activation_request_id: str, profile, *, confirmed=False):
        """Issue only from authoritative local IDs and a named local policy profile."""
        from .issuance import _issue_from_authoritative_records
        from .audit import current_operator_id
        if self._database is None:
            raise SigningUnavailable("Production authority is not bound to the operator database.")
        def sign_built_lease(_database_transaction, internally_built_lease):
            # This closure is only passed to the private checked issuance workflow.
            key, kid = self._load()
            return issue_lease(internally_built_lease, key, kid=kid)
        return _issue_from_authoritative_records(
            self._database, application_id, activation_request_id, profile,
            operator_id=current_operator_id(), confirmed=confirmed,
            signer=sign_built_lease, mode=self.mode, metadata_authority=self,
        )
    def status(self):
        try:
            key, kid = self._load()
            pub = public_key_bytes(key)
            return AuthorityStatus(True, self.mode, kid, hashlib.sha256(pub).hexdigest(), "Protected licence signing authority available.")
        except (SigningUnavailable, OSError, ValueError, ProtectionUnavailable):
            return AuthorityStatus(False, self.mode, None, None, "SIGNING AUTHORITY UNAVAILABLE")
    @property
    def public_key(self): return public_key_bytes(self._load()[0])
    def _load(self):
        if not sys.platform.startswith("win") or not self.key_path.is_file() or not self.metadata_path.is_file():
            raise SigningUnavailable("No protected production signing key is provisioned.")
        import json
        metadata = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        if set(metadata) != {"schema_version", "kid", "public_key"} or type(metadata["schema_version"]) is not int or metadata["schema_version"] != 1:
            raise SigningUnavailable("Signing metadata is invalid.")
        kid = metadata["kid"]
        if not isinstance(kid, str) or not re.fullmatch(r"lic-[a-z0-9][a-z0-9._-]{0,63}", kid):
            raise SigningUnavailable("Signing key identifier is outside the licence trust domain.")
        raw = LicenceSigningKeyStore(self.key_path).load_private_key()
        if raw is None:
            raise SigningUnavailable("No protected production signing key is provisioned.")
        key = Ed25519PrivateKey.from_private_bytes(raw)
        pub = b64url_encode(public_key_bytes(key))
        if pub != metadata["public_key"]:
            raise SigningUnavailable("Protected key and public metadata do not match.")
        return key, kid


def public_key_record(authority):
    return {"kid": authority.kid, "algorithm": "Ed25519", "public_key": b64url_encode(authority.public_key)}


def record_public_metadata(database, authority, *, operator_id="operator"):
    """Persist immutable public metadata only; never persist signing bytes."""
    status = authority.status()
    if not status.available:
        return False
    domain = "test-licence" if status.mode == "TEST" else "licence"
    public_key = bytes(authority.public_key)
    from .audit import append_event, utc_now
    existing = database.connection.execute("SELECT public_key,domain FROM signing_keys WHERE kid=?", (status.kid,)).fetchone()
    if existing and (bytes(existing[0]) != public_key or existing[1] != domain):
        with database.transaction() as db:
            append_event(db, "rejected_policy_action", operator_id, [status.kid], {"code": "signing_metadata_mismatch"})
        raise SigningUnavailable("Stored signing metadata does not match the active authority.")
    with database.transaction() as db:
        existing = db.execute("SELECT public_key,domain FROM signing_keys WHERE kid=?", (status.kid,)).fetchone()
        if not existing:
            db.execute("INSERT INTO signing_keys VALUES(?,?,?,?,?)", (status.kid, public_key, domain, utc_now(), "active"))
        append_event(db, "signing_authority_status", operator_id, [status.kid], {"available": True, "mode": status.mode, "domain": domain})
    return True
