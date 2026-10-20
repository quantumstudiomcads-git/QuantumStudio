"""Qt-free, session-only desktop activation flow. Never installs a lease."""
from __future__ import annotations

import platform
import sys
import time
import uuid
from .connectors.desktop_auth import DesktopAuthError


def device_activation_facts(device, version):
    if device is None:
        raise DesktopAuthError("A protected device identity is unavailable. Windows DPAPI identity storage is required.")
    machine = platform.machine().lower()
    if sys.platform not in {"win32", "linux"} or machine not in {"amd64", "x86_64"}:
        raise DesktopAuthError("Device activation currently supports Windows and Linux x86_64.")
    return {"installation_id": device.device_id, "device_public_key_hash": device.public_key_hash,
            "platform": "windows" if sys.platform == "win32" else "linux",
            "architecture": "x86_64", "app_version": version}


class DesktopActivationFlow:
    def __init__(self, connector, device, version, *, clock=time.monotonic):
        self.connector = connector
        self.facts = device_activation_facts(device, version)
        self.clock = clock
        self._challenge = None
        self.deadline = 0
        self.interval = 3
        self.state = "idle"

    def start(self):
        if self.state != "idle":
            raise DesktopAuthError("Start a new activation flow before retrying.")
        self._challenge = self.connector.start_activation(self.facts)
        self.deadline = self.clock() + self._challenge["expires_in"]
        self.interval = self._challenge["interval"]
        self.state = "pending"
        return self._challenge["verification_url"]

    def poll(self):
        if self.state != "pending":
            return {"state": self.state}
        if self.clock() >= self.deadline:
            self.cancel()
            self.state = "expired"
            return {"state": "expired"}
        data = self.connector.poll_activation(self._challenge["challenge_id"], self._challenge["device_code"])
        if self.clock() >= self.deadline:
            self.cancel()
            self.state = "expired"
            return {"state": "expired"}
        state = data.get("state")
        if state not in ("pending", "completed", "expired", "consumed", "cancelled", "failed"):
            raise DesktopAuthError("The website returned an invalid activation state.")
        if state == "completed":
            activation = data.get("activation")
            try:
                valid = (set(data) == {"state", "activation"}
                         and isinstance(activation, dict)
                         and set(activation) == {"activation_request_id", "installation_id", "status"}
                         and activation["installation_id"] == self.facts["installation_id"]
                         and activation["status"] in ("AUTHORIZED", "FLAGGED", "REVOKED")
                         and str(uuid.UUID(activation["activation_request_id"])) == activation["activation_request_id"].lower())
            except (ValueError, TypeError, AttributeError):
                valid = False
            if not valid:
                raise DesktopAuthError("The activation result does not match this device.")
        elif set(data) != {"state"}:
            raise DesktopAuthError("The website returned unexpected activation data.")
        if state != "pending":
            self.state = state
            self._challenge = None  # Never persist the short-lived device code.
        return data

    def cancel(self):
        challenge, self._challenge = self._challenge, None
        self.state = "cancelled"
        if challenge:
            try:
                self.connector.cancel_activation(challenge["challenge_id"], challenge["device_code"])
            except DesktopAuthError:
                pass  # Local cancellation always completes; abandoned server codes expire.
