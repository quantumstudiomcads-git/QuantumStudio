"""M8 real M5 signer + HTTP clients, restart recovery, explicit public trust."""
from dataclasses import asdict, replace
from http.server import BaseHTTPRequestHandler, HTTPServer
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Thread
from types import SimpleNamespace
import time
import secrets

import pytest

from backend.licensing.canonical import canonical_json
from backend.licensing.device_identity import DeviceIdentityService, InMemorySecureKeyStore
from backend.licensing.local_test_trust import load_test_trust
from backend.licensing.verifier import LeaseVerifier
from operator_tools.licence_manager import beta_worker as module
from operator_tools.licence_manager.beta_worker import BetaLicenceWorker, WorkerConfig, WorkerError, maintain_test_trust
from operator_tools.licence_manager.crypto import DataProtector
from operator_tools.licence_manager.database import Database
from operator_tools.licence_manager.issuance import issue_website_activation_for_testing
from operator_tools.licence_manager.licence_delivery import stored_test_licence
from operator_tools.licence_manager.signing import TestEphemeralAuthority as Signer, ProductionAuthority
from operator_tools.licence_manager.website_sync import WebsiteActivation


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("BETA_ENVIRONMENT", "local")
    identity_service = DeviceIdentityService(InMemorySecureKeyStore())
    identity = identity_service.load_or_create()
    activation = WebsiteActivation("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "12345678-1234-4123-8123-123456789abc",
        identity.device_id, "windows", "x86_64", "0.2.0", "AUTHORIZED", None,
        "2026-10-20T00:00:00Z", "2026-10-20T00:00:00Z", "2026-10-20T00:00:00Z", None, identity.public_key_hash)
    state = SimpleNamespace(activation=activation, metadata=None, envelope=None, failure=None, calls=[])
    class Handler(BaseHTTPRequestHandler):
        def reply(self, code, data):
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())
        def do_GET(self):
            assert self.headers.get("Authorization") == "Bearer synthetic-read"
            self.reply(200, {"schema_version":1, "activations":[asdict(state.activation)]})
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path.startswith("/api/licence/"):
                assert not self.headers.get("Authorization")
                if self.path.endswith("device-challenge"):
                    state.challenge={"schema_version":1,"purpose":"quantum-studio:licence-retrieve:v1",
                        "challenge_id":secrets.token_hex(32),"nonce":secrets.token_hex(32),
                        "activation_request_id":state.activation.activation_request_id,
                        "installation_id":identity.device_id,"device_public_key_hash":identity.public_key_hash,
                        "expires_at":int(time.time())+120}
                    return self.reply(200,{"challenge":state.challenge})
                from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
                from backend.licensing.canonical import b64url_decode
                Ed25519PublicKey.from_public_bytes(identity.public_key).verify(b64url_decode(body['signature']),canonical_json(state.challenge))
                if state.envelope is None: return self.reply(200,{"state":"pending"})
                return self.reply(200,{"state":"available","envelope":state.envelope,
                    "envelope_sha256":hashlib.sha256(canonical_json(state.envelope)).hexdigest()})
            stage = "metadata" if self.path.endswith("/licence") else "publication"
            state.calls.append(stage)
            assert self.headers.get("Authorization") == "Bearer synthetic-" + ("metadata" if stage == "metadata" else "publish")
            if state.failure == stage:
                return self.reply(400, {"error":{"code":"invalid_metadata" if stage == "metadata" else "publication_conflict", "message":"secret-never-echo"}})
            if stage == "metadata":
                result = "already_current" if state.metadata == body else "updated"
                if state.metadata is not None and state.metadata != body:
                    return self.reply(409, {"error":{"code":"licence_metadata_conflict"}})
                state.metadata = body
                state.activation = replace(state.activation, licence_id=body["licence_id"], licence_status="ISSUED",
                    licence_issued_at=body["issued_at"], licence_expires_at=body["expires_at"])
                return self.reply(200, {"schema_version":1,"result":result})
            envelope = body["envelope"]
            if state.envelope is not None and state.envelope != envelope:
                return self.reply(409, {"error":{"code":"publication_conflict"}})
            result = "already_current" if state.envelope == envelope else "published"
            state.envelope = envelope
            self.reply(200, {"schema_version":1,"result":result,"envelope_sha256":hashlib.sha256(canonical_json(envelope)).hexdigest()})
        def log_message(self, *_): pass
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    protector = DataProtector.for_testing(b"W"*32)
    db = Database(tmp_path/"operator", protector)
    config = WorkerConfig(f"http://127.0.0.1:{server.server_port}", "synthetic-read", "synthetic-metadata", "synthetic-publish",
                          db.root, tmp_path/"issuer.json", True)
    signer = Signer()
    b = SimpleNamespace(state=state, db=db, config=config, signer=signer, identity=identity, protector=protector,
                        identity_service=identity_service)
    b.worker = BetaLicenceWorker(db, signer, config)
    yield b
    db.close()
    server.shutdown(); server.server_close(); thread.join(timeout=2)


def count(b):
    return b.db.connection.execute("SELECT COUNT(*) FROM website_activation_licences").fetchone()[0]


def forbid_signing(monkeypatch, signer):
    def forbidden(_): raise AssertionError("MUST NOT SIGN AGAIN")
    monkeypatch.setattr(signer, "sign_test_fixture_only", forbidden)


def test_first_run_and_repeat_are_idempotent_actual_clients_and_signer(setup, monkeypatch):
    b=setup
    assert b.worker.run_once()[0].result == "published"
    original=canonical_json(b.state.envelope)
    forbid_signing(monkeypatch,b.signer)
    assert b.worker.run_once()[0].result == "already_current"
    assert canonical_json(b.state.envelope)==original and count(b)==1
    LeaseVerifier(load_test_trust(b.config.trust_file)).verify(b.state.envelope,b.identity)
    assert b.db.connection.execute("SELECT COUNT(*) FROM signing_keys").fetchone()[0]==1
    events=[json.loads(r[0]) for r in b.db.connection.execute("SELECT details FROM audit_events WHERE event_type='automatic_test_licence'")]
    assert all(any(e['stage']==stage for e in events) for stage in ['eligibility','issuance','trust','metadata','publication'])
    assert all('synthetic-' not in json.dumps(e) for e in events)


@pytest.mark.parametrize('change',[
    {'status':'FLAGGED'}, {'status':'REVOKED'}, {'device_public_key_hash':None},
    {'device_public_key_hash':'b'*64}, {'installation_id':'dev_'+'0'*32},
    {'application_id':'invalid'}, {'app_version':''}, {'authorized_at':None},
    {'flag_reason':'DEVICE_LIMIT'}, {'revoked_at':'2026-10-20T00:00:00Z'},
    {'licence_revoked_at':'2026-10-20T00:00:00Z'},
])
def test_ineligible_does_not_sign(setup, monkeypatch, change):
    b=setup
    activation=replace(b.state.activation,**change)
    # Exercise service validation too, independently of the existing strict fetch parser.
    monkeypatch.setattr(module,'fetch_website_activations',lambda **_: (activation,))
    forbid_signing(monkeypatch,b.signer)
    assert b.worker.run_once()[0].stage=='eligibility'
    assert count(b)==0 and not b.config.trust_file.exists() and b.state.calls==[]


def test_remote_licence_without_local_envelope_requires_recovery(setup,monkeypatch):
    b=setup
    b.state.activation=replace(b.state.activation,licence_id='lic_12345678-1234-4123-8123-123456789abc')
    forbid_signing(monkeypatch,b.signer)
    assert b.worker.run_once()[0].result=='recovery_required'
    assert count(b)==0 and b.state.calls==[]


@pytest.mark.parametrize('stage',['metadata','publication'])
def test_failed_sync_or_publication_retries_original_without_resigning(setup,monkeypatch,stage):
    b=setup
    b.state.failure=stage
    first=b.worker.run_once()[0]
    assert first.stage==stage and first.result=='failed'
    assert 'HTTP 400' in first.message and 'secret-never-echo' not in first.message
    original=stored_test_licence(b.db,b.state.activation)[0]
    assert count(b)==1
    if stage=='metadata': assert b.state.envelope is None and b.state.calls==['metadata']
    else: assert b.state.metadata['licence_id']==original['licence_id']
    forbid_signing(monkeypatch,b.signer)
    b.state.failure=None
    assert b.worker.run_once()[0].result=='published'
    assert b.state.envelope==original and count(b)==1


def test_immutable_conflicting_publication_is_preserved(setup):
    b=setup
    b.state.envelope={'conflicting':'artifact'}
    result=b.worker.run_once()[0]
    assert result.stage=='publication' and 'publication_conflict' in result.message
    assert b.state.envelope=={'conflicting':'artifact'} and count(b)==1


def test_remote_local_licence_id_conflict_never_syncs_or_resigns(setup,monkeypatch):
    b=setup
    issue_website_activation_for_testing(b.db,b.signer,b.state.activation)
    b.state.activation=replace(b.state.activation,licence_id='lic_12345678-1234-4123-8123-123456789abc')
    forbid_signing(monkeypatch,b.signer)
    assert b.worker.run_once()[0].result=='licence_conflict' and b.state.calls==[]


def test_trust_contains_only_actual_public_metadata_and_accepts_identical(setup):
    b=setup
    b.worker.run_once()
    record=json.loads(b.config.trust_file.read_text(encoding='utf-8'))
    assert record==stored_test_licence(b.db,b.state.activation)[1]
    assert set(record)=={'schema_version','domain','algorithm','kid','public_key'}
    assert load_test_trust(b.config.trust_file)=={b.signer.kid:b.signer.public_key}
    before=b.config.trust_file.read_bytes()
    assert maintain_test_trust(b.config.trust_file,record)=='already_current'
    assert b.config.trust_file.read_bytes()==before
    with pytest.raises(WorkerError): maintain_test_trust(b.config.trust_file,dict(record,private_key='NEVER'))
    assert b.config.trust_file.read_bytes()==before


@pytest.mark.parametrize('existing',['invalid','different'])
def test_conflicting_trust_is_preserved_before_first_signature(setup,monkeypatch,existing):
    b=setup
    if existing=='invalid': b.config.trust_file.write_text('invalid',encoding='utf-8')
    else:
        other=Signer()
        from operator_tools.licence_manager.signing import public_key_record
        maintain_test_trust(b.config.trust_file,dict(schema_version=1,domain='test-licence',**public_key_record(other)))
    before=b.config.trust_file.read_bytes()
    forbid_signing(monkeypatch,b.signer)
    result=b.worker.run_once()[0]
    assert result.stage=='trust' and result.result=='failed'
    assert b.config.trust_file.read_bytes()==before and count(b)==0 and b.state.calls==[]


def test_recovered_prior_signer_uses_original_trust_even_with_new_authority(setup,monkeypatch):
    b=setup
    original=issue_website_activation_for_testing(b.db,b.signer,b.state.activation)
    next_signer=Signer()
    forbid_signing(monkeypatch,next_signer)
    worker=BetaLicenceWorker(b.db,next_signer,b.config)
    assert worker.run_once()[0].result=='published'
    assert b.state.envelope==original
    assert load_test_trust(b.config.trust_file)=={b.signer.kid:b.signer.public_key}
    assert worker.run_once()[0].result=='already_current'


def test_actual_process_restart_recovers_original_and_trust(setup):
    b=setup
    assert b.worker.run_once()[0].result=='published'
    original=b.state.envelope.copy()
    trust_before=b.config.trust_file.read_bytes()
    source="""
import sys
from pathlib import Path
from operator_tools.licence_manager.beta_worker import BetaLicenceWorker, WorkerConfig
from operator_tools.licence_manager.database import Database
from operator_tools.licence_manager.crypto import DataProtector
from operator_tools.licence_manager.signing import TestEphemeralAuthority
root,trust,url,generation=sys.argv[1:]
db=Database(Path(root),DataProtector.for_testing(b'W'*32,storage_generation_id=generation))
signer=TestEphemeralAuthority()
def fail(_): raise AssertionError('NO REPLACEMENT SIGNATURE')
signer.sign_test_fixture_only=fail
config=WorkerConfig(url,'synthetic-read','synthetic-metadata','synthetic-publish',Path(root),Path(trust),True)
try:
    result=BetaLicenceWorker(db,signer,config).run_once()[0]
    assert result.result=='already_current',result
    print('restart already_current')
finally: db.close()
"""
    completed=subprocess.run([sys.executable,'-c',source,str(b.db.root),str(b.config.trust_file),b.config.base_url,b.protector.storage_generation_id],
        capture_output=True,text=True,timeout=30,check=True)
    assert 'restart already_current' in completed.stdout
    assert b.state.envelope==original and b.config.trust_file.read_bytes()==trust_before and count(b)==1


def test_fresh_activation_after_restart_cannot_rotate_existing_trust(setup):
    b=setup
    assert b.worker.run_once()[0].result=='published'
    original=b.config.trust_file.read_bytes()
    identity=DeviceIdentityService(InMemorySecureKeyStore()).load_or_create()
    b.state.activation=replace(b.state.activation, activation_request_id='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
        installation_id=identity.device_id,device_public_key_hash=identity.public_key_hash,
        licence_id=None,licence_status=None,licence_issued_at=None,licence_expires_at=None)
    worker=BetaLicenceWorker(b.db,Signer(),b.config)
    result=worker.run_once()[0]
    assert result.stage=='trust' and result.result=='failed'
    assert count(b)==1 and b.config.trust_file.read_bytes()==original


def test_conflicting_active_device_licence_blocks_new_activation(setup):
    b=setup
    issue_website_activation_for_testing(b.db,b.signer,b.state.activation)
    b.state.activation=replace(b.state.activation,activation_request_id='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb')
    assert b.worker.run_once()[0].stage=='reconciliation' and count(b)==1


def test_multiple_distinct_authorized_devices_keep_m4_policy(setup):
    b=setup
    assert b.worker.run_once()[0].result=='published'
    identity=DeviceIdentityService(InMemorySecureKeyStore()).load_or_create()
    b.state.activation=replace(b.state.activation,activation_request_id='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
        installation_id=identity.device_id,device_public_key_hash=identity.public_key_hash,
        licence_id=None,licence_status=None,licence_issued_at=None,licence_expires_at=None)
    b.state.metadata=None; b.state.envelope=None
    assert b.worker.run_once()[0].result=='published' and count(b)==2


@pytest.mark.parametrize('test_mode,environment',[(False,'local'),(True,'production'),(True,''),(True,'staging')])
def test_non_test_configuration_is_refused(setup,monkeypatch,test_mode,environment):
    monkeypatch.setenv('BETA_ENVIRONMENT',environment)
    with pytest.raises(WorkerError): BetaLicenceWorker(setup.db,setup.signer,replace(setup.config,test_mode=test_mode))
    assert count(setup)==0


@pytest.mark.parametrize('field,value',[
    ('read_token',''),('metadata_token',''),('publish_token',''),('publish_token',' bad '),
    ('base_url','https://example.com'),('test_data_root',Path('relative')),('trust_file',Path('relative.json')),
])
def test_all_config_is_checked_before_any_issuance(setup,field,value):
    with pytest.raises(WorkerError): replace(setup.config,**{field:value}).validate()
    assert count(setup)==0


def test_production_authority_is_rejected(setup):
    b=setup
    with pytest.raises(WorkerError): BetaLicenceWorker(b.db,ProductionAuthority(b.db.root/'key',b.db.root/'meta'),b.config)


def test_worker_import_has_no_qt_dependency():
    source="""
import sys,importlib.abc
class BlockQt(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.startswith(('PySide6','PyQt')): raise AssertionError('Qt dependency: '+fullname)
sys.meta_path.insert(0,BlockQt())
import operator_tools.licence_manager.beta_worker
import scripts.run_beta_licence_worker
assert not any(n.startswith(('PySide6','PyQt')) for n in sys.modules)
print('Qt-free worker import passed')
"""
    result=subprocess.run([sys.executable,'-c',source],capture_output=True,text=True,check=True,timeout=20)
    assert 'Qt-free' in result.stdout


def test_second_worker_cannot_race_same_root(setup):
    with module._worker_lock(setup.db.root):
        with pytest.raises(WorkerError,match='Another TEST worker'):
            setup.worker.run_once()
    assert setup.worker.run_once()[0].result=='published'


def test_local_signing_failure_is_audited_without_secret_output(setup,monkeypatch):
    def fail(_): raise RuntimeError('SYNTHETIC PRIVATE MATERIAL')
    monkeypatch.setattr(setup.signer,'sign_test_fixture_only',fail)
    result=setup.worker.run_once()[0]
    assert result.stage=='issuance' and result.result=='failed' and count(setup)==0
    assert 'SYNTHETIC' not in result.message
    row=setup.db.connection.execute("SELECT details FROM audit_events ORDER BY seq DESC LIMIT 1").fetchone()
    assert json.loads(row[0])=={'stage':'issuance','result':'failed'}


def test_worker_to_existing_desktop_delivery_then_offline_cache(setup,tmp_path,monkeypatch):
    from backend.licensing.service import LicensingService
    from backend.licensing.lease_store import LeaseStore
    from backend.runtime.paths import runtime_paths
    from backend.licensing.licence_delivery import LicenceDeliveryService
    from backend.licensing.connectors.licence_delivery import WebsiteLicenceDeliveryConnector
    b=setup
    monkeypatch.setenv('QS_TEST_LICENSING','1')
    paths=runtime_paths(environ={'QUANTUM_STUDIO_DATA_ROOT':str(tmp_path/'desktop')},home=tmp_path)
    service=LicensingService(trusted_public_keys={},device_identity=b.identity,lease_store=LeaseStore(paths),test_mode=True)
    connector=WebsiteLicenceDeliveryConnector(b.config.base_url,allow_local_http=True)
    delivery=LicenceDeliveryService(service,connector,b.identity_service,
        trust_loader=lambda:service.reload_local_test_trust(b.config.trust_file))
    assert delivery.retrieve_and_install(b.state.activation.activation_request_id)=='pending'
    assert service.lease is None and not b.config.trust_file.exists()
    assert b.worker.run_once()[0].result=='published'
    assert delivery.retrieve_and_install(b.state.activation.activation_request_id)=='installed'
    assert service.diagnostics_summary()['status']=='active'
    original=service.lease.licence_id
    # New service/store, with no connector or worker: cached signed licence only.
    restarted=LicensingService(trusted_public_keys=load_test_trust(b.config.trust_file),
        device_identity=DeviceIdentityService(b.identity_service.store).load_or_create(),lease_store=LeaseStore(paths),test_mode=True)
    assert restarted.lease.licence_id==original
    assert restarted.device_identity.device_id==b.identity.device_id
    assert restarted.diagnostics_summary()['status']=='active'
    assert restarted.authorize_feature('workspace:device_builder').allowed


def test_trust_publication_race_never_overwrites_winner(setup,monkeypatch):
    b=setup
    issue_website_activation_for_testing(b.db,b.signer,b.state.activation)
    trust=stored_test_licence(b.db,b.state.activation)[1]
    real_link=module.os.link
    def race(source,target):
        Path(target).write_text('conflicting winner',encoding='utf-8')
        return real_link(source,target)
    monkeypatch.setattr(module.os,'link',race)
    with pytest.raises(WorkerError,match='conflict'): maintain_test_trust(b.config.trust_file,trust)
    assert b.config.trust_file.read_text(encoding='utf-8')=='conflicting winner'
    assert not list(b.config.trust_file.parent.glob('.test-trust-*.tmp'))


def test_missing_trust_after_signer_restart_does_not_authorize_rotation(setup):
    b=setup
    issue_website_activation_for_testing(b.db,b.signer,b.state.activation)
    identity=DeviceIdentityService(InMemorySecureKeyStore()).load_or_create()
    b.state.activation=replace(b.state.activation,activation_request_id='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
        installation_id=identity.device_id,device_public_key_hash=identity.public_key_hash)
    result=BetaLicenceWorker(b.db,Signer(),b.config).run_once()[0]
    assert result.stage=='trust' and result.result=='failed' and count(b)==1
    assert not b.config.trust_file.exists()


def test_duplicate_remote_device_activation_blocks_issuance(setup,monkeypatch):
    b=setup
    other=replace(b.state.activation,activation_request_id='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb')
    monkeypatch.setattr(module,'fetch_website_activations',lambda **_: (b.state.activation,other))
    results=b.worker.run_once()
    assert all(r.result=='conflicting_device_activation' for r in results)
    assert count(b)==0


def test_cli_requires_all_three_explicit_credentials_before_storage(setup,monkeypatch,capsys):
    b=setup
    monkeypatch.setenv('QS_OPERATOR_WEBSITE_URL',b.config.base_url)
    monkeypatch.setenv('QS_OPERATOR_SYNC_TOKEN','synthetic-read')
    monkeypatch.setenv('QS_OPERATOR_LICENCE_SYNC_TOKEN','synthetic-metadata')
    monkeypatch.delenv('QS_OPERATOR_LICENCE_PUBLISH_TOKEN',raising=False)
    def forbidden(_): raise AssertionError('Storage must not open')
    monkeypatch.setattr(module,'bootstrap_storage',forbidden)
    assert module.main(['--test-mode','--test-data-root',str(b.db.root),'--trust-file',str(b.config.trust_file)])==2
    output=capsys.readouterr().out
    assert 'QS_OPERATOR_LICENCE_PUBLISH_TOKEN' in output and 'synthetic-' not in output


@pytest.mark.skipif(os.name!='nt',reason='Actual storage bootstrap uses Windows CurrentUser DPAPI')
def test_canonical_cli_with_real_dpapi_storage_restarts_idempotently(setup,tmp_path):
    b=setup
    root=tmp_path/'cli-operator'
    trust=tmp_path/'cli-issuer.json'
    environment=dict(os.environ,BETA_ENVIRONMENT='local',QS_OPERATOR_WEBSITE_URL=b.config.base_url,
        QS_OPERATOR_SYNC_TOKEN='synthetic-read',QS_OPERATOR_LICENCE_SYNC_TOKEN='synthetic-metadata',
        QS_OPERATOR_LICENCE_PUBLISH_TOKEN='synthetic-publish')
    command=[sys.executable,'scripts/run_beta_licence_worker.py','--test-mode',
        '--test-data-root',str(root),'--trust-file',str(trust)]
    first=subprocess.run(command,env=environment,capture_output=True,text=True,timeout=30,check=True)
    assert 'complete published' in first.stdout
    envelope=b.state.envelope.copy()
    trust_before=trust.read_bytes()
    second=subprocess.run(command,env=environment,capture_output=True,text=True,timeout=30,check=True)
    assert 'complete already_current' in second.stdout
    assert b.state.envelope==envelope and trust.read_bytes()==trust_before
    assert 'synthetic-' not in first.stdout+second.stdout+first.stderr+second.stderr
    import sqlite3
    with sqlite3.connect(root/'operator.sqlite3') as connection:
        assert connection.execute('SELECT COUNT(*) FROM website_activation_licences').fetchone()[0]==1
        assert json.loads(connection.execute('SELECT envelope_json FROM website_activation_licences').fetchone()[0])==envelope
    assert (root/'data-key.dpapi').is_file()
