"""Deployed public delivery and public trust only; known synthetic seeds, no real network."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import time

import pytest
from backend.runtime.paths import runtime_paths
from backend.licensing.configuration import desktop_configuration, ConfigurationError
from backend.licensing.canonical import canonical_json
from backend.licensing.device_identity import DeviceIdentityService, InMemorySecureKeyStore
from backend.licensing.lease_store import LeaseStore
from backend.licensing.service import LicensingService
from backend.licensing.licence_delivery import LicenceDeliveryService
from backend.licensing.connectors.licence_delivery import WebsiteLicenceDeliveryConnector, LicenceDeliveryError
from backend.licensing.connectors.device_status import WebsiteDeviceStatusConnector, DeviceStatusNetworkError
from backend.licensing.verifier import LeaseValidationError
from operator_tools.licence_manager.signing_runtime import RuntimeEd25519Signer
from tests.licensing.test_production_signing import configuration
from tests.licensing.test_licence_delivery import FakeDelivery
from tests.helpers.licensing import StatusFixture

APP='12345678-1234-4123-8123-123456789abc'
AID='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'

@pytest.fixture(params=['staging','production'])
def deployed(tmp_path,request):
    mode=request.param
    values=configuration(mode,seed=bytes(range(32)) if mode=='staging' else bytes(reversed(range(32))),issuer='lic-'+mode+'-unit')
    runtime_signer=RuntimeEd25519Signer(values,bind_environment=True)
    config_values={'BETA_ENVIRONMENT':mode,'QS_WEBSITE_URL':'https://'+mode+'.unit-fixture.org',
        'QS_LICENCE_TRUST':json.dumps({'schema_version':1,'environment':mode,'domain':'licence','algorithm':'Ed25519',
            'keys':{runtime_signer.kid:values['QS_LICENCE_SIGNING_PUBLIC_KEY']}})}
    config=desktop_configuration(config_values)
    key_store=InMemorySecureKeyStore();key_store.save_private_key(b'D'*32)
    identity=DeviceIdentityService(key_store);device=identity.load_or_create();now=int(time.time())
    payload={'schema_version':1,'licence_id':'lic_bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb','account_id':'sub_'+APP,
        'subject_type':'beta_applicant','subject_id':'sub_'+APP,'approved_application_ref':APP,'product':'Quantum Studio','channel':'beta','plan_id':'pro',
        'device_id':device.device_id,'device_public_key_hash':device.public_key_hash,'issued_at':now,'not_before':now,'expires_at':now+86400,
        'offline_until':now+86400,'entitlement_version':1,'feature_entitlements':['workspace:device_builder'],'calculation_entitlements':[],
        'registered_device_limit':1,'concurrent_session_limit':1,'offline_device_limit':1,'nonce':'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
        'policy_profile':'PROFESSOR_BETA','issuer_label':'Quantum Studio Licence Manager'}
    envelope=runtime_signer.sign_licence(payload)
    store=LeaseStore(runtime_paths(environ={'QUANTUM_STUDIO_DATA_ROOT':str(tmp_path)},home=tmp_path))
    remote=StatusFixture(envelope,now,identity)
    service=LicensingService(trusted_public_keys=config.trusted_public_keys,device_identity=device,lease_store=store,
        now=lambda:now,deployment_config=config,status_connector=remote,identity_service=identity)
    return SimpleNamespace(mode=mode,values=config_values,config=config,signer=runtime_signer,payload=payload,envelope=envelope,
        identity_service=identity,device=device,store=store,service=service,remote=remote,now=now,
        activation=SimpleNamespace(activation_request_id=AID))

def delivery(b,envelope=None):
    result=None if envelope is None else {'state':'available','envelope':envelope,'envelope_sha256':hashlib.sha256(canonical_json(envelope)).hexdigest()}
    return LicenceDeliveryService(b.service,FakeDelivery(b,result),b.identity_service)

def restart(b,connector=None):
    return LicensingService(trusted_public_keys=b.config.trusted_public_keys,device_identity=b.device,lease_store=b.store,
        now=lambda:b.now,deployment_config=b.config,status_connector=connector or b.remote,identity_service=b.identity_service)

def test_published_runtime_envelope_installs_verifies_and_is_idempotent(deployed):
    b=deployed
    assert delivery(b).retrieve_and_install(AID)=='installed'
    assert b.store.load_lease()==b.envelope
    assert b.service.diagnostics_summary()['status']=='active'
    before=b.store.lease_path.read_bytes()
    assert delivery(b).retrieve_and_install(AID)=='installed'
    assert b.store.lease_path.read_bytes()==before
    assert b.service.can_start_protected_work().allowed
    assert b.service.authorize_feature('workspace:device_builder').allowed

@pytest.mark.parametrize('case',['missing','environment','test-issuer','test-switch','malformed'])
def test_deployed_trust_cannot_fall_back_to_local(deployed,case):
    values=deepcopy(deployed.values)
    if case=='missing':values.pop('QS_LICENCE_TRUST')
    if case=='environment':
        trust=json.loads(values['QS_LICENCE_TRUST']);trust['environment']='production' if deployed.mode=='staging' else 'staging';values['QS_LICENCE_TRUST']=json.dumps(trust)
    if case=='test-issuer':
        trust=json.loads(values['QS_LICENCE_TRUST']);trust['keys']={'test-lic-fixture':next(iter(trust['keys'].values()))};values['QS_LICENCE_TRUST']=json.dumps(trust)
    if case=='test-switch':values['QS_TEST_LICENSING']='1'
    if case=='malformed':values['QS_LICENCE_TRUST']='{bad'
    with pytest.raises(ConfigurationError):desktop_configuration(values)

@pytest.mark.parametrize('case',['device','issuer','signature','malformed','expired','not_before','account','application','limit'])
def test_invalid_published_envelope_cannot_install_or_grant(deployed,case):
    b=deployed;p=dict(b.payload)
    if case=='device':p['device_id']='dev_'+'f'*32
    if case=='expired':p.update(issued_at=b.now-100,not_before=b.now-100,expires_at=b.now-1,offline_until=b.now-1)
    if case=='not_before':p['not_before']=b.now+60
    if case=='account':p['account_id']='sub_another_application'
    if case=='application':p['approved_application_ref']='ffffffff-ffff-4fff-8fff-ffffffffffff'
    if case=='limit':p['concurrent_session_limit']=2
    e=b.signer.sign_licence(p)
    if case=='issuer':e['kid']='lic-untrusted'
    if case=='signature':e['signature']='a'*86
    if case=='malformed':del e['device_public_key_hash']
    with pytest.raises(LeaseValidationError):delivery(b,e).retrieve_and_install(AID)
    assert b.store.load_lease() is None
    assert not b.service.can_start_protected_work().allowed

def test_status_outage_requires_online_validation_after_install_and_restart(deployed):
    b=deployed;b.remote.failure=DeviceStatusNetworkError('synthetic unreachable')
    assert delivery(b).retrieve_and_install(AID)=='installed'
    assert b.service.diagnostics_summary()['status']=='online_validation_required'
    assert not b.service.can_start_protected_work().allowed
    service=restart(b)
    assert service.lease is not None and not service.can_start_protected_work().allowed
    assert service.diagnostics_summary()['status']=='online_validation_required'

def test_cached_licence_never_bypasses_revocation_or_replacement(deployed):
    b=deployed;delivery(b).retrieve_and_install(AID)
    b.remote.state='REVOKED';b.remote.revision+=1
    assert not b.service.can_start_protected_work().allowed
    assert b.service.diagnostics_summary()['status']=='revoked'
    b.remote.failure=DeviceStatusNetworkError('offline')
    service=restart(b)
    assert service.diagnostics_summary()['status']=='revoked'
    assert not service.can_start_protected_work().allowed
    assert service.device_identity==b.device and b.store.load_lease()==b.envelope

def test_online_server_expiry_and_tampered_cache_deny_protected_work(deployed):
    b=deployed;delivery(b).retrieve_and_install(AID)
    b.remote.now=b.envelope['expires_at']
    assert not b.service.can_start_protected_work().allowed
    assert b.service.diagnostics_summary()['status']=='expired'
    changed=dict(b.envelope,account_id='sub_tampered');b.store.save_lease(changed)
    service=restart(b)
    assert service.lease is None and not service.can_start_protected_work().allowed

@pytest.mark.parametrize('cache',['{bad','[]'])
def test_malformed_cache_is_rejected_safely(deployed,cache):
    b=deployed;b.store.root.mkdir(parents=True,exist_ok=True);b.store.lease_path.write_text(cache)
    service=restart(b)
    assert service.lease is None and service.error_code=='licence_cache_invalid'

def test_real_connectors_use_only_cookie_free_public_endpoints(deployed):
    b=deployed;transport=FakeDelivery(b);calls=[]
    class Response:
        status=200
        def __init__(self,value):self.raw=json.dumps(value).encode()
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def read(self,n):return self.raw[:n]
    class Opener:
        def open(self,req,timeout):
            calls.append(req.full_url)
            assert req.full_url.startswith(b.config.api_origin+'/api/licence/')
            assert not any(k.lower() in {'authorization','cookie'} for k in req.headers)
            body=json.loads(req.data)
            if req.full_url.endswith('/device-challenge'):return Response({'challenge':transport.message})
            if req.full_url.endswith('/device-retrieve'):return Response(transport.retrieve_device_licence(body))
            if req.full_url.endswith('/device-status-challenge'):return Response({'challenge':b.remote.challenge(b.device,body['licence_id'],body['envelope_sha256'])})
            if req.full_url.endswith('/device-status'):return Response(b.remote.status(body))
            pytest.fail('Unexpected private or non-public endpoint')
    opener=Opener()
    connector=WebsiteLicenceDeliveryConnector(b.config.api_origin);connector._opener=opener
    status=WebsiteDeviceStatusConnector(b.config.api_origin);status._opener=opener;b.service._online.connector=status
    assert LicenceDeliveryService(b.service,connector,b.identity_service).retrieve_and_install(AID)=='installed'
    assert b.service.can_start_protected_work().allowed
    assert {url.rsplit('/',1)[-1] for url in calls}=={'device-challenge','device-retrieve','device-status-challenge','device-status'}

def test_desktop_licensing_source_contains_no_private_service_or_provider_credentials():
    root=Path(__file__).resolve().parents[2]
    files=list((root/'backend'/'licensing').rglob('*.py'))+[root/'frontend'/'app'/'account_dialog.py']
    forbidden=('QS_LICENCE_SIGNING_KEY','QS_SIGNING_SERVICE_AUTH','QS_SIGNING_SERVICE_CALLER','OPERATOR_SYNC_TOKEN',
        'OPERATOR_LICENCE_PUBLISH_TOKEN','OPERATOR_STATUS_SYNC_TOKEN','OPERATOR_LICENCE_SYNC_TOKEN','OPERATOR_ACTIVATION_REVOKE_TOKEN',
        'RESEND_API_KEY','GOOGLE_CLIENT_SECRET','SIGNING_SERVICE','/v1/licences/issue','/api/operator/')
    for file in files:
        source=file.read_text(encoding='utf-8')
        assert not any(value in source for value in forbidden),str(file.relative_to(root))

@pytest.mark.parametrize('status',[429,500,502,503,504])
def test_temporary_status_http_failure_is_online_required_not_an_offline_grant(deployed,status):
    from urllib.error import HTTPError
    from io import BytesIO
    b=deployed;delivery(b).retrieve_and_install(AID)
    class Unavailable:
        def open(self,req,timeout):raise HTTPError(req.full_url,status,'private diagnostic',{},BytesIO(b'{"error":{"code":"private-diagnostic"}}'))
    connector=WebsiteDeviceStatusConnector(b.config.api_origin);connector._opener=Unavailable();b.service._online.connector=connector
    assert not b.service.can_start_protected_work().allowed
    assert b.service.diagnostics_summary()['status']=='online_validation_required'

def test_delivery_worker_reports_only_safe_user_messages(deployed):
    from PySide6.QtWidgets import QApplication
    from frontend.app.account_dialog import DeliveryWorker
    app=QApplication.instance() or QApplication([])
    class Failing:
        def retrieve_and_install(self,*_,**__):raise LicenceDeliveryError('private-server-diagnostic',code='request_failed',http_status=503)
    worker=DeliveryWorker(Failing());results=[];worker.result.connect(lambda state,text:results.append((state,text)))
    worker.run()
    assert results and 'Online validation required' in results[0][1]
    assert 'private-server-diagnostic' not in results[0][1]

def test_other_environment_key_cannot_validate_even_if_issuer_id_collides(deployed):
    b=deployed;other='production' if b.mode=='staging' else 'staging'
    seed=bytes(range(32)) if other=='staging' else bytes(reversed(range(32)))
    foreign=RuntimeEd25519Signer(configuration(other,seed=seed,issuer=b.signer.kid),bind_environment=True)
    with pytest.raises(LeaseValidationError):delivery(b,foreign.sign_licence(b.payload)).retrieve_and_install(AID)
    assert b.store.load_lease() is None
