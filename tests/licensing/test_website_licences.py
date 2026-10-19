"""Milestone 5: real signer, restart, and button-to-HTTP metadata contracts."""
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import re
from pathlib import Path
import sqlite3
from threading import Thread

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from backend.licensing.verifier import LeaseVerifier, LeaseValidationError, device_identity_from_private_key
from operator_tools.licence_manager.crypto import DataProtector
from operator_tools.licence_manager.database import Database
from operator_tools.licence_manager.issuance import IssuanceRejected, issue_website_activation_for_testing
from operator_tools.licence_manager.main_window import LicenceManagerWindow
from operator_tools.licence_manager import main_window, website_sync
from operator_tools.licence_manager.signing import TestEphemeralAuthority as _TestSigner, ProductionAuthority
from operator_tools.licence_manager.website_sync import WebsiteActivation


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "operator", DataProtector.for_testing(b"T" * 32))
    yield database
    database.close()


@pytest.fixture
def device():
    return device_identity_from_private_key(Ed25519PrivateKey.generate())


@pytest.fixture
def activation(device):
    return WebsiteActivation(
        activation_request_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        application_id="12345678-1234-4123-8123-123456789abc",
        installation_id=device.device_id, device_public_key_hash=device.public_key_hash,
        platform="linux", architecture="x86_64", app_version="0.1.0",
        status="AUTHORIZED", flag_reason=None, created_at="2026-10-19T00:00:00Z",
        updated_at="2026-10-19T00:00:00Z", authorized_at="2026-10-19T00:00:00Z", revoked_at=None)


def test_authorized_issuance_verifies_and_is_idempotent(db, activation, device):
    signer = _TestSigner()
    first = issue_website_activation_for_testing(db, signer, activation)
    second = issue_website_activation_for_testing(db, signer, activation)
    assert second == first
    assert LeaseVerifier({signer.kid: signer.public_key}).verify(first, device).lease.licence_id == first["licence_id"]
    assert db.connection.execute("SELECT COUNT(*) FROM website_activation_licences").fetchone()[0] == 1
    assert db.connection.execute("SELECT COUNT(*) FROM activation_requests").fetchone()[0] == 0
    assert db.connection.execute("SELECT COUNT(*) FROM licences").fetchone()[0] == 0


@pytest.mark.parametrize("change", [
    {"status": "FLAGGED"}, {"status": "REVOKED"}, {"device_public_key_hash": None},
    {"device_public_key_hash": "b" * 64},
])
def test_ineligible_or_incompatible_identity_cannot_issue(db, activation, change):
    with pytest.raises(IssuanceRejected):
        issue_website_activation_for_testing(db, _TestSigner(), replace(activation, **change))
    assert db.connection.execute("SELECT COUNT(*) FROM website_activation_licences").fetchone()[0] == 0


def test_production_authority_is_never_used(db, activation, tmp_path):
    with pytest.raises(IssuanceRejected, match="TEST ONLY"):
        issue_website_activation_for_testing(db, ProductionAuthority(tmp_path / "missing", tmp_path / "missing-meta"), activation)


def test_restart_recovers_original_envelope_without_new_signature(tmp_path, activation, device):
    root = tmp_path / "reopen"
    protector = DataProtector.for_testing(b"R" * 32)
    first_db = Database(root, protector)
    first_signer = _TestSigner()
    first = issue_website_activation_for_testing(first_db, first_signer, activation)
    first_db.close()
    reopened = Database(root, protector)
    try:
        next_signer = _TestSigner()
        recovered = issue_website_activation_for_testing(reopened, next_signer, activation)
        assert recovered == first
        assert reopened.connection.execute("SELECT COUNT(*) FROM website_activation_licences").fetchone()[0] == 1
        LeaseVerifier({first_signer.kid: first_signer.public_key}).verify(recovered, device)
        with pytest.raises(LeaseValidationError, match="Unknown"):
            LeaseVerifier({next_signer.kid: next_signer.public_key}).verify(recovered, device)
        with pytest.raises(IssuanceRejected, match="conflicts"):
            issue_website_activation_for_testing(reopened, next_signer, replace(activation, application_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"))
    finally:
        reopened.close()


def test_signer_failure_rolls_back_business_and_audit_state(db, activation, monkeypatch):
    signer = _TestSigner()
    def fail(_payload):
        raise RuntimeError("synthetic signer failure")
    monkeypatch.setattr(signer, "sign_test_fixture_only", fail)
    with pytest.raises(RuntimeError):
        issue_website_activation_for_testing(db, signer, activation)
    assert db.connection.execute("SELECT COUNT(*) FROM website_activation_licences").fetchone()[0] == 0
    assert db.connection.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0] == 0


@pytest.fixture
def metadata_server():
    class Handler(BaseHTTPRequestHandler):
        received = []
        code = 400
        payload = {"error": {"code": "invalid_metadata", "message": "must-not-display-server-text"}}
        def do_POST(self):
            self.received.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"]))), self.headers.get("Authorization")))
            self.send_response(self.code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(self.payload).encode())
        def log_message(self, *_args):
            pass
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", Handler
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def button(window, text):
    return next(b for b in window.findChildren(QPushButton) if b.text() == text)


@pytest.mark.parametrize("code", ["invalid_metadata", "invalid_activation_id"])
def test_metadata_sync_button_real_http_400_survives_ui_handler(app, db, activation, monkeypatch, metadata_server, code):
    url, handler = metadata_server
    handler.payload = {"error": {"code": code, "message": "must-not-display-server-text"}}
    monkeypatch.setenv("QS_OPERATOR_WEBSITE_URL", url)
    monkeypatch.setenv("QS_OPERATOR_LICENCE_SYNC_TOKEN", "synthetic-dedicated-write-token")
    monkeypatch.setenv("BETA_ENVIRONMENT", "local")
    monkeypatch.setattr(main_window, "fetch_website_activations", lambda **_kw: (activation,))
    dialogs = []
    monkeypatch.setattr(QMessageBox, "critical", lambda _w, _title, message: dialogs.append(message))
    captured = []
    original = website_sync.WebsiteLicenceMetadataClient.push_issued_licence
    def capture(self, *args):
        try:
            return original(self, *args)
        except Exception as exc:
            captured.append(type(exc))
            raise
    monkeypatch.setattr(website_sync.WebsiteLicenceMetadataClient, "push_issued_licence", capture)
    window = LicenceManagerWindow(test_mode=True, database=db)
    try:
        button(window, "Refresh website activations").click()
        window.website_activations_table.selectRow(0)
        button(window, "Issue test licence").click()
        button(window, "Sync licence metadata").click()
        assert captured == [website_sync.WebsiteLicenceResponseError]
        assert "HTTP 400" in window.feedback.text() and code in window.feedback.text()
        assert dialogs == [window.feedback.text()]
        assert "must-not-display-server-text" not in dialogs[0]
        assert "synthetic-dedicated-write-token" not in dialogs[0]
        path, payload, bearer = handler.received[0]
        assert path == f"/api/operator/activations/{activation.activation_request_id}/licence"
        assert bearer == "Bearer synthetic-dedicated-write-token"
        assert set(payload) == {"schema_version", "installation_id", "licence_id", "status", "issued_at", "expires_at", "revoked_at"}
        assert payload["status"] == "ISSUED" and payload["revoked_at"] is None
        assert payload["issued_at"].endswith(".000Z")
    finally:
        window.close()


def test_ui_reload_recovers_licence_and_retries_sync_without_issuing(app, tmp_path, activation, monkeypatch, metadata_server):
    url, handler = metadata_server
    handler.code = 200
    handler.payload = {"schema_version": 1, "result": "already_current"}
    monkeypatch.setenv("QS_OPERATOR_WEBSITE_URL", url)
    monkeypatch.setenv("QS_OPERATOR_LICENCE_SYNC_TOKEN", "synthetic-dedicated-write-token")
    monkeypatch.setattr(main_window, "fetch_website_activations", lambda **_kw: (activation,))
    protector = DataProtector.for_testing(b"P" * 32)
    root = tmp_path / "persistent"
    db = Database(root, protector)
    first = issue_website_activation_for_testing(db, _TestSigner(), activation)
    db.close()
    db = Database(root, protector)
    window = LicenceManagerWindow(test_mode=True, database=db)
    try:
        button(window, "Refresh website activations").click()
        window.website_activations_table.selectRow(0)
        assert window.website_activations_table.item(0, 7).text() == first["licence_id"]
        assert "Prior TEST key" in window.website_activations_table.item(0, 9).text()
        assert not button(window, "Issue test licence").isEnabled()
        assert button(window, "Sync licence metadata").isEnabled()
        window.issue_selected_website_test_licence()  # Even a direct repeat call is idempotent.
        button(window, "Sync licence metadata").click()
        button(window, "Sync licence metadata").click()
        assert "already_current" in window.feedback.text()
        assert len(handler.received) == 2
        assert all(item[1]["licence_id"] == first["licence_id"] for item in handler.received)
        assert db.connection.execute("SELECT COUNT(*) FROM website_activation_licences").fetchone()[0] == 1
    finally:
        window.close()
        db.close()


def test_flagged_ui_never_enables_issuance(app, db, activation, monkeypatch):
    monkeypatch.setattr(main_window, "fetch_website_activations", lambda **_kw: (replace(activation, status="FLAGGED"),))
    window = LicenceManagerWindow(test_mode=True, database=db)
    try:
        window.refresh_website_activations()
        window.website_activations_table.selectRow(0)
        assert not button(window, "Issue test licence").isEnabled()
        window.issue_selected_website_test_licence()
        assert db.connection.execute("SELECT COUNT(*) FROM website_activation_licences").fetchone()[0] == 0
    finally:
        window.close()


def test_missing_licence_token_is_specific_in_ui(app, db, activation, monkeypatch):
    monkeypatch.setenv("QS_OPERATOR_WEBSITE_URL", "http://127.0.0.1:8788")
    monkeypatch.delenv("QS_OPERATOR_LICENCE_SYNC_TOKEN", raising=False)
    monkeypatch.setattr(main_window, "fetch_website_activations", lambda **_kw: (activation,))
    monkeypatch.setattr(QMessageBox, "critical", lambda *_args: None)
    issue_website_activation_for_testing(db, _TestSigner(), activation)
    window = LicenceManagerWindow(test_mode=True, database=db)
    try:
        window.refresh_website_activations()
        window.website_activations_table.selectRow(0)
        button(window, "Sync licence metadata").click()
        assert "QS_OPERATOR_LICENCE_SYNC_TOKEN" in window.feedback.text()
        assert "Check the configured URL" not in window.feedback.text()
    finally:
        window.close()


def test_website_migration_applies_on_verified_v5_baseline():
    connection = sqlite3.connect(":memory:")
    try:
        for path in sorted(Path("website/migrations").glob("*.sql")):
            connection.executescript(path.read_text())
        columns = {row[1] for row in connection.execute("PRAGMA table_info(beta_activations)")}
        assert {"licence_id", "licence_status", "device_public_key_hash"} <= columns
    finally:
        connection.close()


def test_activation_upsert_and_metadata_sql_on_real_sqlite():
    db = sqlite3.connect(":memory:")
    try:
        db.executescript("""
            CREATE TABLE users(user_id TEXT PRIMARY KEY);
            CREATE TABLE beta_applications(application_id TEXT PRIMARY KEY, user_id TEXT, status TEXT, licence_expires_at TEXT);
            INSERT INTO users VALUES('user-a');
            INSERT INTO beta_applications VALUES('12345678-1234-4123-8123-123456789abc','user-a','APPROVED',NULL);
        """)
        for name in ("0005_beta_activations.sql", "0006_beta_activation_licences.sql"):
            db.executescript((Path("website/migrations") / name).read_text())
        source = Path("website/functions/_lib/beta-activation.js").read_text()
        sql = re.search(r"prepare\(`\s*(INSERT INTO beta_activations.*?)`\)\.bind", source, re.S).group(1)
        stamp = "2026-10-19T12:00:00.000Z"
        installation = "dev_" + "a" * 32
        def register(digest):
            db.execute(sql, ("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", installation, "linux", "x86_64", "0.1.0",
                stamp, installation, 2, stamp, installation, 2, stamp, stamp, stamp, installation, 2, stamp, digest, "user-a"))
        register(None)  # Legacy registration remains valid.
        register("a" * 64)  # Add the full public hash without replacing the activation.
        register("a" * 32 + "b" * 32)  # Rebinding is not allowed even for a colliding short ID.
        assert db.execute("SELECT COUNT(*) FROM beta_activations").fetchone()[0] == 1
        assert db.execute("SELECT device_public_key_hash,status FROM beta_activations").fetchone() == ("a" * 64, "AUTHORIZED")
        endpoint = Path("website/functions/api/operator/activations/[activationId]/licence.js").read_text()
        update = re.search(r"prepare\(`(UPDATE beta_activations.*?)`\)\.bind", endpoint, re.S).group(1)
        values = ("lic_12345678-1234-4123-8123-123456789abc", "ISSUED", stamp, "2027-01-17T12:00:00.000Z", None,
                  "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", installation)
        assert db.execute(update, values).rowcount == 1
        assert db.execute(update, values).rowcount == 0
        register(None)
        assert db.execute("SELECT licence_id FROM beta_activations").fetchone()[0] == values[0]
    finally:
        db.close()


def test_owned_test_database_closes_before_temporary_directory_cleanup(app):
    window = LicenceManagerWindow(test_mode=True)
    db = window.database
    root = db.root
    assert root.exists()
    window.close()
    assert not root.exists()
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        db.connection.execute("SELECT 1")
