import {beforeEach,afterEach,it,expect,vi} from 'vitest';
import {createPrivateKey,createPublicKey,createHash,sign} from 'node:crypto';
import {mkdtempSync,readFileSync,readdirSync,unlinkSync,rmdirSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {SQLiteD1} from './helpers/sqlite-d1.mjs';
import {canonicalJson} from '../functions/_lib/licence-delivery.js';
import {onRequestPost as challengeRoute} from '../functions/api/licence/device-challenge.js';
import {onRequestPost as retrieveRoute} from '../functions/api/licence/device-retrieve.js';
import {onRequestPost as statusChallengeRoute} from '../functions/api/licence/device-status-challenge.js';
import {onRequestPost as statusRoute} from '../functions/api/licence/device-status.js';
import {onRequestPost as publishRoute} from '../functions/api/operator/activations/[activationId]/publish.js';
import {onRequestPost as revokeRoute} from '../functions/api/operator/activations/[activationId]/revoke.js';

vi.setConfig({testTimeout:30000});
const aid='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',app='12345678-1234-4123-8123-123456789abc';
// Known fixture seed; not any deployed device or signing identity.
const key=createPrivateKey({key:Buffer.concat([Buffer.from('302e020100300506032b657004220420','hex'),Buffer.from(Array.from({length:32},(_,i)=>i))]),format:'der',type:'pkcs8'});
const pub=createPublicKey(key).export({format:'der',type:'spki'}).subarray(-32),hash=createHash('sha256').update(pub).digest('hex'),installation='dev_'+hash.slice(0,32);
const stamp=n=>new Date(n*1000).toISOString().replace('.000Z','Z');
let root,db,env,e,digest,now;
const post=(route,body,headers={})=>route({env,params:{activationId:aid},request:new Request(env.BETA_ALLOWED_ORIGIN+'/api/test',{method:'POST',headers:{'Content-Type':'application/json',...headers},body:JSON.stringify(body)})});
const challenge=()=>post(challengeRoute,{installation_id:installation,activation_request_id:aid});
const proof=m=>({challenge_id:m.challenge_id,installation_id:installation,public_key:pub.toString('base64url'),signature:sign(null,Buffer.from(canonicalJson(m)),key).toString('base64url')});
const deliveryProof=async()=>{const r=await challenge();expect(r.status).toBe(200);return proof((await r.json()).challenge);};
const statusMessage=async()=>{const r=await post(statusChallengeRoute,{installation_id:installation,licence_id:e.licence_id,envelope_sha256:digest});expect(r.status).toBe(200);return (await r.json()).challenge;};
beforeEach(async()=>{
  now=Math.floor(Date.now()/1000);root=mkdtempSync(join(tmpdir(),'qs-deployed-delivery-'));db=new SQLiteD1(join(root,'db.sqlite'));
  db.script(readdirSync('migrations').filter(x=>x.endsWith('.sql')).sort().map(x=>readFileSync(join('migrations',x),'utf8')).join('\n'));
  db.script(`INSERT INTO users(user_id,full_name,institution,email,normalized_email,email_lookup_hash,status,created_at,updated_at)
    VALUES('u','Researcher','Institute','u@example.test','u@example.test','hash','VERIFIED','${stamp(now-60)}','${stamp(now-60)}');
    INSERT INTO beta_applications(application_id,user_id,full_name,email,normalized_email,email_lookup_hash,institution,country,research_area,operating_system,privacy_consent,privacy_version,terms_consent,terms_version,communications_consent,status,submitted_at,updated_at)
    VALUES('${app}','u','Researcher','u@example.test','u@example.test','hash','Institute','Test','Materials','Windows',1,'1',1,'1',0,'APPROVED','${stamp(now-60)}','${stamp(now-60)}');`);
  const ent=await db.prepare('SELECT * FROM account_entitlements').first();
  const payload={schema_version:1,licence_id:'lic_bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',account_id:'sub_'+app,subject_id:'sub_'+app,subject_type:'beta_applicant',approved_application_ref:app,
    product:'Quantum Studio',channel:'beta',plan_id:'pro',device_id:installation,device_public_key_hash:hash,issued_at:now-2,not_before:now-2,expires_at:Date.parse(ent.expires_at)/1000,
    offline_until:Date.parse(ent.expires_at)/1000,entitlement_version:1,feature_entitlements:['builder'],calculation_entitlements:[],registered_device_limit:1,concurrent_session_limit:1,offline_device_limit:1,
    nonce:'cccccccc-cccc-4ccc-8ccc-cccccccccccc',policy_profile:'PROFESSOR_BETA',issuer_label:'Quantum Studio Licence Manager',kid:'lic-unit-fixture'};
  e={...payload,signature:sign(null,Buffer.from(canonicalJson(payload)),key).toString('base64url')};digest=createHash('sha256').update(canonicalJson(e)).digest('hex');
  await db.prepare(`INSERT INTO beta_activations(activation_request_id,user_id,application_id,installation_id,platform,architecture,app_version,status,created_at,updated_at,authorized_at,device_public_key_hash,licence_id,licence_status,licence_issued_at,licence_expires_at) VALUES(?,'u',?,?,'windows','x86_64','0.2.0','AUTHORIZED',?,?,?,?,?,'ISSUED',?,?)`).bind(aid,app,installation,stamp(now-60),stamp(now-60),stamp(now-60),hash,e.licence_id,stamp(e.issued_at),stamp(e.expires_at)).run();
  await db.prepare(`INSERT INTO published_licences(activation_request_id,licence_id,envelope_json,envelope_sha256,published_at,status) VALUES(?,?,?,?,?,'PUBLISHED')`).bind(aid,e.licence_id,canonicalJson(e),digest,now).run();
  env={BETA_ENVIRONMENT:'staging',BETA_ALLOWED_ORIGIN:'https://licensing.unit-fixture.org',BETA_DB:db,
    AUTH_OTP_PEPPER:'synthetic-otp',BETA_IDENTITY_PEPPER:'synthetic-identity',TURNSTILE_SECRET_KEY:'synthetic-turnstile',OPERATOR_SYNC_TOKEN:'synthetic-read',OPERATOR_STATUS_SYNC_TOKEN:'synthetic-status',
    OPERATOR_LICENCE_SYNC_TOKEN:'synthetic-metadata',OPERATOR_LICENCE_PUBLISH_TOKEN:'synthetic-publish',OPERATOR_ACTIVATION_REVOKE_TOKEN:'synthetic-revoke',BETA_PRIVACY_VERSION:'1',BETA_TERMS_VERSION:'1'};
  vi.stubGlobal('fetch',vi.fn(()=>{throw new Error('No private/public network allowed');}));
});
afterEach(()=>{vi.useRealTimers();vi.unstubAllGlobals();for(const name of readdirSync(root))unlinkSync(join(root,name));rmdirSync(root);});
it.each(['staging','production'])('%s retrieves exactly the published envelope with device proof and no cookies/binding/operator token',async mode=>{
  env.BETA_ENVIRONMENT=mode;const response=await post(retrieveRoute,await deliveryProof());expect(response.status).toBe(200);
  expect(await response.json()).toEqual({state:'available',envelope:e,envelope_sha256:digest});
  expect(response.headers.get('Cache-Control')).toBe('no-store');expect(fetch).not.toHaveBeenCalled();
  const m=await statusMessage();expect(await (await post(statusRoute,proof(m))).json()).toMatchObject({authorization_state:'AUTHORIZED',licence_id:e.licence_id});
});
it('still keeps the direct operator publication endpoint local-only',async()=>{
  expect((await post(publishRoute,{schema_version:1,envelope:e},{Authorization:'Bearer synthetic-publish'})).status).toBe(403);
});
it('requires proof of the existing matching private device key and rejects replay',async()=>{
  const p=await deliveryProof();expect((await post(retrieveRoute,{...p,signature:Buffer.alloc(64).toString('base64url')})).status).toBe(403);
  expect((await post(retrieveRoute,p)).status).toBe(200);expect((await post(retrieveRoute,p)).status).toBe(409);
});
it('returns pending only after valid proof when no licence has been published',async()=>{
  await db.prepare('DELETE FROM published_licences').run();await db.prepare('UPDATE beta_activations SET licence_id=NULL,licence_status=NULL,licence_issued_at=NULL,licence_expires_at=NULL').run();
  expect(await (await post(retrieveRoute,await deliveryProof())).json()).toEqual({state:'pending'});
});
it.each(['application','entitlement','licence-revoked','device-limit','test-issuer','account','corrupt-artifact','disabled-user'])('rejects deployed %s state at retrieval and status',async kind=>{
  const p=await deliveryProof(),m=await statusMessage();
  if(kind==='application')await db.prepare("UPDATE beta_applications SET status='REVOKED'").run();
  if(kind==='entitlement')await db.prepare('DELETE FROM account_entitlements').run();
  if(kind==='licence-revoked')await db.prepare('UPDATE beta_activations SET licence_revoked_at=?').bind(stamp(now)).run();
  if(kind==='device-limit')await db.prepare('UPDATE account_entitlements SET device_limit=2').run();
  if(kind==='disabled-user')await db.prepare("UPDATE users SET status='DISABLED'").run();
  if(['test-issuer','account','corrupt-artifact'].includes(kind)){
    const changed={...e};if(kind==='test-issuer')changed.kid='test-lic-fixture';if(kind==='account')changed.account_id='sub_wrong';
    const json=kind==='corrupt-artifact'?'{bad':canonicalJson(changed);
    // Keep the old immutable digest: even an unauthorized storage mutation cannot authenticate a cached grant.
    await db.prepare('UPDATE published_licences SET envelope_json=?').bind(json).run();
  }
  expect((await post(retrieveRoute,p)).status).toBe(409);expect((await post(statusRoute,proof(m))).status).toBe(409);
});
it('rejects account mismatch even if a corrupted artifact digest is also replaced',async()=>{
  const p=await deliveryProof();const changed=canonicalJson({...e,account_id:'sub_wrong'});
  await db.prepare('UPDATE published_licences SET envelope_json=?,envelope_sha256=?').bind(changed,createHash('sha256').update(changed).digest('hex')).run();
  expect((await post(retrieveRoute,p)).status).toBe(409);
});
it('detects a revocation racing delivery and returns the terminal status without altering the signed envelope',async()=>{
  const p=await deliveryProof(),m=await statusMessage();
  expect((await post(revokeRoute,{schema_version:1,expected_status:'AUTHORIZED',reason_code:'DEVICE_REPLACED'},{Authorization:'Bearer synthetic-revoke'})).status).toBe(200);
  expect((await post(retrieveRoute,p)).status).toBe(403);
  expect(await (await post(statusRoute,proof(m))).json()).toMatchObject({authorization_state:'REVOKED',authorization_revision:2,reason_code:'DEVICE_REPLACED'});
  expect((await db.prepare('SELECT envelope_json FROM published_licences').first()).envelope_json).toBe(canonicalJson(e));
});
it('returns authenticated expiry for existing grants and refuses expired retrieval',async()=>{
  vi.useFakeTimers({toFake:['Date']});vi.setSystemTime(new Date(e.expires_at*1000));
  expect((await challenge()).status).toBe(409);
  const m=await statusMessage(),r=await post(statusRoute,proof(m));expect(r.status).toBe(200);
  expect((await r.json()).server_time).toBe(e.expires_at);
});
it('deployed retrieval requires valid runtime configuration and HTTPS',async()=>{
  env.BETA_ALLOWED_ORIGIN='http://localhost:8788';expect([403,503]).toContain((await challenge()).status);
  env.BETA_ALLOWED_ORIGIN='https://licensing.unit-fixture.org';delete env.AUTH_OTP_PEPPER;expect((await challenge()).status).toBe(503);
});
