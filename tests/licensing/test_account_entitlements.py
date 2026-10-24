"""M9A real SQL provisioning/history/races and existing TEST issuer expiry."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
from threading import Barrier
import time
import uuid

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from backend.licensing.verifier import device_identity_from_private_key
from operator_tools.licence_manager.database import Database
from operator_tools.licence_manager.crypto import DataProtector
from operator_tools.licence_manager.issuance import IssuanceRejected, issue_website_activation_for_testing
from operator_tools.licence_manager.signing import TestEphemeralAuthority as Signer
from operator_tools.licence_manager.website_sync import WebsiteActivation, _parse_website_activation, WebsiteResponseError
from tests.helpers.licensing import beta_entitlement

APP='12345678-1234-4123-8123-123456789abc'
START=1792368000
STAMP='2026-10-19T00:00:00Z'
MIGRATIONS=Path('website/migrations')
SQL=re.search(r'prepare\(`\s*(INSERT INTO beta_activations.*?)`\)\.bind',Path('website/functions/_lib/beta-activation.js').read_text(encoding='utf-8'),re.S).group(1)


def migrate(db,through=10):
    for path in sorted(MIGRATIONS.glob('*.sql')):
        if int(path.name[:4])<=through: db.executescript(path.read_text(encoding='utf-8'))


def seed(db,status='UNDER_REVIEW'):
    db.execute("""INSERT INTO users(user_id,full_name,institution,email,normalized_email,email_lookup_hash,status,created_at,updated_at)
        VALUES('user-a','Test','Test','a@example.test','a@example.test','hash','VERIFIED',?,?)""",(STAMP,STAMP))
    db.execute("""INSERT INTO beta_applications(application_id,user_id,full_name,email,normalized_email,email_lookup_hash,institution,country,research_area,
        operating_system,privacy_consent,privacy_version,terms_consent,terms_version,communications_consent,status,submitted_at,updated_at)
        VALUES(?,'user-a','Test','a@example.test','a@example.test','hash','Test','Test','Test','Windows',1,'1',1,'1',0,?,?,?)""",(APP,status,STAMP,STAMP))
    db.commit()


def approve(db):
    db.execute("UPDATE beta_applications SET status='APPROVED',reviewed_at=?,updated_at=? WHERE application_id=?",(STAMP,STAMP,APP));db.commit()


def register(db,device='a',activation_id=None):
    installation='dev_'+device*32
    db.execute(SQL,(activation_id or str(uuid.uuid4()),installation,'windows','x86_64','0.2.0',
        STAMP,STAMP,installation,STAMP,STAMP,installation,STAMP,STAMP,STAMP,STAMP,installation,STAMP,device*64,'user-a'))
    db.commit()
    return db.execute("SELECT status FROM beta_activations WHERE installation_id=? ORDER BY (status<>'REVOKED') DESC LIMIT 1",(installation,)).fetchone()[0]


@pytest.fixture
def website(tmp_path):
    path=tmp_path/'website.sqlite3'
    db=sqlite3.connect(path);db.row_factory=sqlite3.Row
    migrate(db);seed(db);approve(db)
    yield db,path
    db.close()


def test_approved_account_provisions_exactly_one_fixed_90_day_default_grant(website):
    db,_=website
    row=dict(db.execute('SELECT * FROM account_entitlements').fetchone())
    assert row['plan_id']=='beta' and row['device_limit']==1 and row['revision']==1
    assert int(datetime.fromisoformat(row['expires_at'].replace('Z','+00:00')).timestamp())-START==90*86400
    before=json.dumps(row,sort_keys=True)
    for _ in range(3): approve(db)
    assert json.dumps(dict(db.execute('SELECT * FROM account_entitlements').fetchone()),sort_keys=True)==before
    assert db.execute("SELECT COUNT(*) FROM beta_audit_events WHERE event_type='ACCOUNT_ENTITLEMENT_PROVISIONED'").fetchone()[0]==1
    register(db)
    assert json.dumps(dict(db.execute('SELECT * FROM account_entitlements').fetchone()),sort_keys=True)==before


@pytest.mark.parametrize('limit,expected',[(1,['AUTHORIZED','FLAGGED','FLAGGED']),(2,['AUTHORIZED','AUTHORIZED','FLAGGED'])])
def test_persisted_device_limit_is_enforced_without_one_device_schema_assumption(website,limit,expected):
    db,_=website
    db.execute('UPDATE account_entitlements SET device_limit=?',(limit,));db.commit()
    assert [register(db,d) for d in 'abc']==expected
    assert register(db,'a')=='AUTHORIZED'
    assert db.execute("SELECT COUNT(*) FROM beta_activations WHERE status='AUTHORIZED'").fetchone()[0]==limit


def test_simultaneous_authorizations_cannot_both_take_final_slot(website):
    _,path=website
    barrier=Barrier(2)
    def activate(device):
        db=sqlite3.connect(path,timeout=20)
        try:
            db.execute('PRAGMA foreign_keys=ON');barrier.wait(timeout=10)
            return register(db,device)
        finally: db.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(activate,['a','b']))
    assert sorted(results)==['AUTHORIZED','FLAGGED']


def test_revoked_history_is_kept_and_same_device_gets_new_activation(website):
    db,_=website
    register(db,'a','aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa')
    db.execute("UPDATE beta_activations SET status='REVOKED',revoked_at=?",(STAMP,));db.commit()
    register(db,'a','bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb')
    rows=db.execute('SELECT activation_request_id,status,revoked_at FROM beta_activations ORDER BY activation_request_id').fetchall()
    assert [(r[0],r[1]) for r in rows]==[('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','REVOKED'),('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb','AUTHORIZED')]
    assert rows[0][2]==STAMP


def test_history_migration_preserves_original_publications_and_challenges(tmp_path):
    db=sqlite3.connect(tmp_path/'legacy.sqlite3');db.execute('PRAGMA foreign_keys=ON')
    try:
        migrate(db,8);seed(db,'APPROVED')
        db.execute("""INSERT INTO beta_activations(activation_request_id,user_id,application_id,installation_id,platform,architecture,app_version,status,created_at,updated_at)
            VALUES('old','user-a',?,'dev_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','windows','x86_64','0.2.0','REVOKED',?,?)""",(APP,STAMP,STAMP))
        db.execute("INSERT INTO published_licences VALUES('old','lic-old','original signed bytes','digest',1,'PUBLISHED')")
        db.execute("INSERT INTO licence_device_challenges VALUES('challenge','old','dev_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',?,'original challenge',9999999999,NULL)",('a'*64,));db.commit()
        original={table:db.execute('SELECT * FROM '+table).fetchall() for table in ['beta_activations','published_licences','licence_device_challenges']}
        for number in (9,10):
            path=next(MIGRATIONS.glob(f'{number:04d}_*.sql'));db.executescript(path.read_text(encoding='utf-8'))
        for table,rows in original.items(): assert db.execute('SELECT * FROM '+table).fetchall()==rows
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert db.execute('SELECT COUNT(*) FROM account_entitlements').fetchone()[0]==0
        # Repeated APPROVED is not permission to invent a new legacy lifetime.
        approve(db)
        assert db.execute('SELECT COUNT(*) FROM account_entitlements').fetchone()[0]==0
        assert register(db,'b')=='FLAGGED'
    finally: db.close()


@pytest.fixture
def issued(tmp_path):
    db=Database(tmp_path/'operator',DataProtector.for_testing(b'E'*32))
    identity=device_identity_from_private_key(Ed25519PrivateKey.generate())
    activation=WebsiteActivation(str(uuid.uuid4()),APP,identity.device_id,'windows','x86_64','0.2.0','AUTHORIZED',None,
        STAMP,STAMP,STAMP,None,identity.public_key_hash,account_entitlement=beta_entitlement())
    yield db,Signer(),activation
    db.close()


def test_later_replacement_inherits_original_expiry_without_fresh_term(issued):
    db,signer,activation=issued
    first=issue_website_activation_for_testing(db,signer,activation,now=START+86400)
    replacement=replace(activation,activation_request_id=str(uuid.uuid4()),installation_id='dev_'+'b'*32,device_public_key_hash='b'*64)
    second=issue_website_activation_for_testing(db,signer,replacement,now=START+60*86400)
    assert first['expires_at']==second['expires_at']==START+90*86400
    assert second['issued_at']==second['not_before']==START+60*86400
    assert second['expires_at']-second['issued_at']==30*86400
    assert issue_website_activation_for_testing(db,Signer(),replacement,now=START+80*86400)==second
    assert db.connection.execute('SELECT COUNT(*) FROM website_activation_licences').fetchone()[0]==2


@pytest.mark.parametrize('case',['missing','expired','future','wrong_app','wrong_plan','changed_duration','fractional_future'])
def test_missing_invalid_or_noncurrent_entitlement_never_signs(issued,case):
    db,signer,activation=issued
    grant=dict(activation.account_entitlement)
    now=START+86400
    if case=='missing': grant=None
    if case=='expired': now=START+90*86400
    if case=='future': now=START-1
    if case=='wrong_app': grant['application_id']=str(uuid.uuid4())
    if case=='wrong_plan': grant['plan_id']='arbitrary'
    if case=='changed_duration': grant['expires_at']='2099-01-01T00:00:00Z'
    if case=='fractional_future':
        grant['starts_at']='2026-10-19T00:00:00.500Z';grant['expires_at']='2027-01-17T00:00:00.500Z';now=START
    activation=replace(activation,account_entitlement=grant)
    def forbidden(_): pytest.fail('Signing must not run')
    signer.sign_test_fixture_only=forbidden
    with pytest.raises(IssuanceRejected): issue_website_activation_for_testing(db,signer,activation,now=now)
    assert db.connection.execute('SELECT COUNT(*) FROM website_activation_licences').fetchone()[0]==0


def test_changed_account_dates_are_rejected_for_a_second_device(issued):
    db,signer,activation=issued
    first=issue_website_activation_for_testing(db,signer,activation,now=START+86400)
    next_grant=beta_entitlement(starts_at=START+86400)
    other=replace(activation,activation_request_id=str(uuid.uuid4()),account_entitlement=next_grant)
    with pytest.raises(IssuanceRejected,match='conflicts'): issue_website_activation_for_testing(db,signer,other,now=START+2*86400)
    assert issue_website_activation_for_testing(db,Signer(),activation,now=START+3*86400)==first


def test_legacy_local_envelope_is_recovered_without_rewriting_or_resigning(issued):
    db,signer,activation=issued
    original=issue_website_activation_for_testing(db,signer,activation,now=START+86400)
    db.connection.execute('DELETE FROM website_account_entitlements');db.connection.commit()
    recovered=issue_website_activation_for_testing(db,Signer(),replace(activation,account_entitlement=None),now=START+864000)
    assert recovered==original
    assert db.connection.execute('SELECT COUNT(*) FROM website_account_entitlements').fetchone()[0]==0


def test_operator_parser_rejects_conflicting_entitlement_binding(issued):
    from dataclasses import asdict
    _,_,activation=issued
    payload=asdict(activation);payload['account_entitlement']['application_id']=str(uuid.uuid4())
    with pytest.raises(WebsiteResponseError): _parse_website_activation(payload)
