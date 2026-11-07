"""Private service boundary; fixed synthetic secrets only, no deployment or network."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import hashlib
from io import BytesIO
import json
from types import SimpleNamespace

import pytest
from backend.licensing.canonical import b64url_encode, canonical_json
from backend.licensing.configuration import Environment
from backend.licensing.verifier import LeaseVerifier, device_identity_from_private_key
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from operator_tools.licence_manager.crypto import DataProtector
from operator_tools.licence_manager.database import Database
from operator_tools.licence_manager.website_sync import WebsiteActivation
from operator_tools.licence_manager.signing import TestEphemeralAuthority as _TestAuthority
from operator_tools.licence_manager.signing_runtime import RuntimeEd25519Signer
from operator_tools.licence_manager.signing_service import (
    PrivateSigningService, SigningServiceRequest, AuthoritativeWebsiteSource, signing_service_wsgi,
)
from operator_tools.licence_manager.signing_service_auth import (
    HmacServiceAuthenticator, SqliteRequestJournal, ServiceConfigurationError,
    service_auth_headers, ISSUE_PATH, FRESHNESS_SECONDS,
)
from tests.licensing.test_production_signing import select, NOW, APP, SEED
from tests.helpers.licensing import beta_entitlement

AUTH_KEY = b'S'*32
CALLER = 'unit-operator'
AID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
ORIGIN = 'https://backend.unit-fixture.org'


def auth_record(mode='production'):
    return json.dumps({'schema_version': 1, 'environment': mode, 'callers': {CALLER: b64url_encode(AUTH_KEY)}})


class Source:
    environment = Environment.PRODUCTION
    origin = ORIGIN
    def __init__(self, records):
        self.records, self.reads, self.failure, self.after_read = records, 0, None, None
    def read_activations(self):
        self.reads += 1
        if self.failure: raise RuntimeError(self.failure)
        result = deepcopy(self.records)
        if self.after_read: self.after_read(self.reads)
        return result


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    select(monkeypatch)
    device = device_identity_from_private_key(Ed25519PrivateKey.from_private_bytes(b'D'*32))
    stamp = '2027-01-15T08:00:00Z'
    activation = WebsiteActivation(AID, APP, device.device_id, 'windows', 'x86_64', '0.2.0',
        'AUTHORIZED', None, stamp, stamp, stamp, None, device.public_key_hash,
        account_entitlement=beta_entitlement(starts_at=NOW-100))
    source = Source((activation,))
    @contextmanager
    def database_factory():
        db = Database(tmp_path/'operator', DataProtector.for_testing(b'P'*32))
        try: yield db
        finally: db.close()
    clock = SimpleNamespace(now=NOW)
    journal = SqliteRequestJournal(tmp_path/'private-service.sqlite3', Environment.PRODUCTION)
    signer = RuntimeEd25519Signer()
    auth = HmacServiceAuthenticator(Environment.PRODUCTION, auth_record())
    def create_service(**changes):
        return PrivateSigningService(**{'database_factory': database_factory, 'source': source,
            'signer': signer, 'authenticator': auth, 'journal': journal, 'clock': lambda: clock.now, **changes})
    b = SimpleNamespace(source=source, activation=activation, device=device, signer=signer, clock=clock,
        journal=journal, auth=auth, create_service=create_service, database_factory=database_factory, sequence=0)
    b.service = create_service()
    yield b


def request(b, body=None, *, nonce=None, timestamp=None, environment=Environment.PRODUCTION, secret=AUTH_KEY, caller=CALLER):
    b.sequence += 1
    raw = canonical_json({'schema_version': 1, 'activation_request_id': AID}) if body is None else body
    headers = service_auth_headers(environment=environment, caller=caller, secret=secret,
        timestamp=b.clock.now if timestamp is None else timestamp, nonce=nonce or f'{b.sequence:064x}', body=raw)
    return SigningServiceRequest('POST', ISSUE_PATH, 'https', headers, raw)


def error(response, status, code):
    assert response.status == status
    assert response.body == {'error': {'code': code}}


def test_authenticated_identifier_only_issuance_independently_loads_and_verifies(bundle):
    b = bundle
    response = b.service.handle(request(b))
    assert response.status == 200 and response.body['result'] == 'persisted'
    assert b.source.reads == 2
    envelope = response.body['envelope']
    assert LeaseVerifier({b.signer.kid: b.signer.public_key}).verify(envelope, b.device).lease.kid == b.signer.kid
    assert response.body['envelope_sha256'] == hashlib.sha256(canonical_json(envelope)).hexdigest()
    assert envelope['expires_at'] == NOW-100+90*86400 and envelope['registered_device_limit'] == 1
    with b.database_factory() as db:
        assert db.connection.execute('SELECT COUNT(*) FROM website_activation_licences').fetchone()[0] == 1
        assert db.connection.execute("SELECT COUNT(*) FROM audit_events WHERE event_type='licence_issuance'").fetchone()[0] == 1


@pytest.mark.parametrize('attack', ['missing', 'wrong-key', 'unknown-caller', 'wrong-environment', 'body-edit', 'header-edit'])
def test_invalid_service_auth_rejected_before_authoritative_or_private_database_access(bundle, attack):
    b = bundle
    req = request(b)
    if attack == 'missing': req = replace(req, headers={'Content-Type': 'application/json'})
    if attack == 'wrong-key': req = request(b, secret=b'W'*32)
    if attack == 'unknown-caller': req = request(b, caller='not-allowed')
    if attack == 'wrong-environment': req = request(b, environment=Environment.STAGING)
    if attack == 'body-edit': req = replace(req, body=req.body+b' ')
    if attack == 'header-edit': req = replace(req, headers={**req.headers, 'X-QS-Nonce': 'f'*64})
    error(b.service.handle(req), 401, 'unauthorized')
    assert b.source.reads == 0


@pytest.mark.parametrize('offset', [-FRESHNESS_SECONDS-1, FRESHNESS_SECONDS+1])
def test_stale_or_future_request_rejected(bundle, offset):
    error(bundle.service.handle(request(bundle, timestamp=NOW+offset)), 401, 'stale_request')
    assert bundle.source.reads == 0


def test_nonce_replay_survives_restart_and_fresh_retry_is_idempotent(bundle):
    b = bundle
    req = request(b)
    first = b.service.handle(req)
    assert first.status == 200
    restarted = b.create_service(journal=SqliteRequestJournal(b.journal.path, Environment.PRODUCTION))
    error(restarted.handle(req), 409, 'replay_rejected')
    second = restarted.handle(request(b))
    assert second.status == 200 and second.body['result'] == 'already_current'
    assert second.body['envelope'] == first.body['envelope']
    with b.database_factory() as db:
        assert db.connection.execute('SELECT COUNT(*) FROM website_activation_licences').fetchone()[0] == 1
        assert db.connection.execute("SELECT COUNT(*) FROM audit_events WHERE event_type='licence_issuance'").fetchone()[0] == 1


def test_failed_authenticated_request_also_consumes_nonce(bundle):
    b = bundle
    b.source.failure = 'sensitive-body-do-not-return'
    req = request(b)
    error(b.service.handle(req), 503, 'source_unavailable')
    b.source.failure = None
    error(b.service.handle(req), 409, 'replay_rejected')
    assert b.service.handle(request(b)).status == 200


@pytest.mark.parametrize('body', [b'{}', b'[]', b'null', b'not-json', b'\xff',
    canonical_json({'schema_version': True, 'activation_request_id': AID}),
    canonical_json({'schema_version': 1, 'activation_request_id': 'invalid'}),
    canonical_json({'schema_version': 1, 'activation_request_id': AID, 'payload': {}}),
    canonical_json({'schema_version': 1, 'activation_request_id': AID, 'user_id': 'caller-chosen'}),
    b'{"schema_version":1,"schema_version":1,"activation_request_id":"'+AID.encode()+b'"}'])
def test_malformed_or_arbitrary_payloads_rejected(bundle, body):
    error(bundle.service.handle(request(bundle, body)), 400, 'malformed_request')
    assert bundle.source.reads == 0


@pytest.mark.parametrize('change', [{'status': 'FLAGGED'}, {'status': 'REVOKED'},
    {'revoked_at': '2027-01-15T08:00:00Z'}, {'licence_revoked_at': '2027-01-15T08:00:00Z'},
    {'flag_reason': 'DEVICE_LIMIT'}, {'authorized_at': None}, {'device_public_key_hash': None}])
def test_unauthorized_revoked_or_unbound_activation_rejected(bundle, change):
    b = bundle
    b.source.records = (replace(b.activation, **change),)
    error(b.service.handle(request(b)), 409, 'activation_unavailable')


def test_missing_activation_is_not_synthesized_from_request(bundle):
    bundle.source.records = ()
    error(bundle.service.handle(request(bundle)), 409, 'activation_unavailable')


def test_expired_entitlement_rejected_even_for_existing_signed_activation(bundle):
    b = bundle
    assert b.service.handle(request(b)).status == 200
    b.clock.now = NOW+90*86400
    error(b.service.handle(request(b)), 409, 'entitlement_unavailable')


def test_changed_account_entitlement_conflicts_with_original_snapshot(bundle):
    b = bundle
    assert b.service.handle(request(b)).status == 200
    entitlement = {**b.activation.account_entitlement, 'user_id': 'another-user'}
    b.source.records = (replace(b.activation, account_entitlement=entitlement),)
    error(b.service.handle(request(b)), 409, 'licence_conflict')


def test_malformed_authoritative_response_and_duplicate_ids_fail_closed(bundle):
    b = bundle
    b.source.records = (b.activation, b.activation)
    error(b.service.handle(request(b)), 503, 'source_unavailable')
    b.source.records = (replace(b.activation, device_public_key_hash='invalid'),)
    error(b.service.handle(request(b)), 503, 'source_unavailable')


@pytest.mark.parametrize('kind', ['remote-id', 'remote-expiry', 'partial-remote', 'stored-signature', 'stored-binding', 'missing-key'])
def test_existing_licence_or_envelope_mismatch_rejected(bundle, kind):
    b = bundle
    first = b.service.handle(request(b)).body['envelope']
    stamp = lambda value: datetime.fromtimestamp(value, timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
    remote = replace(b.activation, licence_id=first['licence_id'], licence_status='ISSUED',
        licence_issued_at=stamp(first['issued_at']), licence_expires_at=stamp(first['expires_at']))
    if kind == 'remote-id': remote = replace(remote, licence_id='lic_bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb')
    if kind == 'remote-expiry': remote = replace(remote, licence_expires_at=stamp(first['expires_at']-1))
    if kind == 'partial-remote': remote = replace(remote, licence_status=None)
    b.source.records = (remote,)
    if kind.startswith('stored-') or kind == 'missing-key':
        with b.database_factory() as db:
            if kind == 'missing-key': db.connection.execute('DELETE FROM signing_keys')
            else:
                changed = {**first, 'signature': 'bad'} if kind == 'stored-signature' else {**first, 'device_id': 'dev_'+'a'*32}
                db.connection.execute('UPDATE website_activation_licences SET envelope_json=?', (json.dumps(changed),))
            db.connection.commit()
    error(b.service.handle(request(b)), 409, 'licence_conflict')


def test_matching_remote_metadata_returns_original_without_resigning(bundle, monkeypatch):
    b = bundle
    first = b.service.handle(request(b)).body['envelope']
    stamp = lambda value: datetime.fromtimestamp(value, timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
    b.source.records = (replace(b.activation, licence_id=first['licence_id'], licence_status='ISSUED',
        licence_issued_at=stamp(first['issued_at']), licence_expires_at=stamp(first['expires_at'])),)
    def forbidden(*args, **kwargs): pytest.fail('Original envelope must not be re-signed')
    monkeypatch.setattr(b.signer, 'sign_licence', forbidden)
    result = b.service.handle(request(b))
    assert result.status == 200 and result.body['result'] == 'already_current'
    assert result.body['envelope'] == first


def test_remote_licence_without_private_original_fails_closed(bundle):
    b = bundle
    b.source.records = (replace(b.activation, licence_id='lic_bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'),)
    error(b.service.handle(request(b)), 409, 'licence_conflict')


def test_concurrent_fresh_calls_create_one_immutable_envelope(bundle):
    b = bundle
    calls = [request(b) for _ in range(6)]
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(b.service.handle, calls))
    assert all(result.status == 200 for result in results)
    assert sum(result.body['result'] == 'persisted' for result in results) == 1
    assert len({result.body['envelope_sha256'] for result in results}) == 1


def test_concurrent_replay_has_exactly_one_winner(bundle):
    b = bundle
    req = request(b)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(b.service.handle, [req]*4))
    assert sorted(result.status for result in results) == [200, 409, 409, 409]


def test_observed_revocation_after_signing_withholds_envelope_and_preserves_original(bundle):
    b = bundle
    def revoke(reads):
        if reads == 1: b.source.records = (replace(b.activation, status='REVOKED'),)
    b.source.after_read = revoke
    result = b.service.handle(request(b))
    error(result, 409, 'activation_unavailable')
    assert 'envelope' not in result.body
    with b.database_factory() as db:
        assert db.connection.execute('SELECT COUNT(*) FROM website_activation_licences').fetchone()[0] == 1
    error(b.service.handle(request(b)), 409, 'activation_unavailable')


def test_replacement_after_terminal_revocation_inherits_original_expiry(bundle):
    b = bundle
    first = b.service.handle(request(b)).body['envelope']
    replacement = replace(b.activation, activation_request_id='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb')
    b.source.records = (replace(b.activation, status='REVOKED'), replacement)
    raw = canonical_json({'schema_version': 1, 'activation_request_id': replacement.activation_request_id})
    result = b.service.handle(request(b, raw))
    assert result.status == 200 and result.body['envelope']['expires_at'] == first['expires_at']
    assert result.body['envelope']['licence_id'] != first['licence_id']
    error(b.service.handle(request(b)), 409, 'activation_unavailable')


def test_clock_rollback_cannot_replay_a_pruned_nonce(bundle):
    b = bundle
    old = request(b)
    assert b.service.handle(old).status == 200
    b.clock.now += FRESHNESS_SECONDS+2
    assert b.service.handle(request(b)).status == 200
    b.clock.now = NOW
    error(b.service.handle(old), 503, 'service_unavailable')


def test_test_signer_or_wrong_profile_rejected_at_composition(bundle, monkeypatch):
    b = bundle
    monkeypatch.setenv('BETA_ENVIRONMENT', 'local')
    test = _TestAuthority()
    monkeypatch.setenv('BETA_ENVIRONMENT', 'production')
    with pytest.raises(ServiceConfigurationError): b.create_service(signer=test)
    wrong = HmacServiceAuthenticator(Environment.STAGING, auth_record('staging'))
    with pytest.raises(ServiceConfigurationError): b.create_service(authenticator=wrong)
    with pytest.raises(ServiceConfigurationError): SqliteRequestJournal(b.journal.path, Environment.STAGING)


def test_environment_change_after_startup_fails_closed(bundle, monkeypatch):
    monkeypatch.setenv('BETA_ENVIRONMENT', 'staging')
    error(bundle.service.handle(request(bundle)), 503, 'configuration_unavailable')
    assert bundle.source.reads == 0


def test_private_keys_and_credentials_never_appear_in_response_or_logs(bundle, caplog):
    b = bundle
    good = b.service.handle(request(b))
    b.source.failure = 'DO-NOT-EXPOSE-'+b64url_encode(SEED)
    bad = b.service.handle(request(b))
    text = json.dumps([good.body, bad.body])+caplog.text+repr(b.service)+repr(b.auth)
    for secret in (b64url_encode(SEED), SEED.hex(), b64url_encode(AUTH_KEY), 'DO-NOT-EXPOSE'):
        assert secret not in text
    assert not caplog.records


def test_wsgi_adapter_requires_tls_and_does_not_trust_forwarded_headers(bundle):
    b = bundle
    app = signing_service_wsgi(b.service)
    req = request(b)
    env = {'REQUEST_METHOD': req.method, 'PATH_INFO': req.target, 'QUERY_STRING': '',
        'wsgi.url_scheme': 'https', 'CONTENT_LENGTH': str(len(req.body)), 'CONTENT_TYPE': 'application/json',
        'wsgi.input': BytesIO(req.body), **{'HTTP_'+name.upper().replace('-', '_'): value
            for name, value in req.headers.items() if name != 'Content-Type'}}
    seen = []
    body = json.loads(b''.join(app(env, lambda status, headers: seen.append((status, headers)))))
    assert seen[0][0] == '200 OK' and body['result'] == 'persisted'
    assert ('Cache-Control', 'no-store') in seen[0][1]
    env.update({'wsgi.url_scheme': 'http', 'HTTP_X_FORWARDED_PROTO': 'https', 'wsgi.input': BytesIO(req.body)})
    body = json.loads(b''.join(app(env, lambda status, headers: seen.append((status, headers)))))
    assert body == {'error': {'code': 'https_required'}} and seen[-1][0].startswith('403')


@pytest.mark.parametrize('change,status,code', [({'scheme': 'http'},403,'https_required'),
    ({'method': 'GET'},405,'method_not_allowed'), ({'target': ISSUE_PATH+'?x=1'},404,'not_found'),
    ({'body': b'x'*2049},413,'request_too_large'), ({'headers': {}},415,'unsupported_media_type')])
def test_transport_guards(bundle, change, status, code):
    error(bundle.service.handle(replace(request(bundle), **change)), status, code)
    assert bundle.source.reads == 0


@pytest.mark.parametrize('record', ['', '{}', 'null', '{"schema_version":1,"environment":"production","callers":{}}',
    json.dumps({'schema_version':1,'environment':'staging','callers':{CALLER:b64url_encode(AUTH_KEY)}}),
    json.dumps({'schema_version':1,'environment':'production','callers':{CALLER:'invalid'}}),
    '{"schema_version":1,"schema_version":1,"environment":"production","callers":{}}'])
def test_invalid_authentication_configuration_fails_closed(record):
    with pytest.raises(ServiceConfigurationError):
        HmacServiceAuthenticator(Environment.PRODUCTION, record)


def test_from_environment_uses_existing_https_operator_source_with_independent_reads(bundle, monkeypatch):
    from operator_tools.licence_manager import website_sync
    b = bundle
    monkeypatch.setenv('QS_SIGNING_SERVICE_AUTH', auth_record())
    monkeypatch.setenv('QS_SIGNING_SERVICE_STATE_PATH', str(b.journal.path))
    monkeypatch.setenv('QS_OPERATOR_WEBSITE_URL', ORIGIN)
    monkeypatch.setenv('QS_OPERATOR_SYNC_TOKEN', 'synthetic-operator-read-only')
    calls = []
    class Response:
        status = 200
        headers = {}
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit):
            return canonical_json({'schema_version':1,'activations':[asdict(b.activation)]})[:limit]
    class Opener:
        def open(self, req, timeout):
            calls.append(req)
            assert req.full_url == ORIGIN+'/api/operator/activations'
            assert req.get_header('Authorization') == 'Bearer synthetic-operator-read-only'
            return Response()
    monkeypatch.setattr(website_sync, 'build_opener', lambda *args: Opener())
    service = PrivateSigningService.from_environment(b.database_factory, clock=lambda: b.clock.now)
    result = service.handle(request(b))
    assert result.status == 200 and len(calls) == 2
    assert b.source.reads == 0  # The caller's in-memory facts are not used.
    assert 'synthetic-operator-read-only' not in json.dumps(result.body)


@pytest.mark.parametrize('name', ['QS_SIGNING_SERVICE_AUTH', 'QS_SIGNING_SERVICE_STATE_PATH',
    'QS_LICENCE_SIGNING_KEY', 'QS_OPERATOR_WEBSITE_URL', 'QS_OPERATOR_SYNC_TOKEN'])
def test_missing_runtime_configuration_never_exposes_a_service(bundle, monkeypatch, name):
    b = bundle
    monkeypatch.setenv('QS_SIGNING_SERVICE_AUTH', auth_record())
    monkeypatch.setenv('QS_SIGNING_SERVICE_STATE_PATH', str(b.journal.path))
    monkeypatch.setenv('QS_OPERATOR_WEBSITE_URL', ORIGIN)
    monkeypatch.setenv('QS_OPERATOR_SYNC_TOKEN', 'synthetic-operator-read-only')
    monkeypatch.delenv(name)
    with pytest.raises(ServiceConfigurationError): PrivateSigningService.from_environment(b.database_factory)


def test_unavailable_replay_store_fails_before_source_or_issuance(bundle, monkeypatch):
    def unavailable(*args): raise RuntimeError('SECRET-SHOULD-NOT-LEAK')
    monkeypatch.setattr(bundle.journal, 'consume', unavailable)
    error(bundle.service.handle(request(bundle)), 503, 'service_unavailable')
    assert bundle.source.reads == 0


def test_post_signing_source_outage_keeps_original_for_a_fresh_retry(bundle):
    b = bundle
    def fail_after_first(reads):
        if reads == 1: b.source.failure = 'unreachable'
    b.source.after_read = fail_after_first
    error(b.service.handle(request(b)), 503, 'source_unavailable')
    with b.database_factory() as db:
        original = db.connection.execute('SELECT envelope_json FROM website_activation_licences').fetchone()[0]
    b.source.after_read, b.source.failure = None, None
    result = b.service.handle(request(b))
    assert result.status == 200 and result.body['result'] == 'already_current'
    assert result.body['envelope'] == json.loads(original)


def test_distinct_journal_cannot_issue_through_already_bound_database(bundle, tmp_path):
    b = bundle
    assert b.service.handle(request(b)).status == 200
    other = b.create_service(journal=SqliteRequestJournal(tmp_path/'another-journal.sqlite3', Environment.PRODUCTION))
    error(other.handle(request(b)), 503, 'service_unavailable')


def test_valid_staging_service_requires_separate_profile_and_state(bundle, tmp_path, monkeypatch):
    b = bundle
    select(monkeypatch, 'staging')
    source = Source((b.activation,)); source.environment = Environment.STAGING
    journal = SqliteRequestJournal(tmp_path/'staging-journal.sqlite3', Environment.STAGING)
    @contextmanager
    def staging_db():
        db = Database(tmp_path/'staging-operator', DataProtector.for_testing(b'G'*32))
        try: yield db
        finally: db.close()
    service = b.create_service(database_factory=staging_db, source=source, signer=RuntimeEd25519Signer(),
        authenticator=HmacServiceAuthenticator(Environment.STAGING, auth_record('staging')), journal=journal)
    result = service.handle(request(b, environment=Environment.STAGING))
    assert result.status == 200
    error(service.handle(request(b)), 401, 'unauthorized')


@pytest.mark.parametrize('authorization', ['Bearer desktop-session-token', 'Device device-proof', ''])
def test_desktop_or_browser_credentials_do_not_authenticate_service(bundle, authorization):
    req = request(bundle)
    headers = {'Content-Type':'application/json', 'Cookie':'session=browser-cookie', 'Authorization':authorization}
    error(bundle.service.handle(replace(req, headers=headers)), 401, 'unauthorized')
    assert bundle.source.reads == 0


def test_duplicate_case_variant_auth_headers_are_rejected(bundle):
    req = request(bundle)
    error(bundle.service.handle(replace(req, headers={**req.headers, 'x-qs-caller':CALLER})), 400, 'malformed_request')
    assert bundle.source.reads == 0
