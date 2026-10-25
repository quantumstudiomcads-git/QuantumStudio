"""M9B dedicated client, real GUI path, and additive migration regressions."""
import json
import os
import sqlite3
from dataclasses import replace
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox
from operator_tools.licence_manager import device_revocation as module, main_window
from operator_tools.licence_manager.device_revocation import (
    DeviceRevocationClient, DeviceRevocationError, DeviceRevocationResult,
    DeviceRevocationAuthenticationError, DeviceRevocationNetworkError, DeviceRevocationConflictError,
)
from operator_tools.licence_manager.main_window import LicenceManagerWindow
from operator_tools.licence_manager.crypto import DataProtector
from operator_tools.licence_manager.database import Database
from operator_tools.licence_manager.website_sync import WebsiteActivation, WebsiteSyncError

ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
APP = "12345678-1234-4123-8123-123456789abc"
TOKEN = "synthetic-dedicated-revocation-token"
STAMP = "2026-10-24T00:00:00.000Z"


def payload(**changes):
    return {"schema_version": 1, "activation_request_id": ID, "status": "REVOKED",
            "result": "revoked", "revoked_at": STAMP, "reason_code": "DEVICE_REPLACED", **changes}


class Response:
    status = 200
    def __init__(self, body): self.body = body
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def read(self, limit): return self.body[:limit]


def opener(monkeypatch, outcome):
    calls = []
    class Opener:
        def open(self, req, timeout):
            calls.append(req)
            if isinstance(outcome, Exception): raise outcome
            return Response(outcome)
    monkeypatch.setattr(module, "build_opener", lambda *_: Opener())
    return calls


@pytest.mark.parametrize("result", ["revoked", "already_revoked"])
def test_dedicated_client_contract_and_immutable_retry_result(monkeypatch, result):
    calls = opener(monkeypatch, json.dumps(payload(result=result)).encode())
    response = DeviceRevocationClient("https://example.test", TOKEN).revoke(ID, "DEVICE_REPLACED")
    assert response == DeviceRevocationResult(ID, result, STAMP, "DEVICE_REPLACED")
    assert calls[0].full_url == f"https://example.test/api/operator/activations/{ID}/revoke"
    assert calls[0].get_method() == "POST"
    assert calls[0].get_header("Authorization") == "Bearer " + TOKEN
    assert json.loads(calls[0].data) == {"schema_version": 1, "reason_code": "DEVICE_REPLACED", "expected_status": "AUTHORIZED"}


@pytest.mark.parametrize("code,expected", [(401, DeviceRevocationAuthenticationError), (403, DeviceRevocationAuthenticationError),
    (409, DeviceRevocationConflictError), (503, DeviceRevocationError), (302, DeviceRevocationError)])
def test_http_errors_are_typed_and_never_expose_raw_server_content(monkeypatch, code, expected):
    from io import BytesIO
    opener(monkeypatch, HTTPError("https://example.test", code, TOKEN, {}, BytesIO(b'private server body')))
    with pytest.raises(expected) as caught: DeviceRevocationClient("https://example.test", TOKEN).revoke(ID, "DEVICE_REPLACED")
    assert TOKEN not in str(caught.value) and 'private' not in str(caught.value)


@pytest.mark.parametrize("outcome", [URLError(TOKEN), TimeoutError(TOKEN), OSError(TOKEN)])
def test_network_outcome_is_unknown_and_safe_to_retry(monkeypatch, outcome):
    opener(monkeypatch, outcome)
    with pytest.raises(DeviceRevocationNetworkError) as caught:
        DeviceRevocationClient("https://example.test", TOKEN).revoke(ID, "DEVICE_REPLACED")
    assert TOKEN not in str(caught.value)


@pytest.mark.parametrize("body", [b'not JSON', b'x'*4097, json.dumps(payload(schema_version=True)).encode(),
    json.dumps(payload(status='AUTHORIZED')).encode(), json.dumps(payload(reason_code='OTHER')).encode(),
    json.dumps(payload(revoked_at='bad')).encode(), json.dumps(payload(activation_request_id=APP)).encode(),
    json.dumps(payload(secret='private')).encode()])
def test_client_rejects_unexpected_or_malformed_contract(monkeypatch, body):
    opener(monkeypatch, body)
    with pytest.raises(DeviceRevocationError): DeviceRevocationClient("https://example.test", TOKEN).revoke(ID, "DEVICE_REPLACED")


def test_configuration_and_controlled_reason_validation_fail_before_network(monkeypatch):
    monkeypatch.delenv('QS_OPERATOR_ACTIVATION_REVOKE_TOKEN', raising=False)
    with pytest.raises(DeviceRevocationAuthenticationError): DeviceRevocationClient('https://example.test')
    with pytest.raises(DeviceRevocationError): DeviceRevocationClient('http://remote.example.test', TOKEN, allow_http_local=True)
    with pytest.raises(DeviceRevocationError): DeviceRevocationClient('http://127.0.0.1', TOKEN, allow_http_local=True, production=True)
    client = DeviceRevocationClient('https://example.test', TOKEN)
    with pytest.raises(DeviceRevocationError): client.revoke(ID, 'arbitrary')
    with pytest.raises(DeviceRevocationError): client.revoke('not-an-id', 'OTHER')
    with pytest.raises(DeviceRevocationError): client.revoke(ID, 'OTHER', reason_text='x'*241)


@pytest.fixture
def window(tmp_path):
    app = QApplication.instance() or QApplication([])
    db = Database(tmp_path/'operator', DataProtector.for_testing(b'R'*32))
    window = LicenceManagerWindow(test_mode=True, database=db)
    activation = WebsiteActivation(ID, APP, 'dev_'+'a'*32, 'windows', 'x86_64', '0.2.0',
        'AUTHORIZED', None, STAMP, STAMP, STAMP, None)
    window._website_activations = (activation,)
    window._render_website_activations()
    window.website_activations_table.selectRow(0)
    yield window, activation
    window.close();db.close()
    assert app is not None


def confirm(monkeypatch):
    monkeypatch.setattr(QInputDialog, 'getItem', lambda *_: ('DEVICE_REPLACED', True))
    monkeypatch.setattr(QMessageBox, 'question', lambda *_: QMessageBox.Yes)


@pytest.mark.parametrize('result', ['revoked', 'already_revoked'])
def test_gui_button_runs_real_client_and_refreshes_authoritative_state(window, monkeypatch, result):
    win, activation = window
    monkeypatch.setenv('QS_OPERATOR_WEBSITE_URL', 'http://127.0.0.1:8788')
    monkeypatch.setenv('QS_OPERATOR_ACTIVATION_REVOKE_TOKEN', TOKEN)
    calls = opener(monkeypatch, json.dumps(payload(result=result)).encode())
    confirm(monkeypatch)
    monkeypatch.setattr(main_window, 'fetch_website_activations', lambda **_: (replace(activation, status='REVOKED', revoked_at=STAMP),))
    assert win.revoke_website_device_button.isEnabled()
    win.revoke_website_device_button.click()
    assert len(calls) == 1
    assert win.website_activations_table.item(0,3).text() == 'REVOKED'
    assert not win.revoke_website_device_button.isEnabled()
    assert not win.issue_website_test_licence_button.isEnabled()
    assert ('already revoked' if result == 'already_revoked' else 'slot released') in win.feedback.text()


@pytest.mark.parametrize('cancel_at', ['reason', 'confirmation'])
def test_gui_cancellation_sends_no_revocation(window, monkeypatch, cancel_at):
    win, _ = window
    monkeypatch.setattr(main_window, 'revoke_website_device', lambda *_a, **_kw: pytest.fail('No revocation permitted'))
    monkeypatch.setattr(QInputDialog, 'getItem', lambda *_: ('DEVICE_REPLACED', cancel_at != 'reason'))
    monkeypatch.setattr(QMessageBox, 'question', lambda *_: QMessageBox.No)
    win.revoke_website_device_button.click()
    assert win._website_activations[0].status == 'AUTHORIZED'


@pytest.mark.parametrize('outcome,word', [(HTTPError('https://test',401,TOKEN,{},None),'authentication'),
    (HTTPError('https://test',409,TOKEN,{},None),'conflict'), (URLError(TOKEN),'could not be reached'),
    (HTTPError('https://test',503,TOKEN,{},None),'unexpected response'), (b'private raw body','unexpected response')])
def test_gui_real_client_error_path_preserves_distinct_safe_messages(window, monkeypatch, outcome, word):
    win, _ = window
    monkeypatch.setenv('QS_OPERATOR_WEBSITE_URL', 'http://127.0.0.1:8788')
    monkeypatch.setenv('QS_OPERATOR_ACTIVATION_REVOKE_TOKEN', TOKEN)
    opener(monkeypatch, outcome);confirm(monkeypatch)
    dialogs=[];monkeypatch.setattr(QMessageBox, 'critical', lambda *_args: dialogs.append(_args[-1]))
    win.revoke_website_device_button.click()
    assert len(dialogs)==1 and word in dialogs[0]
    assert TOKEN not in dialogs[0] and 'private raw body' not in dialogs[0]
    assert win._website_activations[0].status == 'AUTHORIZED'


def test_gui_keeps_confirmed_revoked_state_when_refresh_fails(window, monkeypatch):
    win, _ = window;confirm(monkeypatch)
    monkeypatch.setattr(main_window, 'revoke_website_device', lambda *_a, **_kw: DeviceRevocationResult(ID,'revoked',STAMP,'DEVICE_REPLACED'))
    def unavailable(**_): raise WebsiteSyncError('private')
    monkeypatch.setattr(main_window, 'fetch_website_activations', unavailable)
    win.revoke_website_device_button.click()
    assert win._website_activations[0].status == 'REVOKED' and not win.revoke_website_device_button.isEnabled()
    assert 'confirmed' in win.feedback.text() and 'refresh failed' in win.feedback.text()


def test_additive_migration_preserves_existing_grant_activation_and_all_licence_foreign_keys(tmp_path):
    from tests.licensing.test_account_entitlements import migrate, seed, approve, register
    db=sqlite3.connect(tmp_path/'upgrade.sqlite3');db.row_factory=sqlite3.Row
    try:
        migrate(db,10);seed(db);approve(db);register(db,'a',ID)
        db.execute("INSERT INTO published_licences VALUES(?, 'lic-original', 'original signed bytes', 'hash', 1, 'PUBLISHED')",(ID,))
        db.execute("INSERT INTO licence_device_challenges VALUES('challenge',?,'dev_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',?,'original proof',9999999999,NULL)",(ID,'a'*64));db.commit()
        tables=['beta_activations','account_entitlements','published_licences','licence_device_challenges']
        original={table:[dict(r) for r in db.execute('SELECT * FROM '+table)] for table in tables}
        db.executescript(Path('website/migrations/0011_device_revocation.sql').read_text(encoding='utf-8'))
        for table in tables:
            current=[dict(r) for r in db.execute('SELECT * FROM '+table)]
            assert len(current)==len(original[table])
            for old,new in zip(original[table],current): assert all(new[k]==v for k,v in old.items())
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
        db.execute("UPDATE beta_activations SET status='REVOKED',revoked_at=? WHERE activation_request_id=?",(STAMP,ID));db.commit()
        with pytest.raises(sqlite3.IntegrityError): db.execute("UPDATE beta_activations SET status='AUTHORIZED' WHERE activation_request_id=?",(ID,))
    finally: db.close()
