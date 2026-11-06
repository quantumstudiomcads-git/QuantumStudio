"""M10 clean and M8/M9A/M9B upgrade paths preserve real SQL history."""
import json
import sqlite3
from pathlib import Path
import pytest
from tests.licensing.test_account_entitlements import migrate,seed,approve,APP,STAMP

MIGRATIONS=Path('website/migrations')
ID='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'


@pytest.mark.parametrize('through',[0,8,10,11],ids=['clean','M8','M9A','M9B'])
def test_clean_and_historical_upgrades_preserve_entitlements_licences_and_revocation(tmp_path,through):
    db=sqlite3.connect(tmp_path/'upgrade.sqlite3');db.row_factory=sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:
        migrate(db,through)
        old={}
        if through:
            seed(db)
            if through>=10:approve(db)
            db.execute("""INSERT INTO beta_activations(activation_request_id,user_id,application_id,installation_id,platform,
                architecture,app_version,status,created_at,updated_at,authorized_at,revoked_at,device_public_key_hash,
                licence_id,licence_status,licence_issued_at,licence_expires_at)
                VALUES(?,'user-a',?,'dev_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','windows','x86_64','0.2.0','REVOKED',?,?,?,?,?,
                'lic_bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb','ISSUED',?,'2027-01-17T00:00:00Z')""",
                (ID,APP,STAMP,STAMP,STAMP,STAMP,'a'*64,STAMP))
            if through>=11:
                db.execute("UPDATE beta_activations SET revocation_reason_code='DEVICE_LOST',revocation_reason_text='Fixture note'")
            db.execute("INSERT INTO published_licences VALUES(?,'lic_bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb','original signed bytes','original digest',1,'PUBLISHED')",(ID,))
            db.execute("INSERT INTO licence_device_challenges VALUES('historical-proof',?,'dev_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',?,'original challenge',9999999999,NULL)",(ID,'a'*64))
            db.execute("""INSERT INTO beta_audit_events VALUES('revocation-audit',?,'OPERATOR_DEVICE_REVOKED',?,
                'operator-device-revocation','AUTHORIZED','REVOKED',?)""",(APP,STAMP,json.dumps({'activation_id':ID,'reason_code':'DEVICE_LOST'})))
            db.commit()
            tables=['beta_applications','beta_activations','published_licences','licence_device_challenges','beta_audit_events']
            if through>=10:tables.append('account_entitlements')
            old={table:[dict(row) for row in db.execute('SELECT * FROM '+table)] for table in tables}
        for migration in sorted(MIGRATIONS.glob('*.sql')):
            if int(migration.name[:4])>through:db.executescript(migration.read_text(encoding='utf-8'))
        for table,rows in old.items():
            current=[dict(row) for row in db.execute('SELECT * FROM '+table)]
            assert len(current)==len(rows)
            for original,upgraded in zip(rows,current):assert all(upgraded[key]==value for key,value in original.items())
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert 'authorization_revision' in {row[1] for row in db.execute('PRAGMA table_info(beta_activations)')}
        assert {'challenge_id','activation_request_id','message_json','expires_at','consumed_at'}=={row[1] for row in db.execute('PRAGMA table_info(device_status_challenges)')}
        if through:
            row=db.execute('SELECT status,authorization_revision FROM beta_activations').fetchone()
            assert tuple(row)==('REVOKED',1)
            with pytest.raises(sqlite3.IntegrityError):db.execute("UPDATE beta_activations SET status='AUTHORIZED'")
            db.rollback()
        if through in (0,8):assert db.execute('SELECT COUNT(*) FROM account_entitlements').fetchone()[0]==0
    finally:db.close()


def test_revoke_racing_replacement_retry_never_overfills_slot_or_changes_grant(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from tests.licensing.test_account_entitlements import register
    path=tmp_path/'race.sqlite3'
    db=sqlite3.connect(path);db.row_factory=sqlite3.Row
    latest=max(int(p.name[:4]) for p in MIGRATIONS.glob('*.sql'))
    migrate(db,latest);seed(db);approve(db)
    assert register(db,'a',ID)=='AUTHORIZED'
    assert register(db,'b','bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb')=='FLAGGED'
    original=dict(db.execute('SELECT * FROM account_entitlements').fetchone());db.close()
    barrier=Barrier(2)
    def run(action):
        connection=sqlite3.connect(path,timeout=20)
        try:
            barrier.wait(timeout=10)
            if action=='revoke':
                connection.execute("UPDATE beta_activations SET status='REVOKED',revoked_at=?,revocation_reason_code='DEVICE_REPLACED' WHERE activation_request_id=? AND status='AUTHORIZED'",(STAMP,ID));connection.commit()
            else:register(connection,'b')
        finally:connection.close()
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(run,['revoke','retry']))
    db=sqlite3.connect(path);db.row_factory=sqlite3.Row
    try:
        assert db.execute('SELECT status FROM beta_activations WHERE activation_request_id=?',(ID,)).fetchone()[0]=='REVOKED'
        assert db.execute("SELECT COUNT(*) FROM beta_activations WHERE status='AUTHORIZED'").fetchone()[0]<=1
        assert register(db,'b')=='AUTHORIZED' # retry resolves either valid serialization.
        assert db.execute('SELECT COUNT(*) FROM beta_activations').fetchone()[0]==2
        assert dict(db.execute('SELECT * FROM account_entitlements').fetchone())==original
    finally:db.close()
