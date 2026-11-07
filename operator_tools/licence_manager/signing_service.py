"""Authenticated identifier-only private issuance service and a non-listening WSGI adapter."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
from http import HTTPStatus
import json
import os
import time
from typing import Protocol
import uuid

from backend.licensing.canonical import canonical_json
from backend.licensing.configuration import Environment, deployment_environment, validate_origin
from .entitlements import require_current_entitlement
from .issuance import (IssuanceRejected, issue_website_activation,
    website_activation_eligibility, validate_website_issuance_history)
from .signing_contract import SigningUnavailable
from .signing_runtime import configured_licence_signer, require_signer_environment
from .signing_service_auth import (HmacServiceAuthenticator, ServiceAuthenticator, SqliteRequestJournal,
    RequestRejected, ServiceConfigurationError, ISSUE_PATH, FRESHNESS_SECONDS)
from .website_sync import WebsiteActivationsClient, MAX_WEBSITE_ACTIVATIONS, _parse_website_activation

MAX_REQUEST_BYTES = 2048
_REMOTE_FIELDS = ("licence_id", "licence_status", "licence_issued_at", "licence_expires_at")


class ActivationSource(Protocol):
    environment: Environment
    origin: str
    def read_activations(self): ...


class AuthoritativeWebsiteSource:
    """Independent HTTPS read using the existing operator endpoint, never caller facts."""
    def __init__(self, environment, origin, read_token):
        self.environment = environment
        self.origin = validate_origin(origin, environment)
        self._client = WebsiteActivationsClient(self.origin, token=read_token,
            allow_http_local=False, production=True)

    def read_activations(self):
        return self._client.fetch_activations()


@dataclass(frozen=True)
class SigningServiceRequest:
    method: str
    target: str
    scheme: str
    headers: dict = field(repr=False)
    body: bytes = field(repr=False)


@dataclass(frozen=True)
class SigningServiceResponse:
    status: int
    body: dict = field(repr=False)


def _error(status, code):
    return SigningServiceResponse(status, {"error": {"code": code}})


def _unique(pairs):
    result = {}
    for name, value in pairs:
        if name in result: raise ValueError
        result[name] = value
    return result


def _activation_id(body):
    try:
        value = json.loads(body.decode("utf-8"), object_pairs_hook=_unique)
        if (not isinstance(value, dict) or set(value) != {"schema_version", "activation_request_id"}
                or type(value["schema_version"]) is not int or value["schema_version"] != 1
                or not isinstance(value["activation_request_id"], str)
                or str(uuid.UUID(value["activation_request_id"])) != value["activation_request_id"]):
            raise ValueError
        return value["activation_request_id"]
    except (ValueError, TypeError, UnicodeError, KeyError, AttributeError):
        raise RequestRejected(400, "malformed_request") from None


class PrivateSigningService:
    """Per-request database handles plus shared durable serialization across runtimes.

    database_factory returns a context manager for the existing private Database.
    No listener, key generation, or website publication is performed here.
    """
    def __init__(self, *, database_factory, source: ActivationSource, signer,
                 authenticator: ServiceAuthenticator, journal, clock=time.time, profile_provider=None):
        try:
            require_signer_environment(signer)
            environment = signer.environment
            if (environment not in (Environment.STAGING, Environment.PRODUCTION)
                    or authenticator.environment is not environment or journal.environment is not environment
                    or source.environment is not environment):
                raise ValueError
            validate_origin(source.origin, environment)
        except Exception:
            raise ServiceConfigurationError() from None
        self._database_factory, self._source, self._signer = database_factory, source, signer
        self._auth, self._journal, self._clock = authenticator, journal, clock
        self.environment = environment
        self._profile_provider = profile_provider

    @classmethod
    def from_environment(cls, database_factory, *, clock=time.time):
        try:
            environment = deployment_environment()
            if os.environ.get("BETA_ENVIRONMENT") not in ("staging", "production"): raise ValueError
            authenticator = HmacServiceAuthenticator(environment, os.environ.get("QS_SIGNING_SERVICE_AUTH", ""))
            journal = SqliteRequestJournal(os.environ.get("QS_SIGNING_SERVICE_STATE_PATH", ""), environment)
            signer = configured_licence_signer()
            source = AuthoritativeWebsiteSource(environment, os.environ.get("QS_OPERATOR_WEBSITE_URL", ""),
                os.environ.get("QS_OPERATOR_SYNC_TOKEN", ""))
            return cls(database_factory=database_factory, source=source, signer=signer,
                authenticator=authenticator, journal=journal, clock=clock)
        except Exception:
            raise ServiceConfigurationError() from None

    def handle(self, request):
        try:
            if request.scheme != "https": return _error(403, "https_required")
            if request.target != ISSUE_PATH: return _error(404, "not_found")
            if request.method != "POST": return _error(405, "method_not_allowed")
            if not isinstance(request.body, bytes) or len(request.body) > MAX_REQUEST_BYTES:
                return _error(413, "request_too_large")
            headers = {}
            for name, value in request.headers.items():
                if (not isinstance(name, str) or not isinstance(value, str) or len(value) > 2048
                        or name.lower() in headers):
                    return _error(400, "malformed_request")
                headers[name.lower()] = value
            if headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
                return _error(415, "unsupported_media_type")
            now = int(self._clock())
            call = self._auth.authenticate(headers, request.body, now)
            self._journal.consume(call, now)
            activation_id = _activation_id(request.body)
            try: require_signer_environment(self._signer)
            except SigningUnavailable: return _error(503, "configuration_unavailable")
            with self._journal.serialized_issuance():
                if abs(int(self._clock()) - call.timestamp) > FRESHNESS_SECONDS:
                    raise RequestRejected(401, "stale_request")
                return self._issue(activation_id, call.caller)
        except RequestRejected as error:
            return _error(error.status, error.code)
        except Exception:
            # Never serialize/log provider, crypto, SQL, request, or configuration diagnostics.
            return _error(503, "service_unavailable")

    def _read(self, activation_id):
        try:
            values = tuple(self._source.read_activations())
        except Exception:
            raise RequestRejected(503, "source_unavailable") from None
        return self.validate_activations(activation_id, values)

    def validate_activations(self, activation_id, values):
        try:
            if len(values) > MAX_WEBSITE_ACTIVATIONS: raise ValueError
            records = tuple(_parse_website_activation(asdict(value)) for value in values)
            ids = [value.activation_request_id for value in records]
            if len(ids) != len(set(ids)): raise ValueError
        except Exception:
            raise RequestRejected(503, "source_unavailable") from None
        selected = next((value for value in records if value.activation_request_id == activation_id), None)
        if selected is None or website_activation_eligibility(selected, records) is not None:
            raise RequestRejected(409, "activation_unavailable")
        try:
            require_current_entitlement(selected.account_entitlement, selected.application_id, int(self._clock()))
        except (ValueError, TypeError):
            raise RequestRejected(409, "entitlement_unavailable") from None
        return selected, records

    def _bind_database(self, database):
        # Public deployment metadata, not a migration or key persistence. Prevent
        # two environments/journals from independently issuing through one database.
        if database.storage_identity == self._journal.storage_identity: raise ServiceConfigurationError()
        def bind(db):
            if db.execute("SELECT 1 FROM signing_keys WHERE domain!='licence' OR kid LIKE 'test-%' LIMIT 1").fetchone():
                raise ServiceConfigurationError()
            for name, value in (("private_signing_environment", self.environment.value),
                    ("private_signing_origin", self._source.origin),
                    ("private_signing_journal", self._journal.storage_identity)):
                row = db.execute("SELECT value FROM storage_metadata WHERE name=?", (name,)).fetchone()
                if row and row[0] != value: raise ServiceConfigurationError()
                db.execute("INSERT OR IGNORE INTO storage_metadata VALUES(?,?)", (name, value))

        database.run_transaction(bind)

    def _check_existing(self, database, activation, envelope=None):
        row = database.connection.execute("SELECT envelope_json FROM website_activation_licences WHERE activation_request_id=?",
            (activation.activation_request_id,)).fetchone()
        if not row:
            if any(getattr(activation, name) is not None for name in _REMOTE_FIELDS):
                raise RequestRejected(409, "licence_conflict")
            return False
        snapshot = database.connection.execute("SELECT snapshot_json FROM website_account_entitlements WHERE application_id=?",
            (activation.application_id,)).fetchone()
        try:
            if snapshot is None or json.loads(snapshot[0]) != activation.account_entitlement: raise ValueError
            stored = json.loads(row[0]) if envelope is None else envelope
            _, expires = require_current_entitlement(activation.account_entitlement, activation.application_id, int(self._clock()))
            if stored["expires_at"] != expires or stored["registered_device_limit"] != activation.account_entitlement["device_limit"]:
                raise ValueError
            remote = [getattr(activation, name) for name in _REMOTE_FIELDS]
            if any(value is not None for value in remote):
                stamp = lambda value: datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
                expected = [stored["licence_id"], "ISSUED", stamp(stored["issued_at"]), stamp(stored["expires_at"])]
                if remote != expected: raise ValueError
        except (ValueError, TypeError, KeyError, OverflowError):
            raise RequestRejected(409, "licence_conflict") from None
        return True

    def persist_activation(self, database, activation, records, caller):
        """One checked persistence implementation for sync and Cloudflare adapters."""
        self._bind_database(database)
        existing = self._check_existing(database, activation)
        try:
            if not existing:
                validate_website_issuance_history(database, activation, records, int(self._clock()))
            envelope = issue_website_activation(database, self._signer, activation,
                operator_id="operator-" + hashlib.sha256(
                    ("private-service:" + self.environment.value + ":" + caller).encode()).hexdigest()[:16],
                now=int(self._clock()), profile_provider=self._profile_provider)
        except IssuanceRejected:
            raise RequestRejected(409, "licence_conflict") from None
        except SigningUnavailable:
            raise RequestRejected(409 if existing else 503,
                "licence_conflict" if existing else "issuance_unavailable") from None
        self._check_existing(database, activation, envelope)
        return envelope, existing

    def completed_response(self, activation, current, envelope, existing):
        if asdict(current) != asdict(activation): raise RequestRejected(409, "authoritative_state_changed")
        return SigningServiceResponse(200, {"schema_version": 1,
            "result": "already_current" if existing else "persisted",
            "envelope_sha256": hashlib.sha256(canonical_json(envelope)).hexdigest(), "envelope": envelope})

    def _issue(self, activation_id, caller):
        activation, records = self._read(activation_id)
        with self._database_factory() as database:
            envelope, existing = self.persist_activation(database, activation, records, caller)
            current, _ = self._read(activation_id)
            return self.completed_response(activation, current, envelope, existing)


def signing_service_wsgi(service):
    """Small adapter only: an approved private TLS server supplies WSGI metadata.

    No listener is started. X-Forwarded-Proto is deliberately not trusted here.
    """
    def application(environ, start_response):
        try:
            length = environ.get("CONTENT_LENGTH", "")
            if not length.isdecimal() or int(length) > MAX_REQUEST_BYTES:
                response = _error(413, "request_too_large")
            else:
                body = environ["wsgi.input"].read(int(length))
                if len(body) != int(length): raise ValueError
                headers = {name[5:].replace("_", "-"): value for name, value in environ.items() if name.startswith("HTTP_")}
                headers["Content-Type"] = environ.get("CONTENT_TYPE", "")
                target = environ.get("PATH_INFO", "")
                if environ.get("QUERY_STRING"): target += "?" + environ["QUERY_STRING"]
                response = service.handle(SigningServiceRequest(environ.get("REQUEST_METHOD", ""), target,
                    environ.get("wsgi.url_scheme", ""), headers, body))
        except Exception:
            response = _error(400, "malformed_request")
        raw = canonical_json(response.body)
        start_response(f"{response.status} {HTTPStatus(response.status).phrase}",
            [("Content-Type", "application/json"), ("Cache-Control", "no-store"),
             ("X-Content-Type-Options", "nosniff"), ("Content-Length", str(len(raw)))])
        return [raw]
    return application
