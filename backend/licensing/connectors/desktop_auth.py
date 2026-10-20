"""Cookie-free HTTPS transport for the bounded desktop activation protocol."""
from __future__ import annotations

import json
import re
from urllib import error, parse, request
from .base import ConnectorError, DesktopActivationConnector

MAX_BYTES = 8192
OPAQUE = re.compile(r"[0-9a-f]{64}")


class DesktopAuthError(ConnectorError):
    """Safe display text only; never include response bodies or credentials."""
    def __init__(self, message, *, code="activation_error"):
        super().__init__(message)
        self.code = code


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class WebsiteDesktopActivationConnector(DesktopActivationConnector):
    def __init__(self, base_url, *, allow_local_http=False, timeout=5):
        try:
            url = parse.urlsplit(base_url)
            valid = (url.scheme in {"http", "https"} and url.hostname
                     and url.username is None and url.password is None
                     and url.path in {"", "/"} and not url.query and not url.fragment)
            url.port
        except (TypeError, ValueError):
            valid = False
        if not valid:
            raise DesktopAuthError("Configure QS_WEBSITE_URL with the Quantum Studio website origin.")
        if url.scheme == "http" and not (allow_local_http and url.hostname.lower() in {"localhost", "127.0.0.1", "::1"}):
            raise DesktopAuthError("Desktop sign-in requires HTTPS. Local loopback HTTP must be explicitly enabled for QA.")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        # No CookieJar or browser session access. Redirects never forward facts/codes.
        self._opener = request.build_opener(_NoRedirect())

    def _post(self, action, body):
        req = request.Request(f"{self.base_url}/api/desktop-auth/{action}",
                              data=json.dumps(body, separators=(",", ":")).encode(),
                              headers={"Content-Type": "application/json", "Accept": "application/json"}, method="POST")
        try:
            with self._opener.open(req, timeout=self.timeout) as response:
                if response.status != 200:
                    raise DesktopAuthError("The desktop activation service returned an unexpected response.")
                raw = response.read(MAX_BYTES + 1)
        except error.HTTPError as exc:
            code = "request_failed"
            try:
                raw = exc.read(MAX_BYTES + 1)
                body = json.loads(raw.decode()) if len(raw) <= MAX_BYTES else None
                problem = body.get("error") if isinstance(body, dict) else None
                candidate = problem.get("code") if isinstance(problem, dict) else None
                if candidate in ("slow_down", "rate_limited", "challenge_expired", "challenge_used", "invalid_challenge", "activation_failed"):
                    code = candidate
            except (ValueError, UnicodeDecodeError, OSError):
                pass  # Only the safe HTTP status is retained for arbitrary bodies.
            raise DesktopAuthError(f"Desktop activation failed (HTTP {exc.code}, {code}).", code=code) from None
        except (error.URLError, OSError, TimeoutError):
            raise DesktopAuthError("Cannot reach the Quantum Studio website. Check the connection and try again.", code="network_error") from None
        try:
            data = json.loads(raw.decode()) if len(raw) <= MAX_BYTES else None
        except (ValueError, UnicodeDecodeError):
            data = None
        if not isinstance(data, dict):
            raise DesktopAuthError("The desktop activation service returned invalid data.")
        return data

    def start_activation(self, facts):
        data = self._post("start", dict(facts))
        if (set(data) != {"challenge_id", "device_code", "verification_url", "expires_in", "interval"}
                or not isinstance(data.get("challenge_id"), str) or not OPAQUE.fullmatch(data["challenge_id"])
                or not isinstance(data.get("device_code"), str) or not OPAQUE.fullmatch(data["device_code"])
                or type(data.get("expires_in")) is not int or not 1 <= data["expires_in"] <= 300
                or type(data.get("interval")) is not int or not 3 <= data["interval"] <= 30
                or data.get("verification_url") != f"{self.base_url}/desktop-auth?challenge={data['challenge_id']}"):
            raise DesktopAuthError("The website returned an invalid activation challenge.")
        return data

    def poll_activation(self, challenge_id, device_code):
        return self._post("status", {"challenge_id": challenge_id, "device_code": device_code})

    def cancel_activation(self, challenge_id, device_code):
        self._post("cancel", {"challenge_id": challenge_id, "device_code": device_code})
