"""Operator-side sync client for reading website beta applications."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from urllib import error, parse, request
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, build_opener

from .imports import ImportRejected, import_applicants_json

DEFAULT_TIMEOUT_SECONDS = 15.0
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_APPLICATIONS = 1000
MAX_STATUS_RESPONSE_BYTES = 4096
REVIEW_STATUSES = frozenset({"APPLIED", "UNDER_REVIEW", "APPROVED", "REJECTED"})


class WebsiteSyncError(RuntimeError):
    """Base category for website sync errors."""


class WebsiteAuthenticationError(WebsiteSyncError):
    """Authentication or authorization failed while contacting the website."""


class WebsiteResponseError(WebsiteSyncError):
    """The website responded with an invalid or unexpected payload."""


class WebsiteStatusSyncError(WebsiteSyncError):
    """A local application status could not be mirrored to the website."""


class WebsiteStatusAuthenticationError(WebsiteStatusSyncError):
    """Status-sync authentication failed."""


class WebsiteStatusResponseError(WebsiteStatusSyncError):
    """The status endpoint returned an invalid or unexpected response."""


@dataclass(frozen=True)
class WebsiteSyncResult:
    fetched: int
    imported: int
    duplicates: int
    rejected: int


@dataclass(frozen=True)
class WebsiteStatusSyncResult:
    application_id: str
    status: str
    result: str


def resolve_operator_sync_token() -> str:
    token = os.environ.get("QS_OPERATOR_SYNC_TOKEN")
    if token:
        return token
    raise WebsiteAuthenticationError("QS_OPERATOR_SYNC_TOKEN is not configured.")


def resolve_operator_status_sync_token() -> str:
    token = os.environ.get("QS_OPERATOR_STATUS_SYNC_TOKEN")
    if token:
        return token
    raise WebsiteStatusAuthenticationError(
        "QS_OPERATOR_STATUS_SYNC_TOKEN is not configured."
    )


def _validated_base_url(
    base_url: str, *, allow_http_local: bool, production: bool
) -> tuple[str, object]:
    if not base_url or not base_url.strip():
        raise ValueError("base_url is required.")
    parsed = parse.urlsplit(base_url.strip())
    try:
        parsed.port
    except ValueError:
        raise WebsiteSyncError("Website URL is invalid.") from None
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise WebsiteSyncError("Website URL must be an HTTP(S) origin or base path.")
    scheme = parsed.scheme.lower()
    if production and scheme != "https":
        raise WebsiteSyncError("Production sync requires HTTPS.")
    if scheme == "http":
        local_host = parsed.hostname.lower() in {"localhost", "127.0.0.1", "::1"}
        if production or not allow_http_local or not local_host:
            raise WebsiteSyncError(
                "HTTP is allowed only for explicitly local/test localhost sync."
            )
    return base_url.strip().rstrip("/"), parsed


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class WebsiteSyncClient:
    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        allow_http_local: bool = False,
        production: bool = False,
    ):
        self.base_url, _ = _validated_base_url(
            base_url,
            allow_http_local=allow_http_local,
            production=production,
        )
        self.token = token if token is not None else resolve_operator_sync_token()
        if not self.token or self.token.strip() != self.token:
            raise WebsiteAuthenticationError("QS_OPERATOR_SYNC_TOKEN is invalid.")
        self.timeout = float(timeout)
        self.allow_http_local = bool(allow_http_local)
        self.production = bool(production)

    def _build_url(self, *, status: str | None = None) -> str:
        endpoint = f"{self.base_url}/api/operator/applications"
        if status is not None:
            return f"{endpoint}?{parse.urlencode({'status': status})}"
        return endpoint

    def fetch_applications(self, *, status: str | None = None) -> dict:
        url = self._build_url(status=status)
        req = request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                "User-Agent": "QuantumStudio-LicenceManager/1.0",
            },
            method="GET",
        )
        try:
            with build_opener(_NoRedirectHandler()).open(req, timeout=self.timeout) as response:
                if response.status < 200 or response.status >= 300:
                    raise WebsiteResponseError(
                        "Website operator endpoint returned an unexpected status."
                    )
                content_length = response.headers.get("Content-Length")
                if (
                    content_length is not None
                    and content_length.isdecimal()
                    and int(content_length) > MAX_RESPONSE_BYTES
                ):
                    raise WebsiteResponseError(
                        "Website payload is larger than the configured limit."
                    )
                payload = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            if exc.code in {401, 403}:
                raise WebsiteAuthenticationError(
                    "Website operator endpoint rejected the request."
                ) from None
            raise WebsiteResponseError(
                "Website operator endpoint returned an unexpected status."
            ) from None
        except WebsiteSyncError:
            raise
        except (error.URLError, TimeoutError, OSError):
            raise WebsiteSyncError("Unable to reach the website operator endpoint.") from None
        if len(payload) > MAX_RESPONSE_BYTES:
            raise WebsiteResponseError("Website payload is larger than the configured limit.")
        try:
            content = payload.decode("utf-8")
            data = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise WebsiteResponseError("Website response was not valid JSON.") from None

        if not isinstance(data, dict):
            raise WebsiteResponseError("Website response is not a JSON object.")
        if (
            set(data) != {"schema_version", "applications"}
            or type(data.get("schema_version")) is not int
            or data.get("schema_version") != 1
            or not isinstance(data.get("applications"), list)
        ):
            raise WebsiteResponseError(
                "Website response does not match the expected schema_version=1 envelope."
            )
        if len(data["applications"]) > MAX_APPLICATIONS:
            raise WebsiteResponseError("Website payload exceeds the application import limit.")
        return data

    def import_applications(
        self, database, *, status: str | None = None, operator_id: str = "operator"
    ) -> WebsiteSyncResult:
        payload = self.fetch_applications(status=status)
        fetched = len(payload["applications"])
        try:
            imported = import_applicants_json(
                json.dumps(payload).encode("utf-8"), database, operator_id=operator_id
            )
        except ImportRejected:
            return WebsiteSyncResult(fetched, 0, 0, fetched)
        return WebsiteSyncResult(fetched, imported, fetched - imported, 0)


def sync_website_applications(
    database,
    *,
    base_url: str | None = None,
    token: str | None = None,
    status: str | None = None,
    operator_id: str = "operator",
    test_mode: bool = False,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> WebsiteSyncResult:
    resolved_url = base_url or os.environ.get("QS_OPERATOR_WEBSITE_URL")
    if not resolved_url:
        raise WebsiteSyncError("QS_OPERATOR_WEBSITE_URL is not configured.")
    environment = os.environ.get("BETA_ENVIRONMENT", "").strip().lower()
    local_mode = test_mode or environment in {"local", "test"}
    client = WebsiteSyncClient(
        resolved_url,
        token=token,
        timeout=timeout,
        allow_http_local=local_mode,
        production=(environment == "production"),
    )
    return client.import_applications(database, status=status, operator_id=operator_id)


class WebsiteStatusSyncClient:
    """Narrow client for pushing a locally stored review status."""

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        allow_http_local: bool = False,
        production: bool = False,
    ):
        self.base_url, _ = _validated_base_url(
            base_url,
            allow_http_local=allow_http_local,
            production=production,
        )
        self.token = token if token is not None else resolve_operator_status_sync_token()
        if not self.token or self.token.strip() != self.token:
            raise WebsiteStatusAuthenticationError(
                "QS_OPERATOR_STATUS_SYNC_TOKEN is invalid."
            )
        self.timeout = float(timeout)

    def sync_local_application_status(
        self, database, application_id: str
    ) -> WebsiteStatusSyncResult:
        row = database.connection.execute(
            "SELECT status FROM applicants WHERE application_id = ?",
            (application_id,),
        ).fetchone()
        if row is None:
            raise WebsiteStatusSyncError("Local application is unavailable.")
        status = row[0]
        if status not in REVIEW_STATUSES:
            raise WebsiteStatusSyncError(
                "Only local application review statuses can be synchronized."
            )
        if not isinstance(application_id, str) or not _is_application_id(application_id):
            raise WebsiteStatusSyncError("Local application identifier is invalid.")

        url = (
            f"{self.base_url}/api/operator/applications/"
            f"{parse.quote(application_id, safe='')}/status"
        )
        payload = json.dumps(
            {"schema_version": 1, "status": status},
            separators=(",", ":"),
        ).encode("utf-8")
        req = request.Request(
            url,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "QuantumStudio-LicenceManager/1.0",
            },
            method="POST",
        )
        try:
            with build_opener(_NoRedirectHandler()).open(
                req, timeout=self.timeout
            ) as response:
                if response.status != 200:
                    raise WebsiteStatusResponseError(
                        "Website status endpoint returned an unexpected status."
                    )
                content_length = response.headers.get("Content-Length")
                if (
                    content_length is not None
                    and content_length.isdecimal()
                    and int(content_length) > MAX_STATUS_RESPONSE_BYTES
                ):
                    raise WebsiteStatusResponseError(
                        "Website status response exceeds the configured limit."
                    )
                body = response.read(MAX_STATUS_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            if exc.code in {401, 403}:
                raise WebsiteStatusAuthenticationError(
                    "Website status endpoint rejected the request."
                ) from None
            if exc.code == 409:
                raise WebsiteStatusResponseError(
                    "Website status changed unexpectedly; local status was preserved."
                ) from None
            raise WebsiteStatusResponseError(
                "Website status endpoint returned an unexpected status."
            ) from None
        except WebsiteSyncError:
            raise
        except (error.URLError, TimeoutError, OSError):
            raise WebsiteStatusSyncError(
                "Unable to reach the website status endpoint."
            ) from None
        if len(body) > MAX_STATUS_RESPONSE_BYTES:
            raise WebsiteStatusResponseError(
                "Website status response exceeds the configured limit."
            )
        try:
            response_data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise WebsiteStatusResponseError(
                "Website status response was not valid JSON."
            ) from None
        if (
            not isinstance(response_data, dict)
            or set(response_data)
            != {"schema_version", "application_id", "status", "result"}
            or type(response_data.get("schema_version")) is not int
            or response_data["schema_version"] != 1
            or response_data["application_id"] != application_id
            or response_data["status"] != status
            or not isinstance(response_data.get("result"), str)
            or response_data["result"] not in {"updated", "already_current"}
        ):
            raise WebsiteStatusResponseError(
                "Website status response did not match the expected contract."
            )
        return WebsiteStatusSyncResult(
            application_id,
            status,
            response_data["result"],
        )


def _is_application_id(value: str) -> bool:
    return re.fullmatch(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-"
        r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}",
        value,
    ) is not None


def sync_local_application_status(
    database,
    application_id: str,
    *,
    base_url: str | None = None,
    token: str | None = None,
    test_mode: bool = False,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> WebsiteStatusSyncResult:
    resolved_url = base_url or os.environ.get("QS_OPERATOR_WEBSITE_URL")
    if not resolved_url:
        raise WebsiteStatusSyncError("QS_OPERATOR_WEBSITE_URL is not configured.")
    environment = os.environ.get("BETA_ENVIRONMENT", "").strip().lower()
    local_mode = test_mode or environment in {"local", "test"}
    client = WebsiteStatusSyncClient(
        resolved_url,
        token=token,
        timeout=timeout,
        allow_http_local=local_mode,
        production=(environment == "production"),
    )
    return client.sync_local_application_status(database, application_id)
