"""Adapter contract tests with a real SQLite engine standing in for DO SQL/FFI."""
import asyncio
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import time
from types import ModuleType, SimpleNamespace

import pytest
from backend.licensing.canonical import canonical_json
from backend.licensing.configuration import Environment
from backend.licensing.verifier import LeaseVerifier
from operator_tools.licence_manager.signing_service_auth import AuthenticatedCall, RequestRejected, service_auth_headers
from tests.licensing.test_production_signing import configuration, SEED
from tests.licensing.test_signing_service import AUTH_KEY, CALLER, AID, APP, auth_record
from tests.helpers.licensing import beta_entitlement
from operator_tools.licence_manager.website_sync import WebsiteActivation
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from backend.licensing.verifier import device_identity_from_private_key
from operator_tools.licence_manager.policy import derive_profile

PROJECT = Path(__file__).resolve().parents[2]/'cloudflare'/'signing_worker'


class Value:
    def __init__(self,value): self.value=value
    def to_py(self): return self.value


class Proxy:
    def __init__(self,callback): self.callback=callback
    def __call__(self): return self.callback()
    def destroy(self): pass


class RawCursor:
    def __init__(self,cursor):
        self.columnNames=Value([item[0] for item in cursor.description] if cursor.description else [])
        self.values=[list(row) for row in cursor.fetchall()]
        self.rowsWritten=max(0,cursor.rowcount)
    def raw(self): return self
    def toArray(self): return Value(self.values)


class Storage:
    def __init__(self,path):
        self.db=sqlite3.connect(path,isolation_level=None)
        self.sql=self
    def exec(self,statement,*parameters):
        assert not statement.upper().startswith(('BEGIN','COMMIT','ROLLBACK','SAVEPOINT'))
        return RawCursor(self.db.execute(statement,parameters))
    def transactionSync(self,action):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            action()
            self.db.commit()
        except BaseException:
            self.db.rollback()
            # Emulate the JS/Python exception boundary, not only direct callbacks.
            raise RuntimeError('opaque JS callback failure') from None


class Reader:
    def __init__(self,data): self.data=data; self.done=False
    async def read(self):
        if self.done: return SimpleNamespace(done=True)
        self.done=True
        return SimpleNamespace(done=False,value=Value(self.data))
    async def cancel(self): pass
    def releaseLock(self): pass


class Message:
    def __init__(self,url,method='POST',headers=None,body=b''):
        self.url,self.method,self.headers=url,method,headers or {}
        self.data=body
        self.body=SimpleNamespace(getReader=lambda:Reader(body))


class Response:
    def __init__(self,body,status=200,headers=None):
        self.status,self.headers,self.data=status,headers or {},body
    def json(self): return json.loads(self.data)


@pytest.fixture
def modules(monkeypatch):
    workers=ModuleType('workers')
    class Base:
        def __init__(self,ctx,env): self.ctx,self.env=ctx,env
    workers.WorkerEntrypoint=workers.DurableObject=Base
    workers.Request=Message; workers.Response=Response
    async def no_network(*args,**kwargs): raise AssertionError('Unexpected live fetch')
    workers.fetch=no_network
    monkeypatch.setitem(sys.modules,'workers',workers)
    js=ModuleType('js')
    js.Uint8Array=SimpleNamespace(new=lambda value:SimpleNamespace(buffer=bytes(value),to_py=lambda:memoryview(value)))
    monkeypatch.setitem(sys.modules,'js',js)
    ffi=ModuleType('pyodide.ffi');ffi.create_proxy=Proxy;ffi.to_js=lambda value:value
    monkeypatch.setitem(sys.modules,'pyodide.ffi',ffi)
    def load(name,file):
        spec=importlib.util.spec_from_file_location(name,PROJECT/'src'/file)
        module=importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules,name,module)
        spec.loader.exec_module(module)
        return module
    storage=load('storage','storage.py')
    entry=load('qs_cloudflare_signing_entry','entry.py')
    entry.profile_provider=derive_profile
    return SimpleNamespace(storage=storage,entry=entry)


@pytest.fixture
def bundle(modules,tmp_path):
    entry=modules.entry
    now=int(time.time())
    values=configuration()
    values.update(QS_OPERATOR_WEBSITE_URL='https://website.unit-fixture.org',
        QS_OPERATOR_SYNC_TOKEN='synthetic-read-token',QS_SIGNING_SERVICE_AUTH=auth_record(),
        QS_SIGNING_OBJECT_NAME='quantum-studio-signing-production-v1')
    env=SimpleNamespace(**values)
    storage=Storage(tmp_path/'durable.sqlite3')
    identity=SimpleNamespace(toString=lambda:'fixed-object-id')
    context=SimpleNamespace(storage=storage,id=identity)
    coordinator=entry.SigningCoordinator(context,env)
    class Namespace:
        def idFromName(self,name):
            assert name==env.QS_SIGNING_OBJECT_NAME
            return identity
        def get(self,object_id): return coordinator
    env.SIGNING_COORDINATOR=Namespace()
    worker=entry.Default(None,env)
    device=device_identity_from_private_key(Ed25519PrivateKey.from_private_bytes(b'D'*32))
    stamp='2026-11-07T00:00:00Z'
    activation=WebsiteActivation(AID,APP,device.device_id,'windows','x86_64','0.2.0','AUTHORIZED',None,
        stamp,stamp,stamp,None,device.public_key_hash,account_entitlement=beta_entitlement(starts_at=now-10))
    records=[activation]
    reads=[]
    async def read(settings,token):
        assert settings.environment is Environment(env.BETA_ENVIRONMENT)
        assert token=='synthetic-read-token'
        reads.append(1)
        return tuple(records)
    entry.website_records=read
    b=SimpleNamespace(entry=entry,storage_module=modules.storage,storage=storage,env=env,
        ctx=context,coordinator=coordinator,worker=worker,activation=activation,records=records,
        reads=reads,now=now,sequence=0,device=device)
    yield b
    storage.db.close()


def request(b,*,environment=None,secret=AUTH_KEY,body=None,nonce=None):
    b.sequence+=1
    data=body if body is not None else canonical_json({'schema_version':1,'activation_request_id':AID})
    headers=service_auth_headers(environment=environment or Environment(b.env.BETA_ENVIRONMENT),caller=CALLER,
        secret=secret,timestamp=int(time.time()),nonce=nonce or f'{b.sequence:064x}',body=data)
    return Message('https://private.unit-fixture.org/v1/licences/issue',headers=headers,body=data)


def run(call): return asyncio.run(call)


def test_worker_end_to_end_uses_shared_issuance_and_recovers_original(bundle):
    b=bundle
    first=run(b.worker.fetch(request(b)))
    assert first.status==200 and first.json()['result']=='persisted'
    envelope=first.json()['envelope']
    from operator_tools.licence_manager.signing_runtime import RuntimeEd25519Signer
    signer=RuntimeEd25519Signer(configuration(),bind_environment=True)
    LeaseVerifier({signer.kid:signer.public_key}).verify(envelope,b.device)
    second=run(b.worker.fetch(request(b)))
    assert second.status==200 and second.json()['result']=='already_current'
    assert second.json()['envelope']==envelope
    assert len(b.reads)==4
    assert b.storage.db.execute("SELECT COUNT(*) FROM audit_events WHERE event_type='licence_issuance'").fetchone()[0]==1


def test_nonce_consumption_survives_durable_object_reconstruction(bundle):
    b=bundle
    req=request(b)
    assert run(b.coordinator.fetch(req)).status==200
    reloaded=b.entry.SigningCoordinator(b.ctx,b.env)
    replay=run(reloaded.fetch(req))
    assert replay.status==409 and replay.json()=={'error':{'code':'replay_rejected'}}


@pytest.mark.parametrize('secret',[b'W'*32,b'Z'*32])
def test_invalid_auth_never_reaches_storage_or_source(bundle,secret):
    b=bundle
    result=run(b.worker.fetch(request(b,secret=secret)))
    assert result.status==401 and b.reads==[]
    assert b.storage.db.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]==0


@pytest.mark.parametrize('name',['QS_LICENCE_SIGNING_KEY','QS_SIGNING_SERVICE_AUTH','QS_OPERATOR_SYNC_TOKEN'])
def test_missing_secret_fails_closed(bundle,name):
    setattr(bundle.env,name,'')
    result=run(bundle.worker.fetch(request(bundle)))
    assert result.status==503 and 'envelope' not in result.json()


def test_https_only_and_endpoint_only(bundle):
    b=bundle
    req=request(b);req.url=req.url.replace('https:','http:')
    assert run(b.worker.fetch(req)).status==403
    req=request(b);req.url='https://private.unit-fixture.org/anything-else'
    assert run(b.worker.fetch(req)).status==404


def test_request_cannot_choose_grants_or_device(bundle):
    b=bundle
    result=run(b.coordinator.fetch(request(b,body=canonical_json({'schema_version':1,'activation_request_id':AID,'expires_at':9999999999}))))
    assert result.status==400 and b.reads==[]


def test_private_key_and_service_secrets_not_leaked(bundle,caplog):
    b=bundle
    result=run(b.worker.fetch(request(b)))
    text=result.data+caplog.text
    from backend.licensing.canonical import b64url_encode
    dump=' '.join(b.storage.db.iterdump())
    for secret in (b64url_encode(SEED),b64url_encode(AUTH_KEY),'synthetic-read-token'):
        assert secret not in text and secret not in dump
    assert not caplog.records


def test_durable_environment_binding_rejects_reuse(bundle):
    b=bundle
    sql=b.storage_module.DurableSql(b.storage)
    b.storage_module.DurableJournal(sql,Environment.PRODUCTION,'same-state')
    with pytest.raises(RequestRejected): b.storage_module.DurableJournal(sql,Environment.STAGING,'same-state')


def test_wrong_request_environment_and_object_name_rejected(bundle):
    b=bundle
    assert run(b.worker.fetch(request(b,environment=Environment.STAGING))).status==401
    b.env.QS_SIGNING_OBJECT_NAME='caller-selected-shard'
    assert run(b.worker.fetch(request(b))).status==503


def test_coordinator_rejects_noncanonical_object_id(bundle):
    b=bundle
    b.coordinator.ctx=SimpleNamespace(storage=b.storage,id=SimpleNamespace(toString=lambda:'different-object'))
    assert run(b.coordinator.fetch(request(b))).status==503


def test_durable_clock_high_water_prevents_rollback_replay(bundle):
    b=bundle
    sql=b.storage_module.DurableSql(b.storage)
    journal=b.storage_module.DurableJournal(sql,Environment.PRODUCTION,'clock')
    journal.consume(AuthenticatedCall(CALLER,200,'a'*64),200)
    journal.consume(AuthenticatedCall(CALLER,400,'b'*64),400)
    with pytest.raises(RequestRejected) as error: journal.consume(AuthenticatedCall(CALLER,200,'a'*64),200)
    assert error.value.status==503


def test_durable_lease_serializes_and_fences_expired_owner(bundle):
    b=bundle
    sql=b.storage_module.DurableSql(b.storage)
    journal=b.storage_module.DurableJournal(sql,Environment.PRODUCTION,'lease')
    first=journal.acquire(100)
    # A reconstructed object sees the same busy durable lease, without a Python lock.
    reloaded=b.storage_module.DurableJournal(sql,Environment.PRODUCTION,'lease')
    with pytest.raises(RequestRejected) as busy: reloaded.acquire(101)
    assert busy.value.code=='issuance_busy'
    second=reloaded.acquire(161)
    assert second.fence==first.fence+1
    with pytest.raises(RequestRejected): journal.assert_owner(first,162)
    journal.release(first)
    reloaded.assert_owner(second,162)  # Stale release cannot clear its successor.


def test_concurrent_network_await_cannot_interleave_issuance(bundle):
    b=bundle
    async def check():
        entered=asyncio.Event();release=asyncio.Event()
        original=b.entry.website_records
        async def blocked(settings,token):
            entered.set()
            await release.wait()
            return await original(settings,token)
        b.entry.website_records=blocked
        one=asyncio.create_task(b.coordinator.fetch(request(b)))
        await entered.wait()
        two=await b.coordinator.fetch(request(b))
        assert two.status==409 and two.json()['error']['code']=='issuance_busy'
        release.set()
        assert (await one).status==200
    run(check())


def test_lost_lease_during_fetch_cannot_persist_or_expose_envelope(bundle):
    b=bundle
    original=b.entry.website_records
    async def lose(settings,token):
        facts=await original(settings,token)
        b.storage.db.execute('UPDATE issuance_lease SET expires_at=0')
        return facts
    b.entry.website_records=lose
    result=run(b.coordinator.fetch(request(b)))
    assert result.status==409 and 'envelope' not in result.json()
    assert b.storage.db.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='website_activation_licences'").fetchone()[0]==0


def test_staging_and_production_use_separate_secret_profiles_and_names(bundle):
    b=bundle
    values=configuration('staging')
    for name,value in values.items(): setattr(b.env,name,value)
    b.env.QS_SIGNING_SERVICE_AUTH=auth_record('staging')
    b.env.QS_SIGNING_OBJECT_NAME='quantum-studio-signing-staging-v1'
    assert run(b.worker.fetch(request(b))).status==200
    assert run(b.worker.fetch(request(b,environment=Environment.PRODUCTION))).status==401


def test_frozen_grants_and_bundle_sources_match_canonical_policy():
    from scripts.build_cloudflare_signing import prepare,SHARED
    target=prepare()
    manifest=json.loads((target/'source_manifest.json').read_text())
    from operator_tools.licence_manager.models import Profile
    grants=derive_profile(Profile.PROFESSOR_BETA)
    assert manifest['profile']['features']==list(grants.features)
    assert manifest['profile']['calculations']==list(grants.calculations)
    assert all((target/name).read_bytes()==(PROJECT.parents[1]/name).read_bytes() for name in SHARED)
    assert not (target/'operator_tools/licence_manager/signing.py').exists()
    assert not (target/'operator_tools/licence_manager/database.py').exists()



def test_durable_transaction_rolls_back_when_lease_expires_during_write(bundle):
    b=bundle
    sql=b.storage_module.DurableSql(b.storage)
    journal=b.storage_module.DurableJournal(sql,Environment.PRODUCTION,'rollback')
    lease=journal.acquire(100)
    clock=[100]
    database=b.storage_module.DurableIssuanceDatabase(sql,journal,lease,lambda:clock[0],'rollback')
    def write(connection):
        connection.execute("INSERT INTO storage_metadata VALUES('must-rollback','public-value')")
        clock[0]=161
    with pytest.raises(RequestRejected): database.run_transaction(write)
    assert sql.execute("SELECT 1 FROM storage_metadata WHERE name='must-rollback'").fetchone() is None


def test_post_signing_outage_withholds_envelope_and_recovers_original(bundle):
    b=bundle
    original=b.entry.website_records
    calls=[0]
    async def outage(settings,token):
        calls[0]+=1
        if calls[0]==2: raise RequestRejected(503,'source_unavailable')
        return await original(settings,token)
    b.entry.website_records=outage
    first=run(b.worker.fetch(request(b)))
    assert first.status==503 and 'envelope' not in first.json()
    stored=b.storage.db.execute('SELECT envelope_json FROM website_activation_licences').fetchone()[0]
    b.entry.website_records=original
    retried=run(b.worker.fetch(request(b)))
    assert retried.status==200 and retried.json()['result']=='already_current'
    assert retried.json()['envelope']==json.loads(stored)


def test_worker_configuration_is_private_and_secret_free():
    import tomllib
    config=tomllib.loads((PROJECT/'wrangler.toml').read_text())
    assert not config['workers_dev'] and not config['preview_urls'] and config['routes']==[]
    assert config['migrations'][0]['new_sqlite_classes']==['SigningCoordinator']
    secret_names={'QS_LICENCE_SIGNING_KEY','QS_SIGNING_SERVICE_AUTH','QS_OPERATOR_SYNC_TOKEN'}
    for mode in ('staging','production'):
        profile=config['env'][mode]
        assert profile['vars']['BETA_ENVIRONMENT']==mode
        assert profile['vars']['QS_SIGNING_OBJECT_NAME']=='quantum-studio-signing-'+mode+'-v1'
        assert not secret_names.intersection(profile['vars'])
        assert not profile['workers_dev'] and not profile['preview_urls'] and profile['routes']==[]


def test_build_command_cannot_deploy(monkeypatch):
    from scripts import build_cloudflare_signing as build
    commands=[]
    monkeypatch.setitem(sys.modules,'uv',SimpleNamespace(find_uv_bin=lambda:'uv'))
    monkeypatch.setattr(build,'prepare',lambda:None)
    monkeypatch.setattr(build.subprocess,'run',lambda command,**kwargs:commands.append(command) or SimpleNamespace(returncode=0))
    assert build.main(['--environment','production'])==0
    assert 'deploy' in commands[0] and '--dry-run' in commands[0]



def test_freshness_is_checked_after_body_stream_read(bundle,monkeypatch):
    b=bundle
    clock=[time.time()]
    monkeypatch.setattr(b.entry.time,'time',lambda:clock[0])
    req=request(b)
    class SlowReader(Reader):
        async def read(self):
            if not self.done: clock[0]+=121
            return await super().read()
    req.body=SimpleNamespace(getReader=lambda:SlowReader(req.data))
    result=run(b.worker.fetch(req))
    assert result.status==401 and result.json()['error']['code']=='stale_request'
    assert b.reads==[]


@pytest.mark.parametrize('mode',[Environment.STAGING,Environment.PRODUCTION])
def test_website_records_workers_compatible_fetch_preserves_auth(modules,monkeypatch,mode):
    entry=modules.entry
    calls=[]
    settings=entry.Settings(mode,'https://website.unit-fixture.org','unused')
    remote=Message(settings.origin,body=b'{"schema_version":1,"activations":[{"fixture":"activation"}]}')
    remote.status=200
    async def result(): return remote
    def workers_fetch(url,**kwargs):
        if kwargs.get('redirect')=='error':raise TypeError('Workers redirect mode unsupported')
        calls.append((url,kwargs));return result()
    monkeypatch.setattr(entry,'fetch',workers_fetch)
    parsed=[]
    def parse(value):parsed.append(value);return 'parsed-activation'
    monkeypatch.setattr(entry,'_parse_website_activation',parse)
    assert run(entry.website_records(settings,'synthetic-operator-secret'))==('parsed-activation',)
    assert parsed==[{'fixture':'activation'}]
    assert calls==[(settings.origin+'/api/operator/activations',{'headers':{'Authorization':'Bearer synthetic-operator-secret','Accept':'application/json'},'redirect':'manual'})]


@pytest.mark.parametrize('status',[300,301,302,303,304,305,306,307,308,399,401,403,404,409,500,503])
def test_website_records_rejects_status_before_reading_headers_or_body(modules,monkeypatch,status,capsys):
    entry=modules.entry
    reads=[]
    class Remote:
        @property
        def body(self):
            reads.append('body')
            raise AssertionError('Body must not be read')
        @property
        def headers(self):
            reads.append('headers')
            raise AssertionError('Location must not be read')
    remote=Remote();remote.status=status
    calls=[]
    async def fetch(url,**kwargs):
        calls.append((url,kwargs));assert kwargs['redirect']=='manual';return remote
    monkeypatch.setattr(entry,'fetch',fetch)
    with pytest.raises(RequestRejected) as error:
        run(entry.website_records(SimpleNamespace(origin='https://website.unit-fixture.org',environment=Environment.PRODUCTION),'synthetic-operator-secret'))
    assert error.value.status==503 and error.value.code=='source_unavailable'
    assert len(calls)==1
    assert reads==[]
    assert 'synthetic-operator-secret' not in str(error.value)
    captured=capsys.readouterr()
    assert captured.err==''
    assert captured.out.strip()=='qs-private-signer-phase '+json.dumps({'environment':'production','phase':'website_records_failed','status':status},separators=(',',':'))


@pytest.mark.parametrize('raw',[b'{bad',b'[]',b'{"schema_version":2,"activations":[]}',b'{"schema_version":1,"activations":[{}]}',b'x'*(2*1024*1024+1)],ids=['invalid-json','array-root','wrong-version','invalid-activation','oversized'])
def test_website_records_rejects_malformed_or_oversized_response(modules,monkeypatch,raw):
    entry=modules.entry
    remote=Message('https://website.unit-fixture.org',body=raw);remote.status=200
    async def fetch(*args,**kwargs):return remote
    monkeypatch.setattr(entry,'fetch',fetch)
    with pytest.raises(RequestRejected) as error:
        run(entry.website_records(SimpleNamespace(origin='https://website.unit-fixture.org',environment=Environment.PRODUCTION),'synthetic-token'))
    assert (error.value.status,error.value.code)==(503,'source_unavailable')


@pytest.mark.parametrize('timeout_stage',[1,2])
def test_website_records_both_timeouts_stay_ten_seconds(modules,monkeypatch,timeout_stage):
    entry=modules.entry;waits=[]
    remote=Message('https://website.unit-fixture.org',body=b'{"schema_version":1,"activations":[]}');remote.status=200
    async def fetch(*args,**kwargs):return remote
    async def wait_for(awaitable,*,timeout):
        waits.append(timeout)
        if len(waits)==timeout_stage:
            awaitable.close()
            raise asyncio.TimeoutError('sensitive-diagnostic')
        return await awaitable
    monkeypatch.setattr(entry,'fetch',fetch)
    monkeypatch.setattr(entry.asyncio,'wait_for',wait_for)
    with pytest.raises(RequestRejected) as error:
        run(entry.website_records(SimpleNamespace(origin='https://website.unit-fixture.org',environment=Environment.PRODUCTION),'synthetic-token'))
    assert (error.value.status,error.value.code)==(503,'source_unavailable')
    assert waits==[10]*timeout_stage
    assert 'sensitive-diagnostic' not in str(error.value)


PHASES=[
    'default_config_valid','default_authenticated','durable_object_dispatch_started',
    'coordinator_config_valid','coordinator_authenticated','journal_initialized','request_consumed','lease_acquired','signer_initialized',
    'website_records_started','website_records_succeeded','activation_validation_succeeded','persist_activation_started','persist_activation_succeeded',
    'second_website_records_started','second_website_records_succeeded','current_activation_validation_succeeded','completed_response_created','coordinator_completed',
    'durable_object_dispatch_completed',
]


def safe_phase_records(capsys,b):
    output=capsys.readouterr()
    assert output.err==''
    records=[]
    for line in output.out.splitlines():
        assert line.startswith('qs-private-signer-phase ')
        record=json.loads(line.removeprefix('qs-private-signer-phase '))
        assert set(record) in ({'environment','phase'},{'environment','phase','status'})
        assert record['environment'] in ('production','staging','unknown')
        if 'status' in record:assert type(record['status']) is int
        records.append(record)
    from backend.licensing.canonical import b64url_encode
    for value in [b.env.QS_OPERATOR_SYNC_TOKEN,b.env.QS_LICENCE_SIGNING_KEY,b.env.QS_LICENCE_SIGNING_PUBLIC_KEY,
                  b64url_encode(AUTH_KEY),b64url_encode(SEED),AID,APP,b.device.device_id,b.device.public_key_hash,
                  'sensitive-diagnostic','Authorization',b.env.QS_SIGNING_OBJECT_NAME,'fixed-object-id']:
        assert value not in output.out
    return records


def test_private_signer_success_phase_sequence_is_safe(bundle,capsys):
    b=bundle
    result=run(b.worker.fetch(request(b)))
    assert result.status==200
    records=safe_phase_records(capsys,b)
    assert [r['phase'] for r in records]==PHASES
    assert result.json()['envelope']['licence_id'] not in json.dumps(records)


@pytest.mark.parametrize('stage',['source','activation','persistence','second-source'])
def test_private_signer_failure_phases_preserve_responses(bundle,monkeypatch,capsys,stage):
    b=bundle
    from operator_tools.licence_manager.signing_service import PrivateSigningService
    if stage in ('source','second-source'):
        original=b.entry.website_records
        calls=[]
        async def read(settings,token):
            calls.append(1)
            if len(calls)==(1 if stage=='source' else 2):raise RequestRejected(503,'source_unavailable')
            return await original(settings,token)
        monkeypatch.setattr(b.entry,'website_records',read)
    elif stage=='activation':
        def reject(*args):raise RequestRejected(409,'activation_unavailable')
        monkeypatch.setattr(PrivateSigningService,'validate_activations',reject)
    else:
        def reject(*args):raise RuntimeError('sensitive-diagnostic '+b.env.QS_OPERATOR_SYNC_TOKEN)
        monkeypatch.setattr(PrivateSigningService,'persist_activation',reject)
    result=run(b.worker.fetch(request(b)))
    assert result.status==(409 if stage=='activation' else 503)
    assert result.json()=={'error':{'code':'activation_unavailable' if stage=='activation' else 'service_unavailable' if stage=='persistence' else 'source_unavailable'}}
    phases=[r['phase'] for r in safe_phase_records(capsys,b)]
    assert phases[-2:]==['coordinator_failure','durable_object_dispatch_completed']
    expected={'source':'website_records_failed','second-source':'second_website_records_failed','activation':'website_records_succeeded','persistence':'persist_activation_started'}[stage]
    assert phases[-3]==expected
    assert 'coordinator_completed' not in phases


def test_default_failure_does_not_print_invalid_environment_or_exception(modules,capsys):
    worker=modules.entry.Default(None,SimpleNamespace(BETA_ENVIRONMENT='sensitive-diagnostic'))
    result=run(worker.fetch(Message('https://private.unit-fixture.org')))
    assert result.status==503
    output=capsys.readouterr()
    assert output.out.strip()=='qs-private-signer-phase {"environment":"unknown","phase":"default_failure"}'
    assert output.err==''
