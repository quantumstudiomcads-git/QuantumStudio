"""M7: real M5 envelope, device proof, explicit trust and offline installation."""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from dataclasses import replace
from types import SimpleNamespace
from threading import Event, Thread
from http.server import BaseHTTPRequestHandler, HTTPServer

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from PySide6.QtWidgets import QFileDialog
from backend.runtime.paths import runtime_paths
from backend.licensing.canonical import canonical_json, b64url_decode
from backend.licensing.device_identity import DeviceIdentityService, InMemorySecureKeyStore, SecureStorageUnavailable
from backend.licensing.lease_store import LeaseStore
from backend.licensing.service import LicensingService
from backend.licensing.verifier import LeaseValidationError
from backend.licensing.local_test_trust import load_test_trust, configured_licensing_service
from backend.licensing import local_test_trust
from backend.licensing.licence_delivery import LicenceDeliveryService
from backend.licensing.connectors.licence_delivery import WebsiteLicenceDeliveryConnector, LicenceDeliveryError
from operator_tools.licence_manager.database import Database
from operator_tools.licence_manager.crypto import DataProtector
from operator_tools.licence_manager.signing import TestEphemeralAuthority as _TestSigner
from operator_tools.licence_manager.issuance import issue_website_activation_for_testing
from operator_tools.licence_manager.website_sync import WebsiteActivation, WebsiteLicenceSyncError
from operator_tools.licence_manager.licence_delivery import publish_website_test_licence, stored_test_licence, PUBLIC_ENVELOPE_FIELDS
from operator_tools.licence_manager.main_window import LicenceManagerWindow
from operator_tools.licence_manager import main_window
from frontend.app.account_dialog import AccountLicensingDialog


@pytest.fixture
def bundle(tmp_path):
    identity_service = DeviceIdentityService(InMemorySecureKeyStore())
    device = identity_service.load_or_create()
    db = Database(tmp_path / "operator", DataProtector.for_testing(b'T'*32))
    activation = WebsiteActivation(activation_request_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        application_id="12345678-1234-4123-8123-123456789abc",installation_id=device.device_id,
        device_public_key_hash=device.public_key_hash,platform="windows",architecture="x86_64",app_version="0.2.0",
        status="AUTHORIZED",flag_reason=None,created_at="2026-10-20T00:00:00Z",updated_at="2026-10-20T00:00:00Z",authorized_at="2026-10-20T00:00:00Z",revoked_at=None)
    signer = _TestSigner()
    now = int(time.time())
    envelope = issue_website_activation_for_testing(db, signer, activation, now=now)
    paths = runtime_paths(environ={"QUANTUM_STUDIO_DATA_ROOT":str(tmp_path / "desktop")},home=tmp_path)
    store = LeaseStore(paths)
    service = LicensingService(trusted_public_keys={signer.kid:signer.public_key},device_identity=device,lease_store=store,now=lambda:now,test_mode=True)
    trust_path = tmp_path / "trust.json"
    trust_path.write_text(json.dumps(stored_test_licence(db,activation)[1]),encoding="utf-8")
    b = SimpleNamespace(identity_service=identity_service,device=device,db=db,activation=activation,signer=signer,
                        envelope=envelope,store=store,service=service,now=now,paths=paths,trust_path=trust_path)
    yield b
    db.close()


def challenge(b):
    return {"schema_version":1,"purpose":"quantum-studio:licence-retrieve:v1","challenge_id":secrets.token_hex(32),
        "nonce":secrets.token_hex(32),"activation_request_id":b.activation.activation_request_id,
        "installation_id":b.device.device_id,"device_public_key_hash":b.device.public_key_hash,"expires_at":int(time.time())+120}


class FakeDelivery:
    def __init__(self,b,result=None):
        self.b=b
        self.result=result
        self.message=challenge(b)
        self.calls=[]
    def get_device_challenge(self,installation_id,activation_request_id=None):
        self.calls.append((installation_id,activation_request_id))
        return self.message
    def retrieve_device_licence(self,proof):
        # Independent cryptographic check that the transport receives a real device proof.
        Ed25519PublicKey.from_public_bytes(self.b.device.public_key).verify(b64url_decode(proof['signature']),canonical_json(self.message))
        assert set(proof)=={'installation_id','challenge_id','public_key','signature'}
        return self.result if self.result is not None else {"state":"available","envelope":self.b.envelope,
            "envelope_sha256":hashlib.sha256(canonical_json(self.b.envelope)).hexdigest()}


def delivery(b,result=None):
    return LicenceDeliveryService(b.service,FakeDelivery(b,result),b.identity_service)


def resign(b,**changes):
    payload={k:v for k,v in b.envelope.items() if k not in {'kid','signature'}}
    payload.update(changes)
    return b.signer.sign_test_fixture_only(payload)


def test_valid_retrieval_verifies_persists_and_reopens_offline(bundle):
    b=bundle
    assert delivery(b).retrieve_and_install(b.activation.activation_request_id)=='installed'
    assert b.store.load_lease()==b.envelope
    assert b.service.authorize_feature('workspace:device_builder').allowed
    # Recreate both identity provider and service without any website/connector.
    device=DeviceIdentityService(b.identity_service.store).load_or_create()
    restarted=LicensingService(trusted_public_keys=load_test_trust(b.trust_path),device_identity=device,lease_store=LeaseStore(b.paths),now=lambda:b.now,test_mode=True)
    assert restarted.lease.licence_id==b.envelope['licence_id']
    assert restarted.diagnostics_summary()['status']=='active'
    assert restarted.authorize_feature('workspace:device_builder').allowed


def test_repeated_install_is_idempotent_and_conflicting_envelope_is_preserved(bundle):
    b=bundle
    b.service.install_delivered_lease(b.envelope)
    b.service.install_delivered_lease(dict(b.envelope))
    before=b.store.lease_path.read_bytes()
    with pytest.raises(LeaseValidationError,match='different'):
        b.service.install_delivered_lease(resign(b,nonce='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'))
    assert b.store.lease_path.read_bytes()==before


@pytest.mark.parametrize('case',['signature','device','issuer','expired','not_before','offline_expired','clock'])
def test_invalid_or_out_of_policy_licence_never_persists_or_grants(bundle,case):
    b=bundle
    envelope=dict(b.envelope)
    if case=='signature': envelope['plan_id']='enterprise'
    if case=='device': b.service.device_identity=replace(b.device,device_id='dev_'+'f'*32)
    if case=='issuer': b.service._trusted_public_keys={}
    if case=='expired': envelope=resign(b,issued_at=b.now-100,not_before=b.now-100,expires_at=b.now-1,offline_until=b.now-1)
    if case=='not_before': envelope=resign(b,not_before=b.now+60)
    if case=='offline_expired': envelope=resign(b,issued_at=b.now-100,not_before=b.now-100,offline_until=b.now-1)
    if case=='clock': b.service.clock_validation_required=True
    with pytest.raises(LeaseValidationError): b.service.install_delivered_lease(envelope)
    assert b.store.load_lease() is None and b.service.lease is None
    assert not b.service.authorize_feature('workspace:device_builder').allowed


def test_cache_save_failure_does_not_grant_memory_only_licence(bundle,monkeypatch):
    b=bundle
    def fail(_e): raise OSError('synthetic full disk')
    monkeypatch.setattr(b.store,'save_lease',fail)
    with pytest.raises(OSError): b.service.install_delivered_lease(b.envelope)
    assert b.service.lease is None


def test_expired_cache_uses_existing_policy_and_reports_expired(bundle):
    b=bundle
    b.store.save_lease(resign(b,issued_at=b.now-100,not_before=b.now-100,expires_at=b.now-1,offline_until=b.now-1))
    restarted=LicensingService(trusted_public_keys={b.signer.kid:b.signer.public_key},device_identity=b.device,lease_store=b.store,now=lambda:b.now)
    assert restarted.diagnostics_summary()['status']=='expired'
    assert not restarted.authorize_feature('workspace:device_builder').allowed
    assert restarted.authorize_read().allowed


@pytest.mark.parametrize('result',[{'state':'pending'},{'state':'available','licence_status':'ISSUED'},{'status':'AUTHORIZED'}])
def test_metadata_and_pending_never_grant_entitlement(bundle,result):
    b=bundle
    if result=={'state':'pending'}: assert delivery(b,result).retrieve_and_install()=='pending'
    else:
        with pytest.raises(LicenceDeliveryError): delivery(b,result).retrieve_and_install()
    assert b.service.lease is None and b.store.load_lease() is None


def test_digest_or_arbitrary_website_key_cannot_establish_trust(bundle):
    b=bundle
    for extra in ({'envelope_sha256':'f'*64},{'public_key':'website-must-not-bootstrap-trust'}):
        result={'state':'available','envelope':b.envelope,'envelope_sha256':hashlib.sha256(canonical_json(b.envelope)).hexdigest(),**extra}
        with pytest.raises(LicenceDeliveryError): delivery(b,result).retrieve_and_install()
    assert b.service.lease is None


def test_cancellation_before_install_does_not_cache(bundle):
    b=bundle
    cancelled=Event()
    connector=FakeDelivery(b)
    original=connector.retrieve_device_licence
    def stop(proof):
        result=original(proof);cancelled.set();return result
    connector.retrieve_device_licence=stop
    with pytest.raises(LicenceDeliveryError,match='cancelled'):
        LicenceDeliveryService(b.service,connector,b.identity_service).retrieve_and_install(cancelled=cancelled)
    assert b.store.load_lease() is None


@pytest.mark.parametrize('change',[{'purpose':'arbitrary-signing'},{'installation_id':'dev_'+'f'*32},{'expires_at':0},{'nonce':'bad'},{'private_key':'forbidden'}])
def test_device_key_signing_is_narrow_and_bound(bundle,change):
    with pytest.raises(SecureStorageUnavailable):
        bundle.identity_service.sign_licence_challenge({**challenge(bundle),**change},bundle.device)


def test_missing_or_changed_device_key_does_not_generate_replacement(bundle):
    missing=InMemorySecureKeyStore()
    with pytest.raises(SecureStorageUnavailable):
        DeviceIdentityService(missing).sign_licence_challenge(challenge(bundle),bundle.device)
    assert missing.value is None
    other=DeviceIdentityService(InMemorySecureKeyStore());other.load_or_create()
    with pytest.raises(SecureStorageUnavailable): other.sign_licence_challenge(challenge(bundle),bundle.device)


def test_explicit_test_trust_and_original_signer_survive_operator_restart(bundle):
    b=bundle
    keys=load_test_trust(b.trust_path)
    assert keys=={b.signer.kid:b.signer.public_key}
    next_signer=_TestSigner()
    envelope,record=stored_test_licence(b.db,b.activation)
    assert envelope==b.envelope and record['kid']!=next_signer.kid
    assert 'private' not in json.dumps(record)


def test_test_trust_double_opt_in_is_not_production_fallback(bundle,monkeypatch):
    b=bundle
    monkeypatch.setenv('QS_TEST_LICENCE_TRUST_FILE',str(b.trust_path))
    monkeypatch.delenv('QS_TEST_LICENSING',raising=False)
    sentinel=LicensingService(device_identity=b.device)
    monkeypatch.setattr(LicensingService,'production',classmethod(lambda cls:sentinel))
    assert configured_licensing_service() is sentinel
    monkeypatch.setenv('QS_TEST_LICENSING','1')
    monkeypatch.setattr(local_test_trust,'LeaseStore',lambda:b.store)
    monkeypatch.setattr(local_test_trust,'production_secure_store',lambda _paths:b.identity_service.store)
    service=configured_licensing_service()
    assert service.test_mode and service.device_identity==b.device
    b.trust_path.write_text('{}')
    invalid=configured_licensing_service()
    assert invalid.error_code=='test_trust_invalid' and invalid.lease is None


@pytest.mark.parametrize('field,value',[('domain','licence'),('kid','lic-production'),('public_key','bad'),('algorithm','RSA')])
def test_test_trust_rejects_other_domains_and_malformed_keys(bundle,field,value):
    record=json.loads(bundle.trust_path.read_text());record[field]=value
    bundle.trust_path.write_text(json.dumps(record))
    with pytest.raises(LeaseValidationError): load_test_trust(bundle.trust_path)


@pytest.fixture
def server(bundle):
    b=bundle
    class Handler(BaseHTTPRequestHandler):
        received=[]
        code=200
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            self.received.append((self.path,dict(self.headers),body))
            if self.path.endswith('/publish'):
                data={'schema_version':1,'result':'published','envelope_sha256':hashlib.sha256(canonical_json(b.envelope)).hexdigest()}
            elif self.path.endswith('device-challenge'):
                self.server.message=challenge(b);data={'challenge':self.server.message}
            else:
                Ed25519PublicKey.from_public_bytes(b.device.public_key).verify(b64url_decode(body['signature']),canonical_json(self.server.message))
                data={'state':'available','envelope':b.envelope,'envelope_sha256':hashlib.sha256(canonical_json(b.envelope)).hexdigest()}
            if self.code!=200: data={'error':{'code':'publication_conflict','message':'private-server-text-never-display'}}
            self.send_response(self.code);self.end_headers();self.wfile.write(json.dumps(data).encode())
        def log_message(self,*_args): pass
    http=HTTPServer(('127.0.0.1',0),Handler);thread=Thread(target=http.serve_forever,daemon=True);thread.start()
    yield f'http://127.0.0.1:{http.server_port}',Handler
    http.shutdown();http.server_close();thread.join(timeout=2)


def test_operator_publication_sends_only_signed_artifact_and_dedicated_credential(bundle,server):
    url,handler=server;b=bundle
    assert publish_website_test_licence(b.db,b.activation,test_mode=True,base_url=url,token='synthetic-publish-token')=='published'
    path,headers,body=handler.received[0]
    assert path.endswith('/publish') and headers['Authorization']=='Bearer synthetic-publish-token'
    assert set(body)=={'schema_version','envelope'} and set(body['envelope'])==PUBLIC_ENVELOPE_FIELDS
    assert body['envelope']==b.envelope
    assert all(key not in json.dumps(body) for key in ('private_key','protected_data','seed'))


def test_actual_cookie_free_delivery_transport_verifies_and_installs(bundle,server):
    url,handler=server;b=bundle
    connector=WebsiteLicenceDeliveryConnector(url,allow_local_http=True)
    assert LicenceDeliveryService(b.service,connector,b.identity_service).retrieve_and_install()=='installed'
    for _path,headers,_body in handler.received:
        assert not {k.lower() for k in headers}&{'cookie','authorization'}


def test_publication_conflict_is_safe_and_local_identity_preserved(bundle,server):
    url,handler=server;handler.code=409;b=bundle
    with pytest.raises(WebsiteLicenceSyncError,match='publication_conflict') as raised:
        publish_website_test_licence(b.db,b.activation,test_mode=True,base_url=url,token='synthetic-token')
    assert 'private-server-text' not in str(raised.value)
    assert stored_test_licence(b.db,b.activation)[0]==b.envelope


def test_operator_ui_exports_original_test_trust_without_resigning(qtbot,bundle,monkeypatch,tmp_path):
    b=bundle
    monkeypatch.setattr(main_window,'fetch_website_activations',lambda **_kw:(b.activation,))
    output=tmp_path/'exported-trust.json'
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *_args:(str(output),'JSON'))
    window=LicenceManagerWindow(test_mode=True,database=b.db,authority=_TestSigner())
    qtbot.addWidget(window);window.refresh_website_activations();window.website_activations_table.selectRow(0)
    window.export_test_trust_button.click()
    assert load_test_trust(output)=={b.signer.kid:b.signer.public_key}
    assert stored_test_licence(b.db,b.activation)[0]==b.envelope


def test_ui_installs_and_reopens_active_without_browser(qtbot,bundle):
    b=bundle
    dialog=AccountLicensingDialog(licensing_service=b.service,delivery_factory=lambda:delivery(b))
    qtbot.addWidget(dialog);dialog.check_button.click()
    qtbot.waitUntil(lambda:dialog._worker is None,timeout=3000)
    assert 'Licence status: Active' in dialog.licence_summary.text()
    assert 'TEST LICENSING' in dialog.licence_summary.text()
    assert b.envelope['licence_id'] in dialog.licence_summary.text()
    reopened=AccountLicensingDialog(licensing_service=LicensingService(trusted_public_keys=load_test_trust(b.trust_path),device_identity=b.device,lease_store=b.store,test_mode=True))
    qtbot.addWidget(reopened)
    assert 'Licence status: Active' in reopened.licence_summary.text()
    assert reopened.start_button.isHidden()


def test_ui_pending_and_flagged_never_grant(qtbot,bundle):
    b=bundle
    calls=[]
    dialog=AccountLicensingDialog(licensing_service=b.service,delivery_factory=lambda:calls.append(1) or delivery(b,{'state':'pending'}))
    qtbot.addWidget(dialog);dialog.check_button.click()
    qtbot.waitUntil(lambda:dialog._worker is None,timeout=3000)
    assert 'licence pending' in dialog.status.text()
    assert b.service.lease is None
    dialog._show_result('completed','FLAGGED')
    assert not dialog._check_after_activation and len(calls)==1
    assert 'FLAGGED' in dialog.status.text()
    dialog.check_licence()
    assert len(calls)==1 and not dialog.check_button.isEnabled()


def test_operator_publish_button_keeps_issuance_separate(qtbot,bundle,monkeypatch):
    b=bundle
    monkeypatch.setattr(main_window,'fetch_website_activations',lambda **_kw:(b.activation,))
    calls=[]
    monkeypatch.setattr(main_window,'sync_website_test_licence_metadata',lambda *args,**kw:calls.append('metadata'))
    monkeypatch.setattr(main_window,'publish_website_test_licence',lambda *args,**kw:calls.append('publication') or 'published')
    window=LicenceManagerWindow(test_mode=True,database=b.db,authority=_TestSigner())
    qtbot.addWidget(window);window.refresh_website_activations();window.website_activations_table.selectRow(0)
    window.publish_website_licence_button.click()
    assert calls==['metadata','publication']
    assert stored_test_licence(b.db,b.activation)[0]==b.envelope
    assert b.db.connection.execute('SELECT COUNT(*) FROM website_activation_licences').fetchone()[0]==1


def test_invalid_cache_is_not_overwritten_by_delivery(bundle):
    b=bundle
    b.store.save_lease({'invalid':'preserve for explicit recovery'})
    with pytest.raises(LeaseValidationError,match='different'):
        b.service.install_delivered_lease(b.envelope)
    assert b.store.load_lease()=={'invalid':'preserve for explicit recovery'}
    assert b.service.lease is None


def test_trust_exported_after_desktop_start_loads_on_check_without_restart(bundle,monkeypatch):
    b=bundle
    monkeypatch.setenv('QS_TEST_LICENSING','1')
    b.service._trusted_public_keys={}
    b.service.error_code='test_trust_invalid'
    flow=LicenceDeliveryService(b.service,FakeDelivery(b),b.identity_service,
        trust_loader=lambda:b.service.reload_local_test_trust(b.trust_path))
    assert flow.retrieve_and_install()=='installed'
    assert b.service.diagnostics_summary()['status']=='active'


def test_pending_does_not_need_test_trust_and_production_cannot_reload_test_file(bundle,monkeypatch):
    b=bundle
    b.service._trusted_public_keys={}
    calls=[]
    flow=LicenceDeliveryService(b.service,FakeDelivery(b,{'state':'pending'}),b.identity_service,
        trust_loader=lambda:calls.append('must not load trust for metadata'))
    assert flow.retrieve_and_install()=='pending' and calls==[]
    b.service.test_mode=False
    monkeypatch.setenv('QS_TEST_LICENSING','1')
    with pytest.raises(LeaseValidationError): b.service.reload_local_test_trust(b.trust_path)
    assert not b.service.authorize_feature('workspace:device_builder').allowed


def test_production_service_ignores_test_environment_even_with_cached_test_lease(bundle,monkeypatch):
    from backend.licensing import service as module
    b=bundle;b.service.install_delivered_lease(b.envelope)
    monkeypatch.setenv('QS_TEST_LICENSING','1')
    monkeypatch.setenv('QS_TEST_LICENCE_TRUST_FILE',str(b.trust_path))
    monkeypatch.setattr(module,'LeaseStore',lambda:b.store)
    monkeypatch.setattr(module,'production_secure_store',lambda _paths:b.identity_service.store)
    production=LicensingService.production()
    assert production.lease is None and not production.test_mode
    assert not production.authorize_feature('workspace:device_builder').allowed


def test_authorized_browser_result_automatically_retrieves_and_installs(qtbot,bundle):
    b=bundle
    class Auth:
        def start_activation(self,_facts):
            return {'challenge_id':'a'*64,'device_code':'b'*64,'verification_url':'https://website.example/desktop-auth?challenge='+'a'*64,'expires_in':300,'interval':0.01}
        def poll_activation(self,*args):
            return {'state':'completed','activation':{'activation_request_id':b.activation.activation_request_id,'installation_id':b.device.device_id,'status':'AUTHORIZED'}}
        def cancel_activation(self,*args): pass
    dialog=AccountLicensingDialog(licensing_service=b.service,connector=Auth(),open_browser=lambda _url:True,delivery_factory=lambda:delivery(b))
    qtbot.addWidget(dialog);dialog.start_button.click()
    qtbot.waitUntil(lambda:b.service.lease is not None and dialog._worker is None,timeout=3000)
    assert b.store.load_lease()==b.envelope
    assert 'Licence status: Active' in dialog.licence_summary.text()


def test_local_private_field_never_reaches_publication_transport(bundle,server):
    b=bundle;url,handler=server
    bad={**b.envelope,'private_key':'never-transmit'}
    b.db.connection.execute('UPDATE website_activation_licences SET envelope_json=?',(json.dumps(bad),))
    b.db.connection.commit()
    with pytest.raises(WebsiteLicenceSyncError,match='unsupported fields'):
        publish_website_test_licence(b.db,b.activation,test_mode=True,base_url=url,token='synthetic-token')
    assert handler.received==[]
