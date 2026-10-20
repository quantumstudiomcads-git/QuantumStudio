"""Cookie-free public-artifact retrieval. Never installs/trusts website claims."""
from __future__ import annotations

import json
from urllib import request, error
from .base import ConnectorError
from .desktop_auth import WebsiteDesktopActivationConnector


class LicenceDeliveryError(ConnectorError):
    def __init__(self, message, *, code="delivery_error"):
        super().__init__(message)
        self.code = code


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class WebsiteLicenceDeliveryConnector:
    def __init__(self, base_url, *, allow_local_http=False, timeout=5):
        # Reuse the existing public origin/HTTPS guard without using its auth flow.
        self.base_url = WebsiteDesktopActivationConnector(base_url, allow_local_http=allow_local_http).base_url
        self.timeout = timeout
        self._opener = request.build_opener(_NoRedirect())

    def _post(self, action, data):
        req = request.Request(f"{self.base_url}/api/licence/{action}", data=json.dumps(data).encode(),
                              headers={"Content-Type": "application/json", "Accept": "application/json"}, method="POST")
        try:
            with self._opener.open(req, timeout=self.timeout) as response:
                raw = response.read(65537)
                if response.status != 200 or len(raw) > 65536:
                    raise LicenceDeliveryError("The licence delivery response is invalid.")
        except error.HTTPError as exc:
            code = "request_failed"
            try:
                raw = exc.read(65537)
                data = json.loads(raw.decode()) if len(raw) <= 65536 else None
                problem = data.get("error") if isinstance(data, dict) else None
                candidate = problem.get("code") if isinstance(problem, dict) else None
                if candidate in ("invalid_proof", "activation_unavailable", "challenge_unavailable", "publication_conflict", "rate_limited", "test_only"):
                    code = candidate
            except (ValueError, UnicodeError, OSError):
                pass  # Never echo arbitrary server data.
            raise LicenceDeliveryError(f"Licence delivery rejected (HTTP {exc.code}, {code}).", code=code) from None
        except (error.URLError, OSError, TimeoutError):
            raise LicenceDeliveryError("Network failure while checking the licence. Cached licence policy is unchanged.", code="network_error") from None
        try:
            data = json.loads(raw.decode())
            if not isinstance(data, dict):
                raise ValueError
            return data
        except (ValueError, UnicodeError):
            raise LicenceDeliveryError("The website returned invalid licence delivery data.") from None

    def get_device_challenge(self, installation_id, activation_request_id=None):
        body = {"installation_id": installation_id}
        if activation_request_id is not None:
            body["activation_request_id"] = activation_request_id
        data = self._post("device-challenge", body)
        if set(data) != {"challenge"} or not isinstance(data["challenge"], dict):
            raise LicenceDeliveryError("The website returned an invalid device proof challenge.")
        return data["challenge"]

    def retrieve_device_licence(self, proof):
        return self._post("device-retrieve", proof)
