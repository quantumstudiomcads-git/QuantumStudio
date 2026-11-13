"""Private Python Worker and SQLite-backed Durable Object. No public website routes."""
import asyncio
from dataclasses import dataclass
import json
from pathlib import Path
import time
from types import SimpleNamespace
from urllib.parse import urlsplit

from workers import WorkerEntrypoint, DurableObject, Request, Response, fetch
from backend.licensing.canonical import canonical_json
from backend.licensing.configuration import Environment, validate_origin
from operator_tools.licence_manager.signing_service_auth import (
    HmacServiceAuthenticator, RequestRejected, ISSUE_PATH, FRESHNESS_SECONDS,
)
from operator_tools.licence_manager.website_sync import _parse_website_activation, MAX_ACTIVATION_RESPONSE_BYTES, MAX_WEBSITE_ACTIVATIONS
from storage import DurableSql, DurableJournal, DurableIssuanceDatabase


def phase(environment, name, status=None):
    """Temporary fixed-label diagnostics; never serialize runtime objects/errors."""
    record = {'environment': environment if environment in ('staging','production') else 'unknown', 'phase': name}
    if type(status) is int and 100 <= status <= 599:
        record['status'] = status
    print('qs-private-signer-phase', json.dumps(record, separators=(',', ':')))


@dataclass(frozen=True)
class Settings:
    environment: Environment
    origin: str
    object_name: str


def configure(env):
    values = {name: getattr(env,name,'') for name in ('BETA_ENVIRONMENT','QS_OPERATOR_WEBSITE_URL',
        'QS_LICENCE_SIGNING_ISSUER_ID','QS_LICENCE_SIGNING_PUBLIC_KEY','QS_LICENCE_SIGNING_KEY',
        'QS_SIGNING_SERVICE_AUTH','QS_OPERATOR_SYNC_TOKEN','QS_SIGNING_OBJECT_NAME',
        'QS_TEST_LICENSING','QS_DESKTOP_AUTH_ALLOW_LOCAL_HTTP','BETA_TURNSTILE_TEST_MODE',
        'AUTH_EMAIL_TEST_MODE','CLOUDFLARE_LOCAL','QS_TEST_LICENCE_TRUST_FILE')}
    mode = values['BETA_ENVIRONMENT']
    if mode not in ('staging','production'): raise ValueError
    environment = Environment(mode)
    origin = validate_origin(values['QS_OPERATOR_WEBSITE_URL'],environment)
    name = values['QS_SIGNING_OBJECT_NAME']
    if name != 'quantum-studio-signing-'+mode+'-v1': raise ValueError
    if any(not isinstance(values[key],str) or not values[key] for key in (
        'QS_LICENCE_SIGNING_KEY','QS_LICENCE_SIGNING_ISSUER_ID','QS_LICENCE_SIGNING_PUBLIC_KEY',
        'QS_SIGNING_SERVICE_AUTH','QS_OPERATOR_SYNC_TOKEN')): raise ValueError
    from backend.licensing.configuration import validate_switches
    validate_switches(values,environment)
    auth = HmacServiceAuthenticator(environment,values['QS_SIGNING_SERVICE_AUTH'])
    return Settings(environment,origin,name),auth,values


async def read_limited(message, limit):
    if message.body is None: return b''
    reader = message.body.getReader()
    data = bytearray()
    try:
        while True:
            item = await reader.read()
            if item.done: break
            chunk = bytes(item.value.to_py())
            if len(data)+len(chunk)>limit:
                await reader.cancel()
                raise RequestRejected(413,'request_too_large')
            data.extend(chunk)
    finally: reader.releaseLock()
    return bytes(data)


def response(status, body):
    return Response(canonical_json(body).decode(),status=status,
        headers={'Content-Type':'application/json','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})


def failure(error):
    if isinstance(error,RequestRejected): return response(error.status,{'error':{'code':error.code}})
    return response(503,{'error':{'code':'service_unavailable'}})


async def authenticated_request(request, auth):
    url = urlsplit(request.url)
    if url.scheme != 'https': raise RequestRejected(403,'https_required')
    if url.path != ISSUE_PATH or url.query or url.fragment: raise RequestRejected(404,'not_found')
    if request.method != 'POST': raise RequestRejected(405,'method_not_allowed')
    headers = {}
    for name,value in request.headers.items():
        if name.lower() in headers or len(value)>2048: raise RequestRejected(400,'malformed_request')
        headers[name.lower()]=value
    if headers.get('content-type','').split(';',1)[0].strip().lower() != 'application/json':
        raise RequestRejected(415,'unsupported_media_type')
    body = await read_limited(request,2048)
    call = auth.authenticate(headers,body,int(time.time()))
    return body,call


async def website_records(settings, token):
    try:
        remote = await asyncio.wait_for(fetch(settings.origin+'/api/operator/activations',
            headers={'Authorization':'Bearer '+token,'Accept':'application/json'},redirect='manual'),timeout=10)
        if remote.status != 200:
            phase(settings.environment.value,'website_records_failed',remote.status)
        if 300 <= remote.status < 400: raise ValueError
        if remote.status != 200: raise ValueError
        raw = await asyncio.wait_for(read_limited(remote,MAX_ACTIVATION_RESPONSE_BYTES),timeout=10)
        data=json.loads(raw)
        if (not isinstance(data,dict) or set(data)!={'schema_version','activations'}
                or type(data['schema_version']) is not int or data['schema_version']!=1
                or not isinstance(data['activations'],list) or len(data['activations'])>MAX_WEBSITE_ACTIVATIONS): raise ValueError
        return tuple(_parse_website_activation(item) for item in data['activations'])
    except Exception:
        raise RequestRejected(503,'source_unavailable') from None


def profile_provider(profile):
    # Generated from the canonical catalogue/policy during the reviewed build,
    # never from a request, website response, secret, or hand-maintained grant list.
    from frozen_profile import PROFILE
    if profile.value != PROFILE['profile']: raise ValueError
    return SimpleNamespace(features=tuple(PROFILE['features']),calculations=tuple(PROFILE['calculations']))


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        environment = getattr(self.env,'BETA_ENVIRONMENT','')
        try:
            settings,auth,_ = configure(self.env)
            phase(environment,'default_config_valid')
            body,_ = await authenticated_request(request,auth)
            phase(environment,'default_authenticated')
            namespace = self.env.SIGNING_COORDINATOR
            stub = namespace.get(namespace.idFromName(settings.object_name))
            # Send only the validated bounded raw request; the DO authenticates again.
            forwarded = Request(request.url,method='POST',headers=dict(request.headers.items()),body=body)
            phase(environment,'durable_object_dispatch_started')
            result = await stub.fetch(forwarded)
            phase(environment,'durable_object_dispatch_completed')
            return result
        except Exception as error:
            phase(environment,'default_failure')
            return failure(error)


class SigningCoordinator(DurableObject):
    async def fetch(self, request):
        environment = getattr(self.env,'BETA_ENVIRONMENT','')
        lease = None
        journal = None
        try:
            settings,auth,values = configure(self.env)
            phase(environment,'coordinator_config_valid')
            expected = self.env.SIGNING_COORDINATOR.idFromName(settings.object_name)
            if self.ctx.id.toString() != expected.toString(): raise ValueError
            body,call = await authenticated_request(request,auth)
            phase(environment,'coordinator_authenticated')
            # cryptography/Rust initializes entropy on import. Import only inside
            # an authenticated request, never during a Worker module snapshot.
            from operator_tools.licence_manager.signing_runtime import RuntimeEd25519Signer
            from operator_tools.licence_manager.signing_service import PrivateSigningService, _activation_id
            sql = DurableSql(self.ctx.storage)
            identity = 'cloudflare:'+settings.object_name
            journal = DurableJournal(sql,settings.environment,identity)
            phase(environment,'journal_initialized')
            journal.consume(call,int(time.time()))
            phase(environment,'request_consumed')
            activation_id = _activation_id(body)
            lease = journal.acquire(int(time.time()))
            phase(environment,'lease_acquired')
            signer = RuntimeEd25519Signer(values,bind_environment=True)
            phase(environment,'signer_initialized')
            source = SimpleNamespace(environment=settings.environment,origin=settings.origin)
            core = PrivateSigningService(database_factory=None,source=source,signer=signer,
                authenticator=auth,journal=journal,profile_provider=profile_provider)
            phase(environment,'website_records_started')
            try:
                facts = await website_records(settings,values['QS_OPERATOR_SYNC_TOKEN'])
            except Exception:
                phase(environment,'website_records_failed')
                raise
            phase(environment,'website_records_succeeded')
            journal.assert_owner(lease,int(time.time()))
            if abs(int(time.time())-call.timestamp)>FRESHNESS_SECONDS: raise RequestRejected(401,'stale_request')
            activation,records=core.validate_activations(activation_id,facts)
            phase(environment,'activation_validation_succeeded')
            database=DurableIssuanceDatabase(sql,journal,lease,time.time,identity)
            phase(environment,'persist_activation_started')
            envelope,existing=core.persist_activation(database,activation,records,call.caller)
            phase(environment,'persist_activation_succeeded')
            phase(environment,'second_website_records_started')
            try:
                current_facts=await website_records(settings,values['QS_OPERATOR_SYNC_TOKEN'])
            except Exception:
                phase(environment,'second_website_records_failed')
                raise
            phase(environment,'second_website_records_succeeded')
            journal.assert_owner(lease,int(time.time()))
            if abs(int(time.time())-call.timestamp)>FRESHNESS_SECONDS: raise RequestRejected(401,'stale_request')
            current,_=core.validate_activations(activation_id,current_facts)
            phase(environment,'current_activation_validation_succeeded')
            result=core.completed_response(activation,current,envelope,existing)
            phase(environment,'completed_response_created')
            reply = response(result.status,result.body)
            phase(environment,'coordinator_completed')
            return reply
        except Exception as error:
            phase(environment,'coordinator_failure')
            return failure(error)
        finally:
            if lease is not None:
                try: journal.release(lease)
                except Exception:
                    # A failed release leaves the durable lease active until expiry.
                    # It never authorizes another signature or logs a secret.
                    pass
