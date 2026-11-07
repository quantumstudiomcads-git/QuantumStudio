"""Private service authentication and durable freshness/replay state; no signing keys."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import hmac
import json
from pathlib import Path
import re
from typing import Protocol

from backend.licensing.canonical import b64url_decode, b64url_encode, canonical_json
from backend.licensing.configuration import Environment

ISSUE_PATH = "/v1/licences/issue"
FRESHNESS_SECONDS = 120
_CALLER = re.compile(r"[a-z][a-z0-9_-]{0,63}")
_NONCE = re.compile(r"[0-9a-f]{64}")


class ServiceConfigurationError(ValueError):
    def __init__(self):
        super().__init__("Private signing service configuration is unavailable.")


class RequestRejected(Exception):
    def __init__(self, status, code):
        self.status, self.code = status, code
        super().__init__(code)


@dataclass(frozen=True)
class AuthenticatedCall:
    caller: str
    timestamp: int
    nonce: str


def _unique(pairs):
    result = {}
    for name, value in pairs:
        if name in result: raise ValueError
        result[name] = value
    return result


def _message(environment, caller, timestamp, nonce, body):
    return canonical_json({"purpose": "quantum-studio:private-licence-issuance:v1",
        "environment": environment.value, "caller": caller, "method": "POST", "path": ISSUE_PATH,
        "timestamp": timestamp, "nonce": nonce, "body_sha256": hashlib.sha256(body).hexdigest()})


def service_auth_headers(*, environment, caller, secret, timestamp, nonce, body):
    """Trusted backend client helper. Supply a fresh random 32-byte nonce for every call."""
    if (environment not in (Environment.STAGING, Environment.PRODUCTION)
            or not _CALLER.fullmatch(caller) or not _NONCE.fullmatch(nonce)
            or type(timestamp) is not int or timestamp < 0
            or not isinstance(secret, bytes) or len(secret) != 32):
        raise ServiceConfigurationError()
    signature = hmac.digest(secret, _message(environment, caller, timestamp, nonce, body), "sha256")
    return {"Content-Type": "application/json", "X-QS-Caller": caller,
        "X-QS-Timestamp": str(timestamp), "X-QS-Nonce": nonce,
        "Authorization": "QS-HMAC-SHA256 " + b64url_encode(signature)}


class ServiceAuthenticator(Protocol):
    environment: Environment
    def authenticate(self, headers, body: bytes, now: int) -> AuthenticatedCall: ...


class HmacServiceAuthenticator:
    """Environment-bound caller allowlist, with per-caller 256-bit shared credentials."""
    def __init__(self, environment, secret_record):
        try:
            if environment not in (Environment.STAGING, Environment.PRODUCTION): raise ValueError
            data = json.loads(secret_record, object_pairs_hook=_unique)
            if (not isinstance(data, dict) or set(data) != {"schema_version", "environment", "callers"}
                    or type(data["schema_version"]) is not int or data["schema_version"] != 1
                    or data["environment"] != environment.value
                    or not isinstance(data["callers"], dict) or not 1 <= len(data["callers"]) <= 32):
                raise ValueError
            keys = {}
            for caller, encoded in data["callers"].items():
                if not _CALLER.fullmatch(caller): raise ValueError
                key = b64url_decode(encoded)
                if len(key) != 32 or b64url_encode(key) != encoded: raise ValueError
                keys[caller] = key
        except Exception:
            raise ServiceConfigurationError() from None
        self.environment, self._keys = environment, keys

    def authenticate(self, headers, body, now):
        # Normalization is performed at the service boundary, rejecting duplicate names.
        caller = headers.get("x-qs-caller", "")
        timestamp = headers.get("x-qs-timestamp", "")
        nonce = headers.get("x-qs-nonce", "")
        authorization = headers.get("authorization", "")
        if (not _CALLER.fullmatch(caller) or caller not in self._keys
                or not re.fullmatch(r"[0-9]{1,12}", timestamp) or not _NONCE.fullmatch(nonce)
                or not authorization.startswith("QS-HMAC-SHA256 ")):
            raise RequestRejected(401, "unauthorized")
        stamp = int(timestamp)
        if str(stamp) != timestamp: raise RequestRejected(401, "unauthorized")
        try:
            encoded = authorization[len("QS-HMAC-SHA256 "):]
            signature = b64url_decode(encoded)
            if len(signature) != 32 or b64url_encode(signature) != encoded: raise ValueError
        except (ValueError, TypeError):
            raise RequestRejected(401, "unauthorized") from None
        expected = hmac.digest(self._keys[caller], _message(self.environment, caller, stamp, nonce, body), "sha256")
        if not hmac.compare_digest(signature, expected): raise RequestRejected(401, "unauthorized")
        if abs(now - stamp) > FRESHNESS_SECONDS: raise RequestRejected(401, "stale_request")
        return AuthenticatedCall(caller, stamp, nonce)


class SqliteRequestJournal:
    """Shared durable nonce claims and cross-process serialized issuance.

    A deployment must use one shared journal per private issuance database. This
    adapter is for an equivalent private Python runtime, not Worker local storage.
    """
    def __init__(self, path, environment):
        self.path = Path(path)
        if not self.path.is_absolute() or environment not in (Environment.STAGING, Environment.PRODUCTION):
            raise ServiceConfigurationError()
        self.environment = environment
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as db:
            db.execute("CREATE TABLE IF NOT EXISTS service_metadata(name TEXT PRIMARY KEY,value TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS request_nonces(caller TEXT NOT NULL,nonce TEXT NOT NULL,expires_at INTEGER NOT NULL,PRIMARY KEY(caller,nonce))")
            db.execute("CREATE INDEX IF NOT EXISTS request_nonce_expiry ON request_nonces(expires_at)")
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT value FROM service_metadata WHERE name='environment'").fetchone()
            if row and row[0] != environment.value: raise ServiceConfigurationError()
            db.execute("INSERT OR IGNORE INTO service_metadata VALUES('environment',?)", (environment.value,))
            db.commit()

    @property
    def storage_identity(self):
        return str(self.path.resolve())

    @contextmanager
    def _connection(self):
        import sqlite3
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        try: yield db
        finally: db.close()

    def consume(self, call, now):
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute("SELECT value FROM service_metadata WHERE name='clock_high_water'").fetchone()
            if previous and now < int(previous[0]): raise RequestRejected(503, "service_unavailable")
            db.execute("INSERT OR REPLACE INTO service_metadata VALUES('clock_high_water',?)", (str(now),))
            # Retain every nonce until its signed request can no longer be fresh.
            db.execute("DELETE FROM request_nonces WHERE expires_at < ?", (now,))
            changed = db.execute("INSERT OR IGNORE INTO request_nonces VALUES(?,?,?)",
                (call.caller, call.nonce, call.timestamp + FRESHNESS_SECONDS + 1)).rowcount
            if changed != 1: raise RequestRejected(409, "replay_rejected")
            db.commit()  # Consumption survives issuance failure and process restart.

    @contextmanager
    def serialized_issuance(self):
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield
                db.commit()
            except BaseException:
                db.rollback()
                raise
