"""Dedicated operator device revocation; never changes licences or entitlements."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib import request
from urllib.error import HTTPError, URLError
from urllib.request import build_opener

from .website_sync import (
    WebsiteSyncError, _NoRedirectHandler, _validated_base_url,
    _is_application_id, _is_iso_timestamp,
)

REVOCATION_REASONS = (
    "DEVICE_REPLACED", "DEVICE_LOST", "USER_REQUEST", "BETA_ACCESS_REVOKED", "ADMINISTRATIVE", "OTHER",
)


class DeviceRevocationError(WebsiteSyncError):
    """Revocation configuration or response is invalid."""


class DeviceRevocationAuthenticationError(DeviceRevocationError):
    """Dedicated credential is missing or rejected."""


class DeviceRevocationNetworkError(DeviceRevocationError):
    """Request outcome is unknown; an identical retry is safe."""


class DeviceRevocationConflictError(DeviceRevocationError):
    """Activation state or original revocation reason conflicts."""


@dataclass(frozen=True)
class DeviceRevocationResult:
    activation_request_id: str
    result: str
    revoked_at: str
    reason_code: str


class DeviceRevocationClient:
    def __init__(self, base_url, token=None, *, allow_http_local=False, production=False, timeout=15):
        try:
            self.base_url, _ = _validated_base_url(base_url, allow_http_local=allow_http_local, production=production)
        except WebsiteSyncError:
            raise DeviceRevocationError("Revocation URL configuration is invalid.") from None
        self.token = token if token is not None else os.environ.get("QS_OPERATOR_ACTIVATION_REVOKE_TOKEN", "")
        if not isinstance(self.token, str) or not self.token or self.token.strip() != self.token:
            raise DeviceRevocationAuthenticationError("Dedicated revocation credential is missing or invalid.")
        self.timeout = timeout

    def revoke(self, activation_id, reason_code, *, reason_text=None):
        if not isinstance(activation_id, str) or not _is_application_id(activation_id) or reason_code not in REVOCATION_REASONS:
            raise DeviceRevocationError("Invalid activation or controlled reason.")
        payload = {"schema_version": 1, "reason_code": reason_code, "expected_status": "AUTHORIZED"}
        if reason_text is not None:
            if (not isinstance(reason_text, str) or not 1 <= len(reason_text) <= 240
                    or reason_text.strip() != reason_text or any(ord(c) < 32 or ord(c) == 127 for c in reason_text)):
                raise DeviceRevocationError("Invalid revocation note.")
            payload["reason_text"] = reason_text
        req = request.Request(f"{self.base_url}/api/operator/activations/{activation_id}/revoke",
            data=json.dumps(payload).encode("utf-8"), method="POST",
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json", "Accept": "application/json"})
        try:
            with build_opener(_NoRedirectHandler()).open(req, timeout=self.timeout) as response:
                if response.status != 200:
                    raise DeviceRevocationError("Unexpected revocation response.")
                body = response.read(4097)
        except HTTPError as exc:
            if exc.code in {401, 403}:
                raise DeviceRevocationAuthenticationError("Revocation authentication failed.") from None
            if exc.code == 409:
                raise DeviceRevocationConflictError("Revocation conflict; refresh before retrying.") from None
            raise DeviceRevocationError("Unexpected revocation response.") from None
        except (URLError, TimeoutError, OSError):
            raise DeviceRevocationNetworkError("Revocation endpoint could not be reached; an identical retry is safe.") from None
        if len(body) > 4096:
            raise DeviceRevocationError("Unexpected revocation response.")
        try:
            data = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise DeviceRevocationError("Unexpected revocation response.") from None
        if (not isinstance(data, dict)
                or set(data) != {"schema_version", "activation_request_id", "status", "result", "revoked_at", "reason_code"}
                or type(data["schema_version"]) is not int or data["schema_version"] != 1
                or data["activation_request_id"] != activation_id or data["status"] != "REVOKED"
                or data["result"] not in ("revoked", "already_revoked") or data["reason_code"] != reason_code
                or not isinstance(data["revoked_at"], str) or not _is_iso_timestamp(data["revoked_at"])):
            raise DeviceRevocationError("Unexpected revocation response.")
        return DeviceRevocationResult(activation_id, data["result"], data["revoked_at"], reason_code)


def revoke_website_device(activation_id, reason_code, *, test_mode=False):
    environment = os.environ.get("BETA_ENVIRONMENT", "").strip().lower()
    client = DeviceRevocationClient(os.environ.get("QS_OPERATOR_WEBSITE_URL", ""),
        allow_http_local=test_mode or environment in {"local", "test"}, production=environment == "production")
    return client.revoke(activation_id, reason_code)
