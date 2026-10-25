import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {existsSync, mkdtempSync, readFileSync, readdirSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join, resolve} from 'node:path';
import {execFileSync} from 'node:child_process';
import {onRequestGet as exportActivations} from '../functions/api/operator/activations.js';
import {SQLiteD1} from './helpers/sqlite-d1.mjs';
import {onRequestPost as revokeRoute} from '../functions/api/operator/activations/[activationId]/revoke.js';
import {registerActivationForUser} from '../functions/_lib/beta-activation.js';

vi.setConfig({testTimeout:30000});
const app='12345678-1234-4123-8123-123456789abc', origin='http://localhost:8788';
const token='synthetic-revocation-only';
let root, db, env, deviceA;
const register=async(key)=>{
  const response=await registerActivationForUser(env,'user-a',{installation_id:'dev_'+key.repeat(32),
    device_public_key_hash:key.repeat(64),platform:'windows',architecture:'x86_64',app_version:'0.2.0'});
  expect(response.status).toBe(200);return (await response.json()).activation;
};
const row=(id=deviceA.activation_request_id)=>db.prepare('SELECT * FROM beta_activations WHERE activation_request_id=?').bind(id).first();
const grant=()=>db.prepare('SELECT * FROM account_entitlements').first();
const events=async()=>(await db.prepare("SELECT * FROM beta_audit_events WHERE event_type='OPERATOR_DEVICE_REVOKED'").all()).results;
const payload={schema_version:1,reason_code:'DEVICE_REPLACED',expected_status:'AUTHORIZED'};
const revoke=(body=payload,credential=token,id=deviceA.activation_request_id,extra={})=>revokeRoute({env,params:{activationId:id},
  request:new Request(origin+'/api/operator/activations/'+id+'/revoke',{method:'POST',
    headers:{'Content-Type':'application/json',...(credential?{Authorization:'Bearer '+credential}:{}),...extra},body:JSON.stringify(body)})});
beforeEach(async()=>{
  vi.useFakeTimers({toFake:['Date']});vi.setSystemTime(new Date('2027-01-01T00:00:00Z'));
  root=mkdtempSync(join(tmpdir(),'qs-m9b-'));db=new SQLiteD1(join(root,'db.sqlite3'));
  db.script(readdirSync('migrations').filter((p)=>p.endsWith('.sql')).sort().map((p)=>readFileSync(join('migrations',p),'utf8')).join('\n'));
  db.script(`INSERT INTO users(user_id,full_name,institution,email,normalized_email,email_lookup_hash,status,created_at,updated_at)
    VALUES('user-a','Test','Test','a@example.test','a@example.test','hash','VERIFIED','2027-01-01','2027-01-01');
    INSERT INTO beta_applications(application_id,user_id,full_name,email,normalized_email,email_lookup_hash,institution,country,research_area,
      operating_system,privacy_consent,privacy_version,terms_consent,terms_version,communications_consent,status,submitted_at,updated_at)
    VALUES('${app}','user-a','Test','a@example.test','a@example.test','hash','Test','Test','Test','Windows',1,'1',1,'1',0,'APPROVED','2027-01-01','2027-01-01');`);
  env={BETA_DB:db,BETA_ENVIRONMENT:'local',BETA_ALLOWED_ORIGIN:origin,OPERATOR_ACTIVATION_REVOKE_TOKEN:token};
  deviceA=await register('a');
});
afterEach(()=>{vi.useRealTimers();if(root)rmSync(root,{recursive:true,force:true});});

describe('M9B specific-device revocation with real migrations and SQL',()=>{
  it('persists reason/note/time, preserves all other data, and appends exactly one safe durable audit',async()=>{
    const before=await row(),entitlement=await grant();
    const response=await revoke({...payload,reason_text:'Replacement requested'});
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({schema_version:1,activation_request_id:deviceA.activation_request_id,
      status:'REVOKED',result:'revoked',revoked_at:'2027-01-01T00:00:00.000Z',reason_code:'DEVICE_REPLACED'});
    const current=await row();expect(current).toEqual({...before,status:'REVOKED',revoked_at:'2027-01-01T00:00:00.000Z',
      revocation_reason_code:'DEVICE_REPLACED',revocation_reason_text:'Replacement requested'});
    expect(await grant()).toEqual(entitlement);
    expect((await db.prepare('SELECT status FROM beta_applications').first()).status).toBe('APPROVED');
    const audit=await events();expect(audit).toHaveLength(1);
    expect(audit[0]).toMatchObject({old_status:'AUTHORIZED',new_status:'REVOKED',event_timestamp:current.revoked_at});
    expect(JSON.parse(audit[0].metadata_json)).toEqual({schema:1,activation_id:deviceA.activation_request_id,reason_code:'DEVICE_REPLACED'});
    expect(JSON.stringify(audit)).not.toContain(token);expect(JSON.stringify(audit)).not.toContain('Replacement requested');
  });
  it('keeps original reason/timestamp and exactly one audit on identical later retries',async()=>{
    expect((await revoke()).status).toBe(200);const original=await row(),entitlement=await grant();
    vi.setSystemTime(new Date('2027-02-01T00:00:00Z'));
    for(let i=0;i<2;i++)expect(await (await revoke()).json()).toMatchObject({result:'already_revoked',revoked_at:original.revoked_at});
    expect(await row()).toEqual(original);expect(await grant()).toEqual(entitlement);expect(await events()).toHaveLength(1);
  });
  it('conflicts on a different reason or note without mutating the first revocation',async()=>{
    await revoke();const original=await row();
    expect((await revoke({...payload,reason_code:'OTHER'})).status).toBe(409);
    expect((await revoke({...payload,reason_text:'Different note'})).status).toBe(409);
    expect(await row()).toEqual(original);expect(await events()).toHaveLength(1);
  });
  it('rejects FLAGGED and stale expected state without audit',async()=>{
    const b=await register('b');expect(b.status).toBe('FLAGGED');
    expect((await revoke(payload,token,b.activation_request_id)).status).toBe(409);
    expect((await revoke({...payload,expected_status:'FLAGGED'})).status).toBe(409);
    expect(await events()).toHaveLength(0);expect((await row()).status).toBe('AUTHORIZED');
  });
  it.each([null,'read-token','metadata-token','publish-token','status-token'])('requires the dedicated credential (%s)',async(credential)=>{
    expect((await revoke(payload,credential)).status).toBe(credential?403:401);
    expect((await row()).status).toBe('AUTHORIZED');expect(await events()).toHaveLength(0);
  });
  it('fails closed when credential is absent or production uses HTTP',async()=>{
    env.OPERATOR_ACTIVATION_REVOKE_TOKEN='';expect((await revoke()).status).toBe(503);
    env.OPERATOR_ACTIVATION_REVOKE_TOKEN=token;env.BETA_ENVIRONMENT='production';expect((await revoke()).status).toBe(403);
  });
  it.each([{reason_code:'invented'},{reason_code:null},{schema_version:true},{schema_version:2},
    {reason_text:''},{reason_text:'x'.repeat(241)},{reason_text:'secret\nline'},{extra:'not allowed'},{expected_status:undefined}])(
    'rejects malformed payload %j',async(change)=>{
      expect((await revoke({...payload,...change})).status).toBe(400);
      expect((await row()).status).toBe('AUTHORIZED');expect(await events()).toHaveLength(0);
    });
  it('bounds streaming body size and rejects invalid identifiers/missing records',async()=>{
    expect((await revoke({...payload,reason_text:'x'.repeat(3000)})).status).toBe(413);
    expect((await revoke(payload,token,'not-an-id')).status).toBe(400);
    expect((await revoke(payload,token,'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb')).status).toBe(404);
  });
  it('releases only the selected slot; FLAGGED replacement must retry the normal authenticated registration service',async()=>{
    const original=await grant();const b=await register('b');expect(b.status).toBe('FLAGGED');
    await revoke();expect((await row(b.activation_request_id)).status).toBe('FLAGGED');
    const retried=await register('b');expect(retried.status).toBe('AUTHORIZED');expect(retried.activation_request_id).toBe(b.activation_request_id);
    expect((await row()).status).toBe('REVOKED');expect(await grant()).toEqual(original);
    expect((await db.prepare("SELECT * FROM beta_activations WHERE status='AUTHORIZED'").all()).results).toHaveLength(1);
  });
  it('creates a new history entry for the same physical device without resurrecting its revoked activation',async()=>{
    await revoke();const historical=await row();const replacement=await register('a');
    expect(replacement.status).toBe('AUTHORIZED');expect(replacement.activation_request_id).not.toBe(deviceA.activation_request_id);
    expect(await row()).toEqual(historical);
    await expect(db.prepare("UPDATE beta_activations SET status='AUTHORIZED' WHERE activation_request_id=?").bind(deviceA.activation_request_id).run()).rejects.toThrow();
  });
  it('serializes identical concurrent requests to one transition/audit and one already_revoked result',async()=>{
    const responses=await Promise.all([revoke(),revoke()]);expect(responses.map((r)=>r.status)).toEqual([200,200]);
    expect((await Promise.all(responses.map((r)=>r.json()))).map((r)=>r.result).sort()).toEqual(['already_revoked','revoked']);
    expect(await events()).toHaveLength(1);
  });
  it('fails closed on a concurrent conflicting transition',async()=>{
    const batch=db.batch.bind(db);
    db.batch=async(statements)=>{await db.prepare("UPDATE beta_activations SET status='FLAGGED' WHERE activation_request_id=?").bind(deviceA.activation_request_id).run();return batch(statements);};
    expect((await revoke()).status).toBe(409);expect(await events()).toHaveLength(0);
  });
  it('rolls back revocation if the durable audit write fails',async()=>{
    db.script("CREATE TRIGGER fail_revocation_audit BEFORE INSERT ON beta_audit_events WHEN NEW.event_type='OPERATOR_DEVICE_REVOKED' BEGIN SELECT RAISE(ABORT,'test private failure'); END;");
    const response=await revoke();expect(response.status).toBe(503);expect(await response.text()).not.toContain('private');
    expect((await row()).status).toBe('AUTHORIZED');expect(await events()).toHaveLength(0);
  });
  it('recovers a lost post-commit response through an identical retry without a second audit',async()=>{
    const prepare=db.prepare.bind(db);let reads=0;
    db.prepare=(sql)=>{if(sql.startsWith('SELECT application_id, status') && ++reads===2)throw new Error('private lookup failure');return prepare(sql);};
    expect((await revoke()).status).toBe(503);expect((await row()).status).toBe('REVOKED');
    expect((await (await revoke()).json()).result).toBe('already_revoked');expect(await events()).toHaveLength(1);
  });
});

it('issues the replacement through the existing TEST signer with the original account expiry after revocation',async()=>{
  const original=await grant();const flagged=await register('b');expect(flagged.status).toBe('FLAGGED');
  await revoke();vi.setSystemTime(new Date('2027-01-21T00:00:00Z'));
  const replacement=await register('b');expect(replacement.status).toBe('AUTHORIZED');
  env.OPERATOR_SYNC_TOKEN='synthetic-read';
  const response=await exportActivations({env,request:new Request(origin+'/api/operator/activations',{headers:{Authorization:'Bearer synthetic-read'}})});
  expect(response.status).toBe(200);
  const facts=(await response.json()).activations.find((a)=>a.activation_request_id===replacement.activation_request_id);
  const code=`import sys,json,tempfile
sys.path.insert(0,'..')
from operator_tools.licence_manager.database import Database
from operator_tools.licence_manager.crypto import DataProtector
from operator_tools.licence_manager.signing import TestEphemeralAuthority
from operator_tools.licence_manager.website_sync import _parse_website_activation
from operator_tools.licence_manager.issuance import issue_website_activation_for_testing
with tempfile.TemporaryDirectory() as root:
 db=Database(root,DataProtector.for_testing(b'R'*32))
 try:
  a=_parse_website_activation(json.load(sys.stdin))
  e=issue_website_activation_for_testing(db,TestEphemeralAuthority(),a,now=int(sys.argv[1]))
  print(json.dumps({'expires_at':e['expires_at'],'issued_at':e['issued_at']}))
 finally: db.close()`;
  const venv=resolve('..','.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
  const python=process.env.QS_TEST_PYTHON || (existsSync(venv)?venv:process.platform==='win32'?'python':'python3');
  const licence=JSON.parse(execFileSync(python,['-c',code,String(Date.now()/1000)],{encoding:'utf8',input:JSON.stringify(facts)}));
  expect(licence.expires_at).toBe(Date.parse(original.expires_at)/1000);
  expect(licence.expires_at-licence.issued_at).toBe(70*86400);
  expect(await grant()).toEqual(original);expect((await row()).status).toBe('REVOKED');
});
