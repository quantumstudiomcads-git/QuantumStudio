import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {existsSync, mkdtempSync, readFileSync, readdirSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join, resolve} from 'node:path';
import {execFile} from 'node:child_process';
import {createServer} from 'node:http';
import {promisify} from 'node:util';
import {SQLiteD1} from './helpers/sqlite-d1.mjs';
import {onRequestGet as currentStatusRoute, onRequestPost as statusRoute} from '../functions/api/operator/applications/[applicationId]/status.js';
import {onRequestGet as exportRoute} from '../functions/api/operator/activations.js';
import {registerActivationForUser, configuredMaxActiveDevices} from '../functions/_lib/beta-activation.js';

vi.setConfig({testTimeout:30000});
const app='12345678-1234-4123-8123-123456789abc';
const origin='http://localhost:8788';
let root,db,env;
const facts=(key='a')=>({installation_id:'dev_'+key.repeat(32),device_public_key_hash:key.repeat(64),platform:'windows',architecture:'x86_64',app_version:'0.2.0'});
const approve=()=>statusRoute({env,params:{applicationId:app},request:new Request(origin+'/api/operator/applications/'+app+'/status',{
  method:'POST',headers:{Authorization:'Bearer synthetic-status','Content-Type':'application/json'},body:JSON.stringify({schema_version:1,status:'APPROVED'})})});
const register=(key='a')=>registerActivationForUser(env,'user-a',facts(key));
const grant=()=>db.prepare('SELECT * FROM account_entitlements').first();
beforeEach(()=>{
  vi.useFakeTimers({toFake:['Date']});vi.setSystemTime(new Date('2027-01-01T00:00:00Z'));
  root=mkdtempSync(join(tmpdir(),'qs-m9a-'));db=new SQLiteD1(join(root,'local.sqlite3'));
  db.script(readdirSync('migrations').filter((p)=>p.endsWith('.sql')).sort().map((p)=>readFileSync(join('migrations',p),'utf8')).join('\n'));
  db.script(`INSERT INTO users(user_id,full_name,institution,email,normalized_email,email_lookup_hash,status,created_at,updated_at)
    VALUES('user-a','Test','Test','a@example.test','a@example.test','hash','VERIFIED','2027-01-01','2027-01-01');
    INSERT INTO beta_applications(application_id,user_id,full_name,email,normalized_email,email_lookup_hash,institution,country,research_area,
      operating_system,privacy_consent,privacy_version,terms_consent,terms_version,communications_consent,status,submitted_at,updated_at)
    VALUES('${app}','user-a','Test','a@example.test','a@example.test','hash','Test','Test','Test','Windows',1,'1',1,'1',0,'UNDER_REVIEW','2027-01-01','2027-01-01');`);
  env={BETA_DB:db,BETA_ENVIRONMENT:'local',BETA_ALLOWED_ORIGIN:origin,OPERATOR_STATUS_SYNC_TOKEN:'synthetic-status',OPERATOR_SYNC_TOKEN:'synthetic-read'};
});
afterEach(()=>{vi.useRealTimers();if(root)rmSync(root,{recursive:true,force:true});});

describe('M9A approved-account entitlement with actual status endpoint and SQLite',()=>{
  it('provisions one 90-day beta entitlement and audit atomically with approval',async()=>{
    expect(await grant()).toBeNull();expect((await approve()).status).toBe(200);
    const row=await grant();
    expect(row.plan_id).toBe('beta');expect(row.device_limit).toBe(1);expect(row.revision).toBe(1);
    expect(row.starts_at).toBe('2027-01-01T00:00:00Z');expect(row.expires_at).toBe('2027-04-01T00:00:00Z');
    expect((await db.prepare("SELECT * FROM beta_audit_events WHERE event_type='ACCOUNT_ENTITLEMENT_PROVISIONED'").all()).results).toHaveLength(1);
    expect((await db.prepare("SELECT * FROM beta_audit_events WHERE event_type='OPERATOR_STATUS_SYNC'").all()).results).toHaveLength(1);
  });
  it('repeat approval and later activation never restart the entitlement clock',async()=>{
    await approve();const original=await grant();
    vi.setSystemTime(new Date('2027-02-01T00:00:00Z'));
    expect((await (await approve()).json()).result).toBe('already_current');
    expect((await (await register()).json()).activation.status).toBe('AUTHORIZED');
    expect(await grant()).toEqual(original);
    expect((await db.prepare('SELECT * FROM account_entitlements').all()).results).toHaveLength(1);
  });
  it('defaults to one device and does not let a global env override expand the grant',async()=>{
    expect(configuredMaxActiveDevices({})).toBe(1);await approve();env.BETA_MAX_ACTIVE_DEVICES='2';
    expect((await (await register('a')).json()).activation.status).toBe('AUTHORIZED');
    expect((await (await register('b')).json()).activation.status).toBe('FLAGGED');
    expect((await (await register('a')).json()).activation.status).toBe('AUTHORIZED');
  });
  it('supports a persisted entitlement device limit of two with the same schema',async()=>{
    await approve();await db.prepare('UPDATE account_entitlements SET device_limit=2').run();
    expect((await (await register('a')).json()).activation.status).toBe('AUTHORIZED');
    expect((await (await register('b')).json()).activation.status).toBe('AUTHORIZED');
    expect((await (await register('c')).json()).activation.status).toBe('FLAGGED');
  });
  it.each(['missing','expired','future'])('fails closed for a %s account entitlement',async(kind)=>{
    await approve();
    if(kind==='missing') await db.prepare('DELETE FROM account_entitlements').run();
    if(kind==='expired') vi.setSystemTime(new Date('2027-04-01T00:00:00Z'));
    if(kind==='future') vi.setSystemTime(new Date('2026-12-31T23:59:59Z'));
    const response=await register();expect(response.status).toBe(403);
    expect((await db.prepare('SELECT * FROM beta_activations').all()).results).toHaveLength(0);
  });
  it('does not encode account expiry as a device authorization-state change',async()=>{
    await approve();await register();vi.setSystemTime(new Date('2027-04-01T00:00:00Z'));
    expect((await register()).status).toBe(403);
    expect((await db.prepare('SELECT status FROM beta_activations').first()).status).toBe('AUTHORIZED');
  });
  it('keeps revoked history and gives an explicitly reauthenticated device a new activation ID',async()=>{
    await approve();const old=(await (await register()).json()).activation;
    await db.prepare("UPDATE beta_activations SET status='REVOKED',revoked_at='2027-01-01T00:00:00Z'").run();
    const current=(await (await register()).json()).activation;
    expect(current.status).toBe('AUTHORIZED');expect(current.activation_request_id).not.toBe(old.activation_request_id);
    const rows=(await db.prepare('SELECT * FROM beta_activations').all()).results;
    expect(rows).toHaveLength(2);expect(rows.find((r)=>r.activation_request_id===old.activation_request_id).status).toBe('REVOKED');
  });
  it('does not invent a new term when approval encounters ambiguous legacy licence history',async()=>{
    await db.prepare("UPDATE beta_applications SET licence_expires_at='2027-02-01T00:00:00Z'").run();
    expect((await approve()).status).toBe(409);
    expect(await grant()).toBeNull();
    expect((await register()).status).toBe(403);
  });
  it('does not provision a new term over a legacy authorized device',async()=>{
    await db.prepare(`INSERT INTO beta_activations(activation_request_id,user_id,application_id,installation_id,platform,architecture,app_version,status,created_at,updated_at)
      VALUES('legacy','user-a',?,'dev_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','windows','x86_64','0.2.0','AUTHORIZED','2026-12-01','2026-12-01')`).bind(app).run();
    expect((await approve()).status).toBe(409);
    expect(await grant()).toBeNull();
    expect((await register()).status).toBe(403);
  });
  it('exports the exact fixed public grant for the existing operator TEST issuance path',async()=>{
    await approve();await register();const row=await grant();
    const response=await exportRoute({env,request:new Request(origin+'/api/operator/activations',{headers:{Authorization:'Bearer synthetic-read'}})});
    expect(response.status).toBe(200);const payload=await response.json();
    expect(payload.activations[0].account_entitlement).toEqual(row);
    expect(JSON.stringify(payload)).not.toContain('a@example.test');
  });
});


describe('M9A status-sync post-commit response regressions',()=>{
  it('accepts D1 trigger-inclusive changes after successful approval and returns the strict client contract',async()=>{
    const batch=db.batch.bind(db);let results;
    db.batch=async(statements)=>{results=await batch(statements);return results;};
    const response=await approve();
    expect(results[0].meta.changes).toBe(3);
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({schema_version:1,application_id:app,status:'APPROVED',result:'updated'});
    expect((await db.prepare('SELECT status FROM beta_applications').first()).status).toBe('APPROVED');
    expect((await db.prepare('SELECT * FROM account_entitlements').all()).results).toHaveLength(1);
  });
  it('reconciles APPLIED through UNDER_REVIEW with parseable success responses and a single grant',async()=>{
    await db.prepare("UPDATE beta_applications SET status='APPLIED'").run();
    for(const [expected,status] of [['APPLIED','UNDER_REVIEW'],['UNDER_REVIEW','APPROVED']]){
      const response=await statusRoute({env,params:{applicationId:app},request:new Request(origin+'/api/operator/applications/'+app+'/status',{
        method:'POST',headers:{Authorization:'Bearer synthetic-status','Content-Type':'application/json','X-QuantumStudio-Expected-Status':expected},body:JSON.stringify({schema_version:1,status})})});
      expect(response.status).toBe(200);
      expect(await response.json()).toEqual({schema_version:1,application_id:app,status,result:'updated'});
    }
    expect((await db.prepare('SELECT * FROM account_entitlements').all()).results).toHaveLength(1);
    const audit=(await db.prepare("SELECT old_status,new_status FROM beta_audit_events WHERE event_type='OPERATOR_STATUS_SYNC' ORDER BY rowid").all()).results;
    expect(audit).toEqual([{old_status:'APPLIED',new_status:'UNDER_REVIEW'},{old_status:'UNDER_REVIEW',new_status:'APPROVED'}]);
  });
  it('returns already_current for an approved QA retry without changing any entitlement field',async()=>{
    expect((await approve()).status).toBe(200);const original=await grant();
    vi.setSystemTime(new Date('2027-02-01T00:00:00Z'));
    for(let i=0;i<2;i++){
      const response=await approve();expect(response.status).toBe(200);
      expect(await response.json()).toEqual({schema_version:1,application_id:app,status:'APPROVED',result:'already_current'});
      expect(await grant()).toEqual(original);
    }
    expect((await db.prepare("SELECT * FROM beta_audit_events WHERE event_type='ACCOUNT_ENTITLEMENT_PROVISIONED'").all()).results).toHaveLength(1);
    expect((await db.prepare("SELECT * FROM beta_audit_events WHERE event_type='OPERATOR_STATUS_SYNC'").all()).results).toHaveLength(1);
  });
  it('keeps a failed post-commit invariant lookup recoverable without repeating approval/provisioning',async()=>{
    const prepare=db.prepare.bind(db);let fail=true;
    db.prepare=(sql)=>{
      if(fail && sql.startsWith('SELECT a.status')) throw new Error('private helper details');
      return prepare(sql);
    };
    const response=await approve();expect(response.status).toBe(503);
    expect(await response.text()).not.toContain('private helper details');
    const original=await grant();expect(original).not.toBeNull();
    expect((await db.prepare('SELECT status FROM beta_applications').first()).status).toBe('APPROVED');
    expect((await approve()).status).toBe(503);
    expect(await grant()).toEqual(original);
    fail=false;
    const retry=await approve();expect(retry.status).toBe(200);expect((await retry.json()).result).toBe('already_current');
    expect(await grant()).toEqual(original);
    expect((await db.prepare('SELECT * FROM account_entitlements').all()).results).toHaveLength(1);
    expect((await db.prepare("SELECT * FROM beta_audit_events WHERE event_type='OPERATOR_STATUS_SYNC'").all()).results).toHaveLength(1);
  });
  it('does not turn APPROVED with a missing entitlement into fake success or a fresh grant',async()=>{
    await approve();await db.prepare('DELETE FROM account_entitlements').run();
    const response=await approve();expect(response.status).toBe(409);expect(await grant()).toBeNull();
  });
  it('does not turn zero change metadata into success even if the target state is present',async()=>{
    const batch=db.batch.bind(db);
    db.batch=async(statements)=>{const result=await batch(statements);result[0].meta.changes=0;return result;};
    const response=await statusRoute({env,params:{applicationId:app},request:new Request(origin+'/api/operator/applications/'+app+'/status',{
      method:'POST',headers:{Authorization:'Bearer synthetic-status','Content-Type':'application/json','X-QuantumStudio-Expected-Status':'UNDER_REVIEW'},body:JSON.stringify({schema_version:1,status:'APPROVED'})})});
    expect(response.status).toBe(409);
  });
});

// Exercise the existing Python reconciliation/parser against the actual JS route.
it('lets the real Licence Manager client reconcile and retry without changing the grant',async()=>{
  await db.prepare("UPDATE beta_applications SET status='APPLIED'").run();
  const transitions=[];
  const server=createServer(async(incoming,outgoing)=>{
    try {
      const chunks=[];for await(const chunk of incoming)chunks.push(chunk);
      const request=new Request(origin+incoming.url,{method:incoming.method,headers:incoming.headers,
        ...(incoming.method==='POST'?{body:Buffer.concat(chunks)}:{})});
      if(incoming.method==='POST')transitions.push(JSON.parse(Buffer.concat(chunks).toString()).status);
      const response=await (incoming.method==='GET'?currentStatusRoute:statusRoute)({env,params:{applicationId:app},request});
      outgoing.writeHead(response.status,Object.fromEntries(response.headers));outgoing.end(await response.text());
    } catch {outgoing.writeHead(500);outgoing.end();}
  });
  await new Promise((done)=>server.listen(0,'127.0.0.1',done));
  try {
    const code=`import sys
sys.path.insert(0, sys.argv[1])
from operator_tools.licence_manager.website_sync import WebsiteStatusSyncClient
class Local:
    connection = property(lambda self: self)
    def execute(self, *args): return self
    def fetchone(self): return ('APPROVED',)
client = WebsiteStatusSyncClient(sys.argv[2], 'synthetic-status', allow_http_local=True)
assert client.sync_local_application_status(Local(), sys.argv[3]).result == 'updated'
assert client.sync_local_application_status(Local(), sys.argv[3]).result == 'already_current'
print('client contract passed')`;
    const venv=resolve('..','.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
    const python=process.env.QS_TEST_PYTHON || (existsSync(venv)?venv:process.platform==='win32'?'python':'python3');
    const result=await promisify(execFile)(python,['-c',code,resolve('..'),`http://127.0.0.1:${server.address().port}`,app],
      {timeout:20000,env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'}});
    expect(result.stdout.trim()).toBe('client contract passed');
    expect(transitions).toEqual(['UNDER_REVIEW','APPROVED','APPROVED']);
    expect((await db.prepare('SELECT * FROM account_entitlements').all()).results).toHaveLength(1);
    const row=await grant();expect(row.starts_at).toBe('2027-01-01T00:00:00Z');
    expect(row.expires_at).toBe('2027-04-01T00:00:00Z');expect(row.revision).toBe(1);
  } finally {server.closeAllConnections();await new Promise((done)=>server.close(done));}
});
