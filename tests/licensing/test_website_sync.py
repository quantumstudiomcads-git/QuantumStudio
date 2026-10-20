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
from operator_tools.licence_manager.models import ApplicantStatus
from operator_tools.licence_manager.signing import TestEphemeralAuthority as _TestEphemeralAuthority
from operator_tools.licence_manager import main_window
from operator_tools.licence_manager.website_sync import (
    MAX_ACTIVATION_RESPONSE_BYTES,
    WebsiteActivation,
    MAX_RESPONSE_BYTES,
    MAX_STATUS_RESPONSE_BYTES,
    WebsiteAuthenticationError,
    WebsiteResponseError,
    WebsiteStatusAuthenticationError,
    WebsiteStatusResponseError,
    WebsiteStatusSyncClient,
    WebsiteStatusSyncError,
    WebsiteStatusSyncResult,
    WebsiteActivationsClient,
    WebsiteSyncClient,
    WebsiteSyncError,
    WebsiteSyncResult,
    fetch_website_activations,
    resolve_operator_sync_token,
    sync_local_application_status,
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


def patch_status_response(
    monkeypatch,
    body,
    *,
    content_length=None,
    error=None,
):
    response = FakeOpener(
        error
        if error is not None
        else FakeResponse(body, content_length=content_length)
    )
    original_open = response.open
    def open_with_status_read(req, timeout):
        if req.get_method() == "GET" and req.full_url.endswith("/status") and error is None:
            try:
                target = json.loads(body).get("status", "APPLIED")
                current = {"UNDER_REVIEW": "APPLIED", "APPROVED": "UNDER_REVIEW", "REJECTED": "UNDER_REVIEW"}.get(target, "APPLIED")
            except (ValueError, TypeError):
                current = "APPLIED"
            response.request = req
            response.timeout = timeout
            return FakeResponse(json.dumps({"schema_version": 1, "application_id": APPLICATION_ID,
                "status": current, "result": "already_current"}).encode())
        return original_open(req, timeout)
    response.open = open_with_status_read
    response.handlers = []

    def build_test_opener(*handlers):
        response.handlers = handlers
        return response

    monkeypatch.setattr(
        "operator_tools.licence_manager.website_sync.build_opener",
        build_test_opener,
    )
    return response


def create_local_application(database, application_id=APPLICATION_ID):
    import_applicants_json(envelope(applicant_record(application_id=application_id)), database)


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


def test_status_client_uses_status_endpoint_and_separate_write_token(
    monkeypatch, database
):
    create_local_application(database)
    read_token = "read-only-token-must-not-be-used"
    status_token = "distinct-status-write-token"
    monkeypatch.setenv("QS_OPERATOR_SYNC_TOKEN", read_token)
    monkeypatch.setenv("QS_OPERATOR_STATUS_SYNC_TOKEN", status_token)
    response_body = json.dumps({
        "schema_version": 1,
        "application_id": APPLICATION_ID,
        "status": "APPLIED",
        "result": "updated",
    }).encode()
    opener = patch_status_response(monkeypatch, response_body)
    result = sync_local_application_status(
        database,
        APPLICATION_ID,
        base_url="https://website.example.test/base/",
    )
    assert result == WebsiteStatusSyncResult(APPLICATION_ID, "APPLIED", "updated")
    assert opener.request.full_url == (
        f"https://website.example.test/base/api/operator/applications/{APPLICATION_ID}/status"
    )
    assert opener.request.get_header("Authorization") == f"Bearer {status_token}"
    assert opener.request.get_header("Authorization") != f"Bearer {read_token}"
    assert json.loads(opener.request.data) == {"schema_version": 1, "status": "APPLIED"}


def test_status_client_does_not_fall_back_to_read_token(monkeypatch):
    monkeypatch.delenv("QS_OPERATOR_STATUS_SYNC_TOKEN", raising=False)
    monkeypatch.setenv("QS_OPERATOR_SYNC_TOKEN", "read-only-token")
    with pytest.raises(WebsiteStatusAuthenticationError, match="not configured"):
        WebsiteStatusSyncClient("https://website.example.test")


def test_status_client_enforces_https_and_explicit_local_http(monkeypatch):
    with pytest.raises(WebsiteSyncError, match="HTTPS"):
        WebsiteStatusSyncClient(
            "http://127.0.0.1:8788",
            "local-status-token",
            production=True,
            allow_http_local=True,
        )
    with pytest.raises(WebsiteSyncError, match="HTTP"):
        WebsiteStatusSyncClient("http://127.0.0.1:8788", "local-status-token")
    client = WebsiteStatusSyncClient(
        "http://127.0.0.1:8788",
        "local-status-token",
        allow_http_local=True,
    )
    assert client.base_url == "http://127.0.0.1:8788"


def test_status_client_rejects_redirects_and_non_success_responses(monkeypatch):
    location = "https://website.example.test/redirect"
    opener = patch_status_response(
        monkeypatch,
        b"",
        error=HTTPError(
            "https://website.example.test/status",
            302,
            f"redirect to {location}",
            {"Location": location},
            None,
        ),
    )
    with pytest.raises(WebsiteStatusResponseError) as raised:
        WebsiteStatusSyncClient(
            "https://website.example.test", TEST_TOKEN
        ).sync_local_application_status(
            _LocalStatusDatabase("APPLIED"), APPLICATION_ID
        )
    assert location not in str(raised.value)
    assert opener.request.get_method() == "GET"
    no_redirect = next(
        handler for handler in opener.handlers
        if handler.__class__.__name__ == "_NoRedirectHandler"
    )
    assert no_redirect.redirect_request(
        opener.request, None, 302, "Found", {"Location": location}, location
    ) is None

    patch_status_response(
        monkeypatch,
        b"",
        error=HTTPError(
            "https://website.example.test/status",
            503,
            "private server detail",
            {},
            None,
        ),
    )
    with pytest.raises(WebsiteStatusResponseError) as raised:
        WebsiteStatusSyncClient(
            "https://website.example.test", TEST_TOKEN
        ).sync_local_application_status(
            _LocalStatusDatabase("APPLIED"), APPLICATION_ID
        )
    assert "private server detail" not in str(raised.value)


class _LocalStatusDatabase:
    def __init__(self, status):
        self.status = status
        self.connection = self

    def execute(self, _query, _values):
        return self

    def fetchone(self):
        return (self.status,)


@pytest.mark.parametrize(
    "response_body",
    [
        b"{",
        b'{"schema_version":2,"application_id":"12345678-1234-4123-8123-123456789abc","status":"APPLIED","result":"updated"}',
        b'{"schema_version":1,"application_id":"12345678-1234-4123-8123-123456789abc","status":"APPROVED","result":"updated"}',
        b'{"schema_version":1,"application_id":"12345678-1234-4123-8123-123456789abc","status":"APPLIED","result":[]}',
        b'{"schema_version":1,"application_id":"12345678-1234-4123-8123-123456789abc","status":"APPLIED","result":"updated","extra":true}',
    ],
)
def test_status_client_rejects_malformed_responses(monkeypatch, response_body):
    patch_status_response(monkeypatch, response_body)
    with pytest.raises(WebsiteStatusResponseError):
        WebsiteStatusSyncClient(
            "https://website.example.test", TEST_TOKEN
        ).sync_local_application_status(
            _LocalStatusDatabase("APPLIED"), APPLICATION_ID
        )


def test_status_client_rejects_oversized_response(monkeypatch):
    patch_status_response(
        monkeypatch,
        b"x" * (MAX_STATUS_RESPONSE_BYTES + 1),
    )
    with pytest.raises(WebsiteStatusResponseError, match="limit"):
        WebsiteStatusSyncClient(
            "https://website.example.test", TEST_TOKEN
        ).sync_local_application_status(
            _LocalStatusDatabase("APPLIED"), APPLICATION_ID
        )
    patch_status_response(
        monkeypatch,
        b"{}",
        content_length=str(MAX_STATUS_RESPONSE_BYTES + 1),
    )
    with pytest.raises(WebsiteStatusResponseError, match="limit"):
        WebsiteStatusSyncClient(
            "https://website.example.test", TEST_TOKEN
        ).sync_local_application_status(
            _LocalStatusDatabase("APPLIED"), APPLICATION_ID
        )


def test_status_token_is_absent_from_errors_and_logs(monkeypatch, caplog):
    token = "never-log-this-status-token"
    patch_status_response(
        monkeypatch,
        b"",
        error=HTTPError(
            "https://website.example.test/status",
            503,
            f"server echoed token {token}",
            {},
            None,
        ),
    )
    with pytest.raises(WebsiteStatusResponseError) as raised:
        WebsiteStatusSyncClient(
            "https://website.example.test", token
        ).sync_local_application_status(
            _LocalStatusDatabase("APPLIED"), APPLICATION_ID
        )
    assert token not in str(raised.value)
    assert token not in caplog.text


@pytest.mark.parametrize(
    ("transitions", "expected_status"),
    [
        ([], "APPLIED"),
        ([ApplicantStatus.UNDER_REVIEW], "UNDER_REVIEW"),
        ([ApplicantStatus.UNDER_REVIEW, ApplicantStatus.APPROVED], "APPROVED"),
        ([ApplicantStatus.UNDER_REVIEW, ApplicantStatus.REJECTED], "REJECTED"),
    ],
)
def test_status_client_reads_each_allowed_state_from_local_database(
    monkeypatch, database, transitions, expected_status
):
    create_local_application(database)
    for state in transitions:
        database.transition(APPLICATION_ID, state)
    response_body = json.dumps({
        "schema_version": 1,
        "application_id": APPLICATION_ID,
        "status": expected_status,
        "result": "updated",
    }).encode()
    opener = patch_status_response(monkeypatch, response_body)
    result = sync_local_application_status(
        database,
        APPLICATION_ID,
        base_url="https://website.example.test",
        token=TEST_TOKEN,
    )
    assert result.status == expected_status
    assert json.loads(opener.request.data)["status"] == expected_status
    assert database.connection.execute(
        "SELECT status FROM applicants WHERE application_id=?",
        (APPLICATION_ID,),
    ).fetchone()[0] == expected_status


def test_status_client_rejects_non_review_local_state(monkeypatch, database):
    create_local_application(database)
    with database.transaction() as conn:
        conn.execute(
            "UPDATE applicants SET status='LICENCE_ISSUED' WHERE application_id=?",
            (APPLICATION_ID,),
        )
    with pytest.raises(WebsiteStatusSyncError, match="review statuses"):
        sync_local_application_status(
            database,
            APPLICATION_ID,
            base_url="https://website.example.test",
            token=TEST_TOKEN,
        )


def test_failed_status_sync_leaves_local_status_unchanged(monkeypatch, database):
    create_local_application(database)
    patch_status_response(
        monkeypatch,
        b"",
        error=HTTPError(
            "https://website.example.test/status",
            503,
            "unavailable",
            {},
            None,
        ),
    )
    with pytest.raises(WebsiteStatusResponseError):
        sync_local_application_status(
            database,
            APPLICATION_ID,
            base_url="https://website.example.test",
            token=TEST_TOKEN,
        )
    assert database.connection.execute(
        "SELECT status FROM applicants WHERE application_id=?",
        (APPLICATION_ID,),
    ).fetchone()[0] == "APPLIED"


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


def test_ui_status_sync_reports_success_and_does_not_accept_caller_status(
    app, database, monkeypatch
):
    create_local_application(database)
    calls = []

    def fake_sync(db, application_id, *, test_mode):
        calls.append((db, application_id, test_mode))
        return WebsiteStatusSyncResult(application_id, "APPLIED", "already_current")

    monkeypatch.setattr(main_window, "sync_local_application_status", fake_sync)
    window = _make_window(database)
    try:
        window.applications_table.selectRow(0)
        _button(window, "Sync status to website").click()
        assert calls == [(database, APPLICATION_ID, True)]
        assert window.feedback.text() == "Website status mirror already current: APPLIED."
        assert database.connection.execute(
            "SELECT status FROM applicants WHERE application_id=?",
            (APPLICATION_ID,),
        ).fetchone()[0] == "APPLIED"
    finally:
        window.close()


def test_ui_reports_stale_mirror_without_reverting_local_decision(
    app, database, monkeypatch
):
    create_local_application(database)
    database.transition(APPLICATION_ID, ApplicantStatus.UNDER_REVIEW)

    def fail_sync(*_args, **_kwargs):
        raise WebsiteStatusResponseError("remote failure detail")

    messages = []
    monkeypatch.setattr(main_window, "sync_local_application_status", fail_sync)
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda _parent, _title, message: messages.append(message),
    )
    window = _make_window(database)
    try:
        window.applications_table.selectRow(0)
        _button(window, "Sync status to website").click()
        assert window.feedback.text() == (
            "Website status endpoint returned an unexpected response. The local decision is unchanged."
        )
        assert messages == [window.feedback.text()]
        assert database.connection.execute(
            "SELECT status FROM applicants WHERE application_id=?",
            (APPLICATION_ID,),
        ).fetchone()[0] == "UNDER_REVIEW"
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


def _website_activation_record(**overrides):
    record = {
        "activation_request_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "application_id": APPLICATION_ID,
        "installation_id": f"dev_{'a' * 32}",
        "platform": "linux",
        "architecture": "x86_64",
        "app_version": "0.1.0",
        "status": "AUTHORIZED",
        "flag_reason": None,
        "created_at": "2026-10-01T00:00:00.000Z",
        "updated_at": "2026-10-01T00:00:00.000Z",
        "authorized_at": "2026-10-01T00:00:00.000Z",
        "revoked_at": None,
    }
    record.update(overrides)
    return record


def test_operator_activation_client_uses_read_only_endpoint_and_strict_contract(monkeypatch):
    body = json.dumps({
        "schema_version": 1,
        "activations": [_website_activation_record()],
    }).encode()
    opener = patch_status_response(monkeypatch, body)
    result = WebsiteActivationsClient(
        "https://website.example.test/base/",
        TEST_TOKEN,
        timeout=3,
    ).fetch_activations()
    assert result == (WebsiteActivation(**_website_activation_record()),)
    assert opener.request.full_url == (
        "https://website.example.test/base/api/operator/activations"
    )
    assert opener.request.get_method() == "GET"
    assert opener.request.get_header("Authorization") == f"Bearer {TEST_TOKEN}"
    assert opener.timeout == 3


@pytest.mark.parametrize(
    "body",
    [
        b"{",
        b'{"schema_version":2,"activations":[]}',
        b'{"schema_version":true,"activations":[]}',
        b'{"schema_version":1,"activations":[],"users":[]}',
        json.dumps({"schema_version": 1, "activations": [{
            **_website_activation_record(),
            "email": "private@example.test",
        }]}).encode(),
        json.dumps({"schema_version": 1, "activations": [{
            **_website_activation_record(),
            "status": "ISSUED",
        }]}).encode(),
    ],
)
def test_operator_activation_client_rejects_malformed_or_sensitive_payloads(
    monkeypatch, body
):
    patch_status_response(monkeypatch, body)
    with pytest.raises(WebsiteResponseError):
        WebsiteActivationsClient(
            "https://website.example.test", TEST_TOKEN
        ).fetch_activations()


def test_operator_activation_client_bounds_http_and_production_transport(monkeypatch):
    with pytest.raises(WebsiteSyncError, match="HTTP"):
        WebsiteActivationsClient("http://127.0.0.1:8788", TEST_TOKEN)
    with pytest.raises(WebsiteSyncError, match="HTTPS"):
        WebsiteActivationsClient(
            "http://127.0.0.1:8788",
            TEST_TOKEN,
            allow_http_local=True,
            production=True,
        )
    patch_status_response(
        monkeypatch,
        b"",
        content_length=str(MAX_ACTIVATION_RESPONSE_BYTES + 1),
    )
    with pytest.raises(WebsiteResponseError, match="limit"):
        WebsiteActivationsClient(
            "https://website.example.test", TEST_TOKEN
        ).fetch_activations()


def test_operator_activation_client_redacts_token_and_rejects_non_success(monkeypatch, caplog):
    token = "activation-token-must-not-leak"
    opener = patch_status_response(
        monkeypatch,
        b"",
        error=HTTPError(
            "https://website.example.test/api/operator/activations",
            503,
            f"private response mentioned {token}",
            {},
            None,
        ),
    )
    with pytest.raises(WebsiteResponseError) as raised:
        WebsiteActivationsClient("https://website.example.test", token).fetch_activations()
    assert token not in str(raised.value)
    assert token not in caplog.text
    assert opener.request.get_method() == "GET"


def test_fetch_website_activations_uses_local_environment(monkeypatch):
    monkeypatch.setenv("QS_OPERATOR_WEBSITE_URL", "http://127.0.0.1:8788")
    monkeypatch.setenv("QS_OPERATOR_SYNC_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("BETA_ENVIRONMENT", "local")
    monkeypatch.setattr(
        "operator_tools.licence_manager.website_sync.WebsiteActivationsClient.fetch_activations",
        lambda self: (),
    )
    assert fetch_website_activations() == ()


def test_ui_refresh_action_displays_read_only_remote_activations(app, database, monkeypatch):
    activation = WebsiteActivation(**_website_activation_record(flag_reason="DEVICE_LIMIT", status="FLAGGED"))
    monkeypatch.setattr(
        main_window,
        "fetch_website_activations",
        lambda **_kwargs: (activation,),
    )
    window = LicenceManagerWindow(test_mode=True, database=database)
    try:
        _button(window, "Refresh website activations").click()
        assert window.website_activations_table.rowCount() == 1
        assert window.website_activations_table.item(0, 3).text() == "FLAGGED"
        assert window.website_activations_table.item(0, 4).text() == "DEVICE_LIMIT"
        assert window.requests_table.rowCount() == 0
        assert database.connection.execute(
            "SELECT COUNT(*) FROM activation_requests"
        ).fetchone()[0] == 0
        assert "read-only" in window.feedback.text()
    finally:
        window.close()


def test_local_pages_d1_operator_status_push_flow(app, tmp_path, monkeypatch):
    if os.environ.get("QS_OPERATOR_STATUS_INTEGRATION_TEST") != "1":
        pytest.skip("Set QS_OPERATOR_STATUS_INTEGRATION_TEST=1 for local Pages/D1 status sync.")
    application_id = os.environ["QS_OPERATOR_STATUS_INTEGRATION_APPLICATION_ID"]
    base_url = os.environ["QS_OPERATOR_WEBSITE_URL"]
    assert base_url == "http://127.0.0.1:8788"
    assert os.environ.get("QS_OPERATOR_SYNC_TOKEN")
    assert os.environ.get("QS_OPERATOR_STATUS_SYNC_TOKEN")
    db = Database(tmp_path / "isolated-status-licence-manager",
                  DataProtector.for_testing(b"S" * 32))
    window = _make_window(db)
    dialogs = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda _parent, _title, message: dialogs.append(("critical", message))
        or QMessageBox.Ok,
    )
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda _parent, _title, message: dialogs.append(("information", message))
        or QMessageBox.Ok,
    )
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message: dialogs.append(("warning", message))
        or QMessageBox.Ok,
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.Yes,
    )
    actual_status_sync = main_window.sync_local_application_status

    def bounded_status_sync(database_arg, selected_application_id, *, test_mode):
        return actual_status_sync(
            database_arg,
            selected_application_id,
            test_mode=test_mode,
            timeout=4,
        )

    monkeypatch.setattr(
        main_window,
        "sync_local_application_status",
        bounded_status_sync,
    )
    try:
        pull = sync_website_applications(
            db, test_mode=True, operator_id="operator", timeout=4
        )
        assert pull.fetched >= 1
        assert db.connection.execute(
            "SELECT status FROM applicants WHERE application_id=?",
            (application_id,),
        ).fetchone()[0] == "APPLIED"

        read_client = WebsiteSyncClient(
            base_url,
            token=os.environ["QS_OPERATOR_SYNC_TOKEN"],
            timeout=4,
            allow_http_local=True,
        )
        for target in (
            ApplicantStatus.UNDER_REVIEW,
            ApplicantStatus.APPROVED,
        ):
            db.transition(application_id, target, operator_id="operator")
            window.refresh()
            for row in range(window.applications_table.rowCount()):
                if window.applications_table.item(row, 0).text() == application_id:
                    window.applications_table.selectRow(row)
                    break
            _button(window, "Sync status to website").click()
            assert target.value in window.feedback.text()
            website_record = next(
                record for record in read_client.fetch_applications()["applications"]
                if record["application_id"] == application_id
            )
            assert website_record["status"] == target.value

        _button(window, "Sync status to website").click()
        assert window.feedback.text() == (
            "Website status mirror already current: APPROVED."
        )
        final_record = next(
            record for record in read_client.fetch_applications()["applications"]
            if record["application_id"] == application_id
        )
        assert final_record["status"] == "APPROVED"
        assert db.connection.execute("SELECT COUNT(*) FROM licences").fetchone()[0] == 0
        assert dialogs == []
    finally:
        window.close()
        db.close()


@pytest.fixture
def status_reconciliation_server():
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from threading import Thread
    from types import SimpleNamespace
    state = SimpleNamespace(status="APPLIED", posts=[], audit=[], fail_target=None, conflict=False,
                            code=None, malformed=False, changed_after_read=False)
    class Handler(BaseHTTPRequestHandler):
        def reply(self, code, body):
            self.send_response(code); self.end_headers()
            self.wfile.write(json.dumps(body).encode())
        def do_GET(self):
            assert self.headers.get("Authorization") == "Bearer " + TEST_TOKEN
            if state.code:
                return self.reply(state.code,{"error":{"message":"PRIVATE BODY " + TEST_TOKEN}})
            if state.malformed:
                return self.reply(200,{"schema_version":1,"application_id":APPLICATION_ID,"status":[],"result":"already_current"})
            current=state.status
            if state.changed_after_read: state.status="REJECTED"
            self.reply(200,{"schema_version":1,"application_id":APPLICATION_ID,"status":current,"result":"already_current"})
        def do_POST(self):
            target=json.loads(self.rfile.read(int(self.headers['Content-Length'])))['status']
            state.posts.append(target)
            if state.fail_target==target: return self.reply(503,{"error":{"code":"service_unavailable"}})
            if state.conflict or self.headers.get('X-QuantumStudio-Expected-Status')!=state.status:
                return self.reply(409,{"error":{"code":"status_conflict","message":"PRIVATE BODY"}})
            if target!=state.status:
                assert target in {'APPLIED':{'UNDER_REVIEW'},'UNDER_REVIEW':{'APPROVED','REJECTED'}}.get(state.status,set())
                state.audit.append((state.status,target)); state.status=target
                result='updated'
            else: result='already_current'
            self.reply(200,{"schema_version":1,"application_id":APPLICATION_ID,"status":state.status,"result":result})
        def log_message(self,*_): pass
    server=HTTPServer(('127.0.0.1',0),Handler)
    thread=Thread(target=server.serve_forever,daemon=True); thread.start()
    state.url=f'http://127.0.0.1:{server.server_port}'
    yield state
    server.shutdown();server.server_close();thread.join(timeout=2)


@pytest.mark.parametrize('remote,target,expected',[
    ('APPLIED','APPROVED',['UNDER_REVIEW','APPROVED']),
    ('APPLIED','UNDER_REVIEW',['UNDER_REVIEW']),
    ('UNDER_REVIEW','APPROVED',['APPROVED']),
    ('APPLIED','REJECTED',['UNDER_REVIEW','REJECTED']),
])
def test_status_reconciliation_valid_paths(status_reconciliation_server,remote,target,expected):
    state=status_reconciliation_server;state.status=remote
    client=WebsiteStatusSyncClient(state.url,TEST_TOKEN,allow_http_local=True)
    result=client.sync_local_application_status(_LocalStatusDatabase(target),APPLICATION_ID)
    assert result==WebsiteStatusSyncResult(APPLICATION_ID,target,'updated')
    assert state.posts==expected and state.status==target
    assert len(state.audit)==len(expected)


def test_status_reconciliation_already_current_is_idempotent(status_reconciliation_server):
    state=status_reconciliation_server;state.status='APPROVED'
    client=WebsiteStatusSyncClient(state.url,TEST_TOKEN,allow_http_local=True)
    for _ in range(2):
        assert client.sync_local_application_status(_LocalStatusDatabase('APPROVED'),APPLICATION_ID).result=='already_current'
    assert state.status=='APPROVED' and state.audit==[]


def test_status_reconciliation_partial_retry_continues_without_duplicate_audit(status_reconciliation_server):
    state=status_reconciliation_server;state.fail_target='APPROVED'
    client=WebsiteStatusSyncClient(state.url,TEST_TOKEN,allow_http_local=True)
    with pytest.raises(WebsiteStatusResponseError):
        client.sync_local_application_status(_LocalStatusDatabase('APPROVED'),APPLICATION_ID)
    assert state.status=='UNDER_REVIEW' and state.audit==[('APPLIED','UNDER_REVIEW')]
    state.fail_target=None
    assert client.sync_local_application_status(_LocalStatusDatabase('APPROVED'),APPLICATION_ID).result=='updated'
    assert state.audit==[('APPLIED','UNDER_REVIEW'),('UNDER_REVIEW','APPROVED')]


@pytest.mark.parametrize('remote,target',[
    ('REJECTED','APPROVED'),('LICENSE_ISSUED','APPROVED'),('REVOKED','APPROVED'),
    ('EXPIRED','APPROVED'),('APPROVED','REJECTED'),('UNDER_REVIEW','APPLIED'),
])
def test_status_reconciliation_incompatible_histories_fail_closed(status_reconciliation_server,remote,target):
    from operator_tools.licence_manager.website_sync import WebsiteStatusConflictError
    state=status_reconciliation_server;state.status=remote
    client=WebsiteStatusSyncClient(state.url,TEST_TOKEN,allow_http_local=True)
    with pytest.raises(WebsiteStatusConflictError):
        client.sync_local_application_status(_LocalStatusDatabase(target),APPLICATION_ID)
    assert state.posts==[] and state.audit==[] and state.status==remote


@pytest.mark.parametrize('code',[401,403,409])
def test_status_reconciliation_http_categories_reach_gui_safely(status_reconciliation_server,code):
    from operator_tools.licence_manager.website_sync import WebsiteStatusConflictError
    state=status_reconciliation_server;state.code=code
    expected=WebsiteStatusConflictError if code==409 else WebsiteStatusAuthenticationError
    client=WebsiteStatusSyncClient(state.url,TEST_TOKEN,allow_http_local=True)
    with pytest.raises(expected) as failure:
        client.sync_local_application_status(_LocalStatusDatabase('APPROVED'),APPLICATION_ID)
    message=LicenceManagerWindow._error_message(failure.value,'Website status sync')
    assert ('conflict' if code==409 else 'authentication') in message.lower()
    assert TEST_TOKEN not in message and 'PRIVATE BODY' not in message


def test_status_reconciliation_concurrent_change_is_not_repaired(status_reconciliation_server):
    from operator_tools.licence_manager.website_sync import WebsiteStatusConflictError
    state=status_reconciliation_server;state.changed_after_read=True
    client=WebsiteStatusSyncClient(state.url,TEST_TOKEN,allow_http_local=True)
    with pytest.raises(WebsiteStatusConflictError):
        client.sync_local_application_status(_LocalStatusDatabase('APPROVED'),APPLICATION_ID)
    assert state.status=='REJECTED' and state.audit==[] and state.posts==['UNDER_REVIEW']


def test_status_reconciliation_network_error_is_safe_and_distinct(monkeypatch):
    from urllib.error import URLError
    from operator_tools.licence_manager.website_sync import WebsiteStatusNetworkError
    patch_status_response(monkeypatch,b'',error=URLError('PRIVATE BODY '+TEST_TOKEN))
    with pytest.raises(WebsiteStatusNetworkError) as failure:
        WebsiteStatusSyncClient('https://website.example.test',TEST_TOKEN).sync_local_application_status(_LocalStatusDatabase('APPROVED'),APPLICATION_ID)
    message=LicenceManagerWindow._error_message(failure.value,'Website status sync')
    assert 'could not be reached' in message and 'PRIVATE BODY' not in message and TEST_TOKEN not in message


def test_status_reconciliation_malformed_read_is_safe(status_reconciliation_server):
    state=status_reconciliation_server;state.malformed=True
    with pytest.raises(WebsiteStatusResponseError) as failure:
        WebsiteStatusSyncClient(state.url,TEST_TOKEN,allow_http_local=True).sync_local_application_status(_LocalStatusDatabase('APPROVED'),APPLICATION_ID)
    assert 'unexpected response' in LicenceManagerWindow._error_message(failure.value,'Website status sync')
    assert state.posts==[]


@pytest.mark.parametrize('kind,fragment',[
    ('authentication','authentication failed'),('network','could not be reached'),
    ('conflict','status conflict'),('response','unexpected response'),
])
def test_status_error_categories_survive_actual_button_handler(app,database,monkeypatch,kind,fragment):
    from operator_tools.licence_manager.website_sync import WebsiteStatusNetworkError, WebsiteStatusConflictError
    classes={'authentication':WebsiteStatusAuthenticationError,'network':WebsiteStatusNetworkError,
             'conflict':WebsiteStatusConflictError,'response':WebsiteStatusResponseError}
    create_local_application(database)
    def fail(*_,**__): raise classes[kind]('PRIVATE BODY '+TEST_TOKEN)
    monkeypatch.setattr(main_window,'sync_local_application_status',fail)
    dialogs=[]
    monkeypatch.setattr(QMessageBox,'critical',lambda _p,_t,message:dialogs.append(message))
    window=_make_window(database)
    try:
        window.applications_table.selectRow(0)
        _button(window,'Sync status to website').click()
        assert fragment in window.feedback.text().lower()
        assert dialogs==[window.feedback.text()]
        assert 'PRIVATE BODY' not in dialogs[0] and TEST_TOKEN not in dialogs[0]
    finally: window.close()


def test_status_local_decision_change_between_steps_stops_reconciliation(status_reconciliation_server):
    from operator_tools.licence_manager.website_sync import WebsiteStatusConflictError
    state=status_reconciliation_server
    database=_LocalStatusDatabase('APPROVED')
    client=WebsiteStatusSyncClient(state.url,TEST_TOKEN,allow_http_local=True)
    actual_request=client._request_status
    def change_after_step(*args,**kwargs):
        response=actual_request(*args,**kwargs)
        if kwargs.get('expected_status')=='UNDER_REVIEW': database.status='REJECTED'
        return response
    client._request_status=change_after_step
    with pytest.raises(WebsiteStatusConflictError): client.sync_local_application_status(database,APPLICATION_ID)
    assert state.posts==['UNDER_REVIEW'] and state.status=='UNDER_REVIEW'
