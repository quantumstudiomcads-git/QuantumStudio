"""Desktop activation transport, real public identity, and responsive Qt flow."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from threading import Thread
from urllib.error import URLError

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from backend.licensing.device_identity import DeviceIdentityService, InMemorySecureKeyStore
from backend.licensing.service import LicensingService
from backend.licensing.desktop_auth import DesktopActivationFlow, device_activation_facts
from backend.licensing.connectors.desktop_auth import DesktopAuthError, WebsiteDesktopActivationConnector
from frontend.app.account_dialog import AccountLicensingDialog


@pytest.fixture
def device():
    return DeviceIdentityService(InMemorySecureKeyStore()).load_or_create()


class FakeConnector:
    def __init__(self, device, states=None):
        self.device = device
        self.states = list(states or [{"state": "pending"}])
        self.calls = []
        self.interval = 3
    def start_activation(self, facts):
        self.calls.append(("start", facts))
        return {"challenge_id": "a" * 64, "device_code": "b" * 64,
                "verification_url": "https://website.example/desktop-auth?challenge=" + "a" * 64,
                "expires_in": 300, "interval": self.interval}
    def poll_activation(self, challenge_id, device_code):
        self.calls.append(("poll", challenge_id, device_code))
        return self.states.pop(0) if len(self.states) > 1 else self.states[0]
    def cancel_activation(self, challenge_id, device_code):
        self.calls.append(("cancel", challenge_id, device_code))


def complete(device, status="AUTHORIZED"):
    return {"state": "completed", "activation": {"activation_request_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "installation_id": device.device_id, "status": status}}


def test_real_identity_is_reused_and_only_public_activation_facts_are_sent(device):
    connector = FakeConnector(device)
    flow = DesktopActivationFlow(connector, device, "0.2.0")
    url = flow.start()
    assert url.startswith("https://website.example/desktop-auth?challenge=")
    assert connector.calls == [("start", device_activation_facts(device, "0.2.0"))]
    assert set(flow.facts) == {"installation_id", "device_public_key_hash", "platform", "architecture", "app_version"}
    assert flow.facts["installation_id"] == "dev_" + flow.facts["device_public_key_hash"][:32]
    assert "private" not in json.dumps(flow.facts)
    store = InMemorySecureKeyStore()
    first = DeviceIdentityService(store).load_or_create()
    reopened = DeviceIdentityService(store).load_or_create()
    assert first == reopened


@pytest.mark.parametrize("status", ["AUTHORIZED", "FLAGGED", "REVOKED"])
def test_completed_result_matches_device_and_never_installs_a_lease(device, status):
    service = LicensingService.for_testing(trusted_public_keys={}, device_identity=device)
    connector = FakeConnector(device, [{"state": "pending"}, complete(device, status)])
    flow = DesktopActivationFlow(connector, service.device_identity, "0.2.0")
    flow.start()
    assert flow.poll() == {"state": "pending"}
    assert flow.poll() == complete(device, status)
    assert flow._challenge is None
    assert service.lease is None


def test_different_device_result_is_rejected(device):
    other = DeviceIdentityService(InMemorySecureKeyStore()).load_or_create()
    flow = DesktopActivationFlow(FakeConnector(device, [complete(other)]), device, "0.2.0")
    flow.start()
    with pytest.raises(DesktopAuthError, match="does not match"):
        flow.poll()


@pytest.mark.parametrize("state", ["expired", "consumed", "cancelled", "failed"])
def test_terminal_states_forget_short_lived_codes(device, state):
    flow = DesktopActivationFlow(FakeConnector(device, [{"state": state}]), device, "0.2.0")
    flow.start()
    assert flow.poll() == {"state": state}
    assert flow._challenge is None
    assert flow.poll() == {"state": state}


def test_local_timeout_and_cancellation_are_bounded_and_clear_codes(device):
    now = [0]
    connector = FakeConnector(device)
    flow = DesktopActivationFlow(connector, device, "0.2.0", clock=lambda: now[0])
    flow.start()
    now[0] = 300
    assert flow.poll() == {"state": "expired"}
    assert connector.calls[-1][0] == "cancel"
    assert flow._challenge is None
    cancelled = DesktopActivationFlow(connector, device, "0.2.0")
    cancelled.start()
    cancelled.cancel()
    assert cancelled.poll() == {"state": "cancelled"}


@pytest.mark.parametrize("url", ["", "http://website.example", "https://user:pass@website.example", "https://website.example/path", "https://website.example?code=secret"])
def test_connector_rejects_unsafe_or_missing_origin(url):
    with pytest.raises(DesktopAuthError):
        WebsiteDesktopActivationConnector(url, allow_local_http=True)


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        received = []
        code = 200
        override = None
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.received.append((self.path, dict(self.headers), body))
            port = self.server.server_port
            reply = self.override
            if reply is None:
                reply = ({"challenge_id": "a" * 64, "device_code": "b" * 64,
                    "verification_url": f"http://127.0.0.1:{port}/desktop-auth?challenge=" + "a" * 64,
                    "expires_in": 300, "interval": 3} if self.path.endswith("/start") else {"state": "pending"})
            self.send_response(self.code)
            if self.code == 302:
                self.send_header("Location", f"http://127.0.0.1:{port}/must-not-follow")
            self.end_headers()
            self.wfile.write(json.dumps(reply).encode())
        def log_message(self, *_args):
            pass
    http = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=http.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{http.server_port}", Handler
    http.shutdown()
    http.server_close()
    thread.join(timeout=2)


def test_actual_http_transport_uses_no_cookies_or_operator_tokens(device, server):
    url, handler = server
    with pytest.raises(DesktopAuthError, match="HTTPS"):
        WebsiteDesktopActivationConnector(url)
    connector = WebsiteDesktopActivationConnector(url, allow_local_http=True)
    flow = DesktopActivationFlow(connector, device, "0.2.0")
    flow.start()
    assert flow.poll() == {"state": "pending"}
    flow.cancel()
    assert len(handler.received) == 3
    for _path, headers, _body in handler.received:
        assert not {key.lower() for key in headers} & {"cookie", "authorization"}
    assert handler.received[0][2] == device_activation_facts(device, "0.2.0")
    assert set(handler.received[1][2]) == {"challenge_id", "device_code"}


@pytest.mark.parametrize("code", [400, 429, 503, 302])
def test_http_errors_are_safe_and_redirects_are_not_followed(server, code):
    url, handler = server
    handler.code = code
    handler.override = {"error": {"code": "slow_down", "message": "sensitive-body-never-display"}}
    connector = WebsiteDesktopActivationConnector(url, allow_local_http=True)
    with pytest.raises(DesktopAuthError) as raised:
        connector.poll_activation("a" * 64, "b" * 64)
    assert f"HTTP {code}" in str(raised.value)
    assert "sensitive-body" not in str(raised.value)
    assert len(handler.received) == 1


def test_invalid_verification_url_cannot_open_another_site(server, device):
    url, handler = server
    handler.override = {"challenge_id": "a" * 64, "device_code": "b" * 64,
                        "verification_url": "https://evil.example", "expires_in": 300, "interval": 3}
    with pytest.raises(DesktopAuthError, match="invalid activation challenge"):
        WebsiteDesktopActivationConnector(url, allow_local_http=True).start_activation(device_activation_facts(device, "0.2.0"))


def test_network_error_is_safe(server, monkeypatch):
    url, _handler = server
    connector = WebsiteDesktopActivationConnector(url, allow_local_http=True)
    def fail(*_args, **_kw):
        raise URLError("sensitive-network-details")
    monkeypatch.setattr(connector._opener, "open", fail)
    with pytest.raises(DesktopAuthError, match="Cannot reach") as raised:
        connector.poll_activation("a" * 64, "b" * 64)
    assert "sensitive-network-details" not in str(raised.value)


@pytest.mark.parametrize("status", ["AUTHORIZED", "FLAGGED"])
def test_dialog_launches_browser_and_displays_activation_without_granting_licence(qtbot, device, status):
    connector = FakeConnector(device, [complete(device, status)])
    connector.interval = 0.01
    service = LicensingService.for_testing(trusted_public_keys={}, device_identity=device)
    opened = []
    dialog = AccountLicensingDialog(licensing_service=service, connector=connector, open_browser=lambda url: opened.append(url) or True)
    qtbot.addWidget(dialog)
    dialog.start_button.click()
    qtbot.waitUntil(lambda: dialog._worker is None, timeout=3000)
    assert len(opened) == 1 and status in dialog.status.text()
    assert service.lease is None
    assert dialog.start_button.isEnabled()


def test_dialog_cancellation_and_browser_failure_are_safe(qtbot, device):
    connector = FakeConnector(device)
    connector.interval = 0.01
    service = LicensingService.for_testing(trusted_public_keys={}, device_identity=device)
    dialog = AccountLicensingDialog(licensing_service=service, connector=connector, open_browser=lambda _url: True)
    qtbot.addWidget(dialog)
    dialog.start_button.click()
    qtbot.waitUntil(lambda: "Waiting" in dialog.status.text(), timeout=2000)
    dialog.cancel_button.click()
    qtbot.waitUntil(lambda: dialog._worker is None, timeout=2000)
    assert "cancelled" in dialog.status.text()
    assert connector.calls[-1][0] == "cancel"


def test_missing_protected_identity_does_not_start_network(qtbot):
    dialog = AccountLicensingDialog(licensing_service=None)
    qtbot.addWidget(dialog)
    dialog.start_button.click()
    assert dialog._worker is None


def test_result_arriving_after_local_deadline_is_not_accepted(device):
    clock = [0]
    connector = FakeConnector(device)
    flow = DesktopActivationFlow(connector, device, "0.2.0", clock=lambda: clock[0])
    flow.start()
    def late(_id, _code):
        clock[0] = 301
        return complete(device)
    connector.poll_activation = late
    assert flow.poll() == {"state": "expired"}
    assert flow._challenge is None


def test_dialog_browser_open_failure_is_reported(qtbot, device):
    connector = FakeConnector(device)
    connector.interval = 0.01
    service = LicensingService.for_testing(trusted_public_keys={}, device_identity=device)
    dialog = AccountLicensingDialog(licensing_service=service, connector=connector, open_browser=lambda _url: False)
    qtbot.addWidget(dialog)
    dialog.start_button.click()
    qtbot.waitUntil(lambda: dialog._worker is None, timeout=2000)
    assert "browser could not be opened" in dialog.status.text()
    assert connector.calls[-1][0] == "cancel"


def test_closing_dialog_during_start_does_not_open_browser(qtbot, device):
    from threading import Event
    gate = Event()
    connector = FakeConnector(device)
    original = connector.start_activation
    def delayed(facts):
        gate.wait(1)
        return original(facts)
    connector.start_activation = delayed
    service = LicensingService.for_testing(trusted_public_keys={}, device_identity=device)
    opened = []
    dialog = AccountLicensingDialog(licensing_service=service, connector=connector, open_browser=lambda url: opened.append(url) or True)
    qtbot.addWidget(dialog)
    dialog.start_button.click()
    dialog.reject()
    gate.set()
    qtbot.waitUntil(lambda: dialog._worker is None, timeout=2000)
    assert opened == []
    assert connector.calls[-1][0] == "cancel"


def test_activation_result_with_lease_or_session_fields_is_rejected(device):
    result = complete(device)
    result["lease"] = {"unexpected": "not-an-activation-result"}
    flow = DesktopActivationFlow(FakeConnector(device, [result]), device, "0.2.0")
    flow.start()
    with pytest.raises(DesktopAuthError):
        flow.poll()
