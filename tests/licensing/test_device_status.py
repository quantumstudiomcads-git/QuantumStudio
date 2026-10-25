"""M9C: no offline grant, durable tombstones, fresh policy and authenticated time."""
from dataclasses import replace
from copy import deepcopy
import json
import pytest
from tests.licensing.test_licence_delivery import bundle
from backend.licensing.service import LicensingService
from backend.licensing.connectors.device_status import DeviceStatusNetworkError, DeviceStatusError
from backend.licensing.verifier import LeaseValidationError
from backend.licensing.models import DecisionReason, ImplementationState
from backend.licensing.enforcement import CalculationAuthorizationBoundary, EntitlementDenied
from tests.helpers.licensing import StatusFixture


@pytest.fixture
def online(bundle):
    b=bundle
    b.service.accept_lease(b.envelope)
    b.remote=b.service._online.connector
    return b


def restart(b, *, online=True, now=None):
    return LicensingService(trusted_public_keys={b.signer.kid:b.signer.public_key},device_identity=b.device,
        lease_store=b.store,now=lambda:b.now if now is None else now,
        status_connector=b.remote if online else Offline(),identity_service=b.identity_service,test_mode=True)


class Offline:
    def challenge(self,*_): raise DeviceStatusNetworkError('unreachable')


def revoke(b):
    b.remote.state='REVOKED';b.remote.revision+=1
    assert b.service.refresh_online_authorization()=='revoked'


def test_valid_signed_matching_online_device_is_active_and_grants_remain_signed(online):
    b=online
    assert b.service.diagnostics_summary()['status']=='online_validation_required'
    assert b.service.can_start_protected_work().allowed
    assert b.service.diagnostics_summary()['status']=='active'
    assert b.service.authorize_feature('workspace:device_builder').allowed
    assert not b.service.authorize_feature('not-in-signed-grant').allowed
    assert b.store.load_authorization_state()['records']


def test_every_new_work_gate_authenticates_again_not_cached_success(online):
    b=online
    assert b.service.can_start_protected_work().allowed
    count=b.remote.calls
    assert b.service.can_start_protected_work().allowed and b.remote.calls==count+1
    b.remote.failure=DeviceStatusNetworkError('unreachable')
    assert not b.service.can_start_protected_work().allowed
    assert b.service.diagnostics_summary()['status']=='online_validation_required'
    assert b.service.authorize_read().allowed


def test_offline_startup_denies_even_after_previous_success(online):
    b=online;assert b.service.can_start_protected_work().allowed
    service=restart(b,online=False)
    assert service.diagnostics_summary()['status']=='online_validation_required'
    assert not service.can_start_protected_work().allowed
    assert service.diagnostics_summary()['status']=='online_validation_required'


def test_revoked_survives_offline_restart_old_cache_and_check(online):
    b=online;assert b.service.can_start_protected_work().allowed;revoke(b)
    records=deepcopy(b.store.load_authorization_state())
    service=restart(b,online=False)
    assert service.diagnostics_summary()['status']=='revoked'
    service.accept_lease(b.envelope)
    assert not service.can_start_protected_work().allowed
    assert service.diagnostics_summary()['status']=='revoked'
    service.install_delivered_lease(b.envelope)
    assert service.diagnostics_summary()['status']=='revoked'
    assert b.store.load_authorization_state()==records and b.store.load_lease()==b.envelope


def test_trust_reload_never_erases_tombstone(online,monkeypatch):
    b=online;revoke(b);monkeypatch.setenv('QS_TEST_LICENSING','1')
    b.service.reload_local_test_trust(b.trust_path)
    assert b.service.diagnostics_summary()['status']=='revoked'
    assert not b.service.can_start_protected_work().allowed


def test_authenticated_server_expiry_overrides_rolled_back_wall_clock(online):
    b=online
    b.remote.now=b.envelope['expires_at']
    service=restart(b,now=b.now-100000)
    assert not service.can_start_protected_work().allowed
    assert service.diagnostics_summary()['status']=='expired'


def test_clock_rollback_requires_fresh_validation_and_no_grace(online):
    b=online;assert b.service.can_start_protected_work().allowed
    service=restart(b,now=b.now-100000)
    assert service.clock_validation_required
    assert not service.authorize_feature('workspace:device_builder').allowed
    assert service.can_start_protected_work().allowed
    assert not service.clock_validation_required
    b.remote.now=b.envelope['expires_at']
    assert not service.can_start_protected_work().allowed
    assert service.diagnostics_summary()['status']=='expired'


@pytest.mark.parametrize('change',[{'activation_id':'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'}, {'licence_id':'wrong'},
    {'envelope_sha256':'0'*64},{'installation_id':'dev_'+'b'*32},{'device_public_key_hash':'b'*64},
    {'authorization_revision':0},{'entitlement_revision':0},{'entitlement_id':'wrong'},
    {'entitlement_expires_at':1},{'checked_at':1},{'schema_version':True},{'feature_entitlements':['feature:*']}])
def test_mismatched_malformed_or_stale_status_is_not_a_network_outage(online,change):
    b=online;b.remote.changes=change
    assert not b.service.can_start_protected_work().allowed
    assert b.service.diagnostics_summary()['status']=='invalid_licence'


@pytest.mark.parametrize('field',['authorization_revision','entitlement_revision','entitlement_id','server_time'])
def test_persisted_binding_and_revision_highwater_fail_closed(online,field):
    b=online;b.remote.revision=3;b.remote.entitlement_revision=3
    assert b.service.can_start_protected_work().allowed
    b.remote.changes={field:'ent_'+'b'*32 if field=='entitlement_id' else 1}
    assert not b.service.can_start_protected_work().allowed
    assert b.service.diagnostics_summary()['status']=='invalid_licence'


def test_changed_state_without_revision_increment_is_invalid(online):
    b=online;assert b.service.can_start_protected_work().allowed;b.remote.state='REVOKED'
    assert b.service.refresh_online_authorization()=='invalid_licence'


@pytest.mark.parametrize('case',['signature','device'])
def test_local_invalidity_denies_before_any_status_request(online,case):
    b=online
    if case=='signature': b.service._verified_envelope['signature']='invalid'
    else: b.service.device_identity=replace(b.device,device_id='dev_'+'b'*32)
    assert not b.service.can_start_protected_work().allowed and b.remote.calls==0
    assert b.service.diagnostics_summary()['status']==('invalid_licence' if case=='signature' else 'invalid_device')


def test_invalid_cached_device_has_distinct_startup_state(online):
    b=online
    service=LicensingService(trusted_public_keys={b.signer.kid:b.signer.public_key},
        device_identity=replace(b.device,device_id='dev_'+'b'*32),lease_store=b.store,now=lambda:b.now)
    assert service.diagnostics_summary()['status']=='invalid_device'
    assert not service.can_start_protected_work().allowed


def test_corrupt_authorization_state_does_not_erase_or_grant(online):
    b=online;assert b.service.can_start_protected_work().allowed
    b.store.authorization_path.write_text('{bad json',encoding='utf-8')
    service=restart(b)
    assert not service.can_start_protected_work().allowed
    assert b.store.authorization_path.read_text()=='{bad json'


def test_distinct_verified_replacement_can_authorize_without_erasing_old_tombstone(online):
    b=online;revoke(b)
    # Simulates explicit installation recovery; the historical record is retained.
    envelope={k:v for k,v in b.envelope.items() if k not in {'kid','signature'}}
    envelope['licence_id']='lic_bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
    signed=b.signer.sign_test_fixture_only(envelope)
    b.service.accept_lease(signed)
    b.remote=StatusFixture(signed,b.now,b.identity_service)
    b.service._online.connector=b.remote
    b.remote.challenge_original=b.remote.challenge
    def challenge(*args):
        message=b.remote.challenge_original(*args);message['activation_request_id']='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';return message
    b.remote.challenge=challenge
    assert b.service.can_start_protected_work().allowed
    assert len(b.store.load_authorization_state()['records'])==2
    b.service.accept_lease(b.envelope)
    assert b.service.diagnostics_summary()['status']=='revoked'


def test_compile_and_new_execution_use_authoritative_gate(online):
    from frontend.calculations.catalog import CALCULATIONS
    from frontend.calculations.reconciliation import CalculationDescriptor, ExecutionSupport
    from frontend.services.calculation_service import CalculationService
    b=online
    descriptor=CalculationDescriptor(next(c for c in CALCULATIONS if c.id=='scf'),ExecutionSupport.IMPLEMENTED,True)
    assert CalculationAuthorizationBoundary(b.service).authorize((descriptor,))[0].allowed
    b.remote.failure=DeviceStatusNetworkError('unreachable')
    with pytest.raises(EntitlementDenied): CalculationAuthorizationBoundary(b.service).authorize((descriptor,))
    with pytest.raises(EntitlementDenied): CalculationService(CALCULATIONS,licensing_service=b.service).require_protected_work()


def test_ui_check_cached_licence_uses_status_not_delivery(qtbot,online):
    from frontend.app.account_dialog import AccountLicensingDialog
    b=online;b.remote.state='REVOKED';b.remote.revision=2
    dialog=AccountLicensingDialog(licensing_service=b.service)
    qtbot.addWidget(dialog);dialog.check_button.click()
    qtbot.waitUntil(lambda:dialog._worker is None,timeout=3000)
    assert 'Licence status: Revoked' in dialog.licence_summary.text()
    assert not b.service.can_start_protected_work().allowed


@pytest.mark.parametrize('state',['AUTHORIZED','REVOKED','offline'])
def test_main_startup_worker_checks_once_and_never_uses_cached_success(qtbot,online,state):
    from PySide6.QtWidgets import QWidget
    from frontend.app.account_dialog import schedule_startup_authorization
    b=online
    if state=='offline': b.remote.failure=DeviceStatusNetworkError('unreachable')
    else: b.remote.state=state;b.remote.revision=2
    window=QWidget();window.licensing_service=b.service;qtbot.addWidget(window)
    schedule_startup_authorization(window)
    expected={'AUTHORIZED':'active','REVOKED':'revoked','offline':'online_validation_required'}[state]
    qtbot.waitUntil(lambda:b.service.diagnostics_summary()['status']==expected,timeout=3000)
    # Wait for the thread as well; no periodic worker is scheduled afterward.
    qtbot.waitUntil(lambda:window._licensing_authorization_worker not in __import__('frontend.app.account_dialog',fromlist=['_RUNNING'])._RUNNING,timeout=3000)
    assert b.remote.calls==(0 if state=='offline' else 1)


def test_replayed_status_challenge_is_rejected_even_with_valid_old_response(online):
    b=online;assert b.service.can_start_protected_work().allowed
    old=dict(b.remote.message)
    b.remote.challenge=lambda *_:old
    assert b.service.refresh_online_authorization()=='invalid_licence'


def test_status_migration_preserves_licence_foreign_keys_grants_and_revoked_history(tmp_path):
    import sqlite3
    from pathlib import Path
    from tests.licensing.test_account_entitlements import migrate,seed,approve,register
    db=sqlite3.connect(tmp_path/'m9c.sqlite3');db.row_factory=sqlite3.Row
    try:
        migrate(db,11);seed(db);approve(db);register(db,'a','aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa')
        db.execute("INSERT INTO published_licences VALUES('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','lic-original','original signed bytes','hash',1,'PUBLISHED')");db.commit()
        tables=['beta_activations','account_entitlements','published_licences','licence_device_challenges','beta_audit_events']
        original={t:[dict(r) for r in db.execute('SELECT * FROM '+t)] for t in tables}
        db.executescript(Path('website/migrations/0012_device_status.sql').read_text(encoding='utf-8'))
        for table,rows in original.items():
            current=[dict(r) for r in db.execute('SELECT * FROM '+table)]
            assert len(current)==len(rows)
            for before,after in zip(rows,current): assert all(after[k]==v for k,v in before.items())
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
        db.execute("UPDATE beta_activations SET status='REVOKED',revoked_at='2026-10-25T00:00:00Z',revocation_reason_code='OTHER'")
        assert db.execute('SELECT authorization_revision FROM beta_activations').fetchone()[0]==2
        db.execute("UPDATE beta_activations SET status='REVOKED'")
        assert db.execute('SELECT authorization_revision FROM beta_activations').fetchone()[0]==2
        assert [dict(r) for r in db.execute('SELECT * FROM account_entitlements')]==original['account_entitlements']
    finally: db.close()


def test_authorized_replacement_device_b_is_active_while_a_stays_revoked(online,tmp_path):
    from backend.licensing.device_identity import DeviceIdentityService,InMemorySecureKeyStore
    from backend.licensing.lease_store import LeaseStore
    from backend.runtime.paths import runtime_paths
    b=online;revoke(b)
    identity=DeviceIdentityService(InMemorySecureKeyStore());device=identity.load_or_create()
    payload={k:v for k,v in b.envelope.items() if k not in {'kid','signature'}}
    payload.update(licence_id='lic_bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',device_id=device.device_id,device_public_key_hash=device.public_key_hash)
    envelope=b.signer.sign_test_fixture_only(payload)
    remote=StatusFixture(envelope,b.now,identity);remote.activation_id='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
    paths=runtime_paths(environ={'QUANTUM_STUDIO_DATA_ROOT':str(tmp_path/'device-b')})
    service=LicensingService(trusted_public_keys={b.signer.kid:b.signer.public_key},device_identity=device,
        lease_store=LeaseStore(paths),status_connector=remote,identity_service=identity,now=lambda:b.now)
    service.accept_lease(envelope)
    assert service.can_start_protected_work().allowed
    assert service.diagnostics_summary()['status']=='active'
    assert service.lease.expires_at==b.envelope['expires_at']
    assert restart(b,online=False).diagnostics_summary()['status']=='revoked'


def test_actual_unreachable_status_connector_is_online_required_not_revoked_or_expired(online):
    import socket
    from backend.licensing.connectors.device_status import WebsiteDeviceStatusConnector
    b=online
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
    b.service._online.connector=WebsiteDeviceStatusConnector(f'http://127.0.0.1:{port}',allow_local_http=True,timeout=1)
    assert not b.service.can_start_protected_work().allowed
    assert b.service.diagnostics_summary()['status']=='online_validation_required'
