from __future__ import annotations

import json
import os
import uuid
from urllib.error import HTTPError

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QPushButton

from operator_tools.licence_manager.crypto import DataProtector
from operator_tools.licence_manager.database import Database
from operator_tools.licence_manager.imports import ImportRejected, import_applicants_json
from operator_tools.licence_manager.main_window import LicenceManagerWindow
from operator_tools.licence_manager.signing import TestEphemeralAuthority as _TestEphemeralAuthority
from operator_tools.licence_manager import main_window
from operator_tools.licence_manager.website_sync import (
    MAX_RESPONSE_BYTES,
    WebsiteAuthenticationError,
    WebsiteResponseError,
    WebsiteSyncClient,
    WebsiteSyncError,
    WebsiteSyncResult,
    resolve_operator_sync_token,
    sync_website_applications,
)


TEST_TOKEN = "local-test-operator-token"
APPLICATION_ID = "12345678-1234-4123-8123-123456789abc"


def applicant_record(*, application_id=APPLICATION_ID, **overrides):
    record = {
        "application_id": application_id,
        "full_name": "Ada Example",
        "email": "ada@example.test",
        "institution": "Example Institute",
        "country": "Exampleland",
        "academic_role": "Researcher",
        "research_area": "Materials",
        "intended_evaluation": "Local test only",
        "operating_system": "Windows",
        "privacy_consent": 1,
        "privacy_version": "draft-0.1",
        "terms_consent": 1,
        "terms_version": "draft-0.1",
        "communications_consent": 0,
        "status": "APPROVED",
        "submitted_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "reviewed_at": None,
        "review_note": None,
        "licence_id": "remote-licence-must-not-be-imported",
        "licence_issued_at": None,
        "licence_expires_at": None,
        "revoked_at": None,
    }
    record.update(overrides)
    return record


def envelope(*records):
    return json.dumps({"schema_version": 1, "applications": list(records)}).encode()


class FakeResponse:
    status = 200

    def __init__(self, body: bytes, *, content_length: str | None = None):
        self.body = body
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = content_length

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, limit):
        return self.body[:limit]


class FakeOpener:
    def __init__(self, result):
        self.result = result
        self.request = None
        self.timeout = None

    def open(self, req, timeout):
        self.request = req
        self.timeout = timeout
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def database(tmp_path):
    db = Database(tmp_path / "operator-data", DataProtector.for_testing(b"T" * 32))
    try:
        yield db
    finally:
        db.close()


def patch_response(monkeypatch, body, *, content_length=None):
    opener = FakeOpener(FakeResponse(body, content_length=content_length))
    monkeypatch.setattr(
        "operator_tools.licence_manager.website_sync.build_opener",
        lambda *_handlers: opener,
    )
    return opener


def test_client_constructs_endpoint_and_bearer_header(monkeypatch):
    opener = patch_response(monkeypatch, b'{"schema_version":1,"applications":[]}')
    client = WebsiteSyncClient(
        "https://website.example.test/base/",
        TEST_TOKEN,
        timeout=4,
    )
    client.fetch_applications(status="UNDER REVIEW")
    assert opener.request.full_url == (
        "https://website.example.test/base/api/operator/applications?status=UNDER+REVIEW"
    )
    assert opener.request.get_header("Authorization") == f"Bearer {TEST_TOKEN}"
    assert opener.request.get_header("Accept") == "application/json"
    assert opener.timeout == 4


def test_missing_configured_token_is_typed(monkeypatch):
    monkeypatch.delenv("QS_OPERATOR_SYNC_TOKEN", raising=False)
    with pytest.raises(WebsiteAuthenticationError, match="not configured"):
        resolve_operator_sync_token()


def test_token_is_never_in_exception_or_logging(monkeypatch, caplog):
    token = "do-not-echo-this-test-token"
    opener = FakeOpener(HTTPError(
        "https://website.example.test/api/operator/applications",
        500,
        f"server response accidentally echoed {token}",
        {},
        None,
    ))
    monkeypatch.setattr(
        "operator_tools.licence_manager.website_sync.build_opener",
        lambda *_handlers: opener,
    )
    with pytest.raises(WebsiteResponseError) as raised:
        WebsiteSyncClient("https://website.example.test", token).fetch_applications()
    assert token not in str(raised.value)
    assert token not in caplog.text
    assert opener.request.get_header("Authorization") == f"Bearer {token}"


def test_http_is_rejected_except_explicit_local_test(monkeypatch):
    with pytest.raises(WebsiteSyncError, match="HTTP"):
        WebsiteSyncClient("http://127.0.0.1:8788", TEST_TOKEN)
    with pytest.raises(WebsiteSyncError, match="HTTPS"):
        WebsiteSyncClient(
            "http://127.0.0.1:8788", TEST_TOKEN, allow_http_local=True, production=True
        )
    with pytest.raises(WebsiteSyncError, match="HTTP"):
        WebsiteSyncClient(
            "http://example.test", TEST_TOKEN, allow_http_local=True
        )
    client = WebsiteSyncClient(
        "http://127.0.0.1:8788", TEST_TOKEN, allow_http_local=True
    )
    assert client.base_url == "http://127.0.0.1:8788"


def test_sync_function_reads_required_environment(monkeypatch):
    monkeypatch.setenv("QS_OPERATOR_WEBSITE_URL", "http://localhost:8788")
    monkeypatch.setenv("QS_OPERATOR_SYNC_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("BETA_ENVIRONMENT", "local")
    monkeypatch.setattr(
        "operator_tools.licence_manager.website_sync.WebsiteSyncClient.import_applications",
        lambda self, *_args, **_kwargs: WebsiteSyncResult(0, 0, 0, 0),
    )
    result = sync_website_applications(object())
    assert result == WebsiteSyncResult(0, 0, 0, 0)


def test_non_200_status_is_handled_without_server_details(monkeypatch):
    opener = FakeOpener(HTTPError(
        "https://website.example.test/api/operator/applications",
        503,
        "private server details",
        {},
        None,
    ))
    monkeypatch.setattr(
        "operator_tools.licence_manager.website_sync.build_opener",
        lambda *_handlers: opener,
    )
    with pytest.raises(WebsiteResponseError) as raised:
        WebsiteSyncClient("https://website.example.test", TEST_TOKEN).fetch_applications()
    assert "private server details" not in str(raised.value)


def test_oversized_response_rejected_by_header_and_stream_limit(monkeypatch):
    opener = patch_response(monkeypatch, b"{}", content_length=str(MAX_RESPONSE_BYTES + 1))
    with pytest.raises(WebsiteResponseError, match="larger"):
        WebsiteSyncClient("https://website.example.test", TEST_TOKEN).fetch_applications()
    assert opener.request is not None

    patch_response(monkeypatch, b"x" * (MAX_RESPONSE_BYTES + 1))
    with pytest.raises(WebsiteResponseError, match="larger"):
        WebsiteSyncClient("https://website.example.test", TEST_TOKEN).fetch_applications()


@pytest.mark.parametrize(
    "body",
    [
        b"{",
        b'{"schema_version":2,"applications":[]}',
        b'{"schema_version":true,"applications":[]}',
        b'{"schema_version":1,"applications":[],"unexpected":true}',
    ],
)
def test_malformed_or_wrong_schema_payload_rejected(monkeypatch, body):
    patch_response(monkeypatch, body)
    with pytest.raises(WebsiteResponseError):
        WebsiteSyncClient("https://website.example.test", TEST_TOKEN).fetch_applications()


def test_payload_flows_through_validated_importer_and_forces_local_applied_state(
    monkeypatch, database
):
    payload = envelope(applicant_record())
    patch_response(monkeypatch, payload)
    result = WebsiteSyncClient("https://website.example.test", TEST_TOKEN).import_applications(
        database
    )
    assert result == WebsiteSyncResult(1, 1, 0, 0)
    row = database.connection.execute(
        "SELECT status FROM applicants WHERE application_id=?", (APPLICATION_ID,)
    ).fetchone()
    assert row[0] == "APPLIED"
    assert database.applicant_pii(APPLICATION_ID)["email"] == "ada@example.test"
    assert database.connection.execute("SELECT COUNT(*) FROM licences").fetchone()[0] == 0


def test_nullable_website_optionals_import_and_remain_idempotent(monkeypatch, database):
    application_id = str(uuid.uuid4())
    exported_record = applicant_record(
        application_id=application_id,
        academic_role="",
        intended_evaluation="",
    )
    payload = envelope(exported_record)
    patch_response(monkeypatch, payload)
    client = WebsiteSyncClient("https://website.example.test", TEST_TOKEN)
    assert client.import_applications(database) == WebsiteSyncResult(1, 1, 0, 0)
    imported_pii = database.applicant_pii(application_id)
    assert imported_pii["academic_role"] == ""
    assert imported_pii["intended_evaluation"] == ""

    patch_response(monkeypatch, payload)
    assert client.import_applications(database) == WebsiteSyncResult(1, 0, 1, 0)
    assert database.connection.execute("SELECT COUNT(*) FROM applicants").fetchone()[0] == 1

    missing_required = dict(exported_record)
    del missing_required["full_name"]
    with pytest.raises(ImportRejected):
        import_applicants_json(envelope(missing_required), database)

    null_required = dict(exported_record, full_name=None)
    with pytest.raises(ImportRejected):
        import_applicants_json(envelope(null_required), database)
    assert database.connection.execute("SELECT COUNT(*) FROM applicants").fetchone()[0] == 1


def test_duplicate_sync_is_idempotent_and_invalid_record_is_rejected(monkeypatch, database):
    payload = envelope(applicant_record())
    patch_response(monkeypatch, payload)
    client = WebsiteSyncClient("https://website.example.test", TEST_TOKEN)
    assert client.import_applications(database) == WebsiteSyncResult(1, 1, 0, 0)
    patch_response(monkeypatch, payload)
    assert client.import_applications(database) == WebsiteSyncResult(1, 0, 1, 0)
    assert database.connection.execute("SELECT COUNT(*) FROM applicants").fetchone()[0] == 1

    bad_payload = envelope(applicant_record(website_session_id="not-allowed"))
    patch_response(monkeypatch, bad_payload)
    assert client.import_applications(database) == WebsiteSyncResult(1, 0, 0, 1)
    assert database.connection.execute("SELECT COUNT(*) FROM applicants").fetchone()[0] == 1


def _make_window(db):
    return LicenceManagerWindow(
        test_mode=True,
        database=db,
        authority=_TestEphemeralAuthority(),
    )


def _button(window, label):
    return next(button for button in window.findChildren(QPushButton)
                if button.accessibleName() == label)


def test_ui_sync_action_refreshes_applications_table(app, database, monkeypatch):
    imported_id = str(uuid.uuid4())

    def fake_sync(db, *, operator_id, test_mode):
        assert db is database
        assert operator_id
        assert test_mode is True
        import_applicants_json(envelope(applicant_record(application_id=imported_id)), db)
        return WebsiteSyncResult(1, 1, 0, 0)

    monkeypatch.setattr(main_window, "sync_website_applications", fake_sync)
    window = _make_window(database)
    try:
        _button(window, "Sync website applications").click()
        assert window.applications_table.rowCount() == 1
        assert window.applications_table.findItems(imported_id, Qt.MatchExactly)
        assert window.feedback.text() == (
            "Fetched: 1\nImported: 1\nDuplicates: 0\nRejected: 0"
        )
    finally:
        window.close()


def test_ui_sync_errors_redact_tokens_and_applicant_data(app, database, monkeypatch):
    def fail_sync(*_args, **_kwargs):
        raise WebsiteAuthenticationError(
            f"Bearer {TEST_TOKEN}; applicant Ada Example"
        )

    messages = []
    monkeypatch.setattr(main_window, "sync_website_applications", fail_sync)
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda _parent, _title, message: messages.append(message),
    )
    window = _make_window(database)
    try:
        _button(window, "Sync website applications").click()
        for message in [window.feedback.text(), *messages]:
            assert TEST_TOKEN not in message
            assert "Ada Example" not in message
        assert "authentication" in window.feedback.text().lower()
    finally:
        window.close()


def test_manual_application_import_action_still_imports_and_refreshes(
    app, database, tmp_path, monkeypatch
):
    application_id = str(uuid.uuid4())
    path = tmp_path / "applications.json"
    path.write_bytes(envelope(applicant_record(application_id=application_id)))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_args: (str(path), "JSON (*.json)"))
    monkeypatch.setattr(QMessageBox, "information", lambda *_args: QMessageBox.Ok)
    window = _make_window(database)
    try:
        _button(window, "Import applications…").click()
        assert window.applications_table.rowCount() == 1
        assert window.applications_table.findItems(application_id, Qt.MatchExactly)
        assert database.connection.execute(
            "SELECT status FROM applicants WHERE application_id=?", (application_id,)
        ).fetchone()[0] == "APPLIED"
    finally:
        window.close()


def test_local_pages_d1_sync_through_actual_licence_manager_ui(app, tmp_path):
    if os.environ.get("QS_OPERATOR_INTEGRATION_TEST") != "1":
        pytest.skip("Set QS_OPERATOR_INTEGRATION_TEST=1 to use the local Pages/D1 runtime.")
    expected_id = os.environ["QS_OPERATOR_INTEGRATION_APPLICATION_ID"]
    assert os.environ["QS_OPERATOR_WEBSITE_URL"] == "http://127.0.0.1:8788"
    assert os.environ.get("QS_OPERATOR_SYNC_TOKEN")
    db = Database(tmp_path / "isolated-licence-manager", DataProtector.for_testing(b"I" * 32))
    window = _make_window(db)
    try:
        _button(window, "Sync website applications").click()
        first_count = db.connection.execute("SELECT COUNT(*) FROM applicants").fetchone()[0]
        assert first_count > 0
        assert db.connection.execute(
            "SELECT COUNT(*) FROM applicants WHERE application_id=?", (expected_id,)
        ).fetchone()[0] == 1
        assert db.connection.execute(
            "SELECT status FROM applicants WHERE application_id=?", (expected_id,)
        ).fetchone()[0] == "APPLIED"
        assert db.connection.execute("SELECT COUNT(*) FROM licences").fetchone()[0] == 0

        _button(window, "Sync website applications").click()
        assert db.connection.execute("SELECT COUNT(*) FROM applicants").fetchone()[0] == first_count
        assert db.connection.execute(
            "SELECT COUNT(*) FROM applicants WHERE application_id=?", (expected_id,)
        ).fetchone()[0] == 1
        assert db.connection.execute(
            "SELECT status FROM applicants WHERE application_id=?", (expected_id,)
        ).fetchone()[0] == "APPLIED"
        assert db.connection.execute("SELECT COUNT(*) FROM licences").fetchone()[0] == 0
        assert window.feedback.text().splitlines() == [
            f"Fetched: {first_count}",
            "Imported: 0",
            f"Duplicates: {first_count}",
            "Rejected: 0",
        ]
    finally:
        window.close()
        db.close()
