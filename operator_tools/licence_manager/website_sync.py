"""Operator-side sync client for reading website beta applications."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib import error, parse, request
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, build_opener

from .imports import ImportRejected, import_applicants_json

DEFAULT_TIMEOUT_SECONDS = 15.0
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_APPLICATIONS = 1000


class WebsiteSyncError(RuntimeError):
    """Base category for website sync errors."""


class WebsiteAuthenticationError(WebsiteSyncError):
    """Authentication or authorization failed while contacting the website."""


class WebsiteResponseError(WebsiteSyncError):
    """The website responded with an invalid or unexpected payload."""


@dataclass(frozen=True)
class WebsiteSyncResult:
    fetched: int
    imported: int
    duplicates: int
    rejected: int


def resolve_operator_sync_token() -> str:
    token = os.environ.get("QS_OPERATOR_SYNC_TOKEN")
    if token:
        return token
    raise WebsiteAuthenticationError("QS_OPERATOR_SYNC_TOKEN is not configured.")


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

        self.base_url = base_url.strip().rstrip("/")
        self.token = token if token is not None else resolve_operator_sync_token()
        if not self.token or self.token.strip() != self.token:
            raise WebsiteAuthenticationError("QS_OPERATOR_SYNC_TOKEN is invalid.")
        self.timeout = float(timeout)
        self.allow_http_local = bool(allow_http_local)
        self.production = bool(production)

        scheme = parsed.scheme.lower()
        if self.production and scheme != "https":
            raise WebsiteSyncError("Production sync requires HTTPS.")
        if scheme == "http":
            local_host = parsed.hostname.lower() in {"localhost", "127.0.0.1", "::1"}
            if self.production or not self.allow_http_local or not local_host:
                raise WebsiteSyncError("HTTP is allowed only for explicitly local/test localhost sync.")

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
) -> WebsiteSyncResult:
    resolved_url = base_url or os.environ.get("QS_OPERATOR_WEBSITE_URL")
    if not resolved_url:
        raise WebsiteSyncError("QS_OPERATOR_WEBSITE_URL is not configured.")
    environment = os.environ.get("BETA_ENVIRONMENT", "").strip().lower()
    local_mode = test_mode or environment in {"local", "test"}
    client = WebsiteSyncClient(
        resolved_url,
        token=token,
        allow_http_local=local_mode,
        production=(environment == "production"),
    )
    return client.import_applications(database, status=status, operator_id=operator_id)
