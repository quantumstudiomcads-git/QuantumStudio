import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {beforeEach,afterEach,it,expect,vi} from 'vitest';
import {createHash,createPrivateKey,createPublicKey,sign} from 'node:crypto';
import {mkdtempSync,readFileSync,readdirSync,unlinkSync,rmdirSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {SQLiteD1} from './helpers/sqlite-d1.mjs';
import {onRequestGet as listRoute} from '../functions/api/admin/applications.js';
import {onRequestGet as detailRoute} from '../functions/api/admin/applications/[applicationId]/index.js';
import {onRequestPost as actionRoute} from '../functions/api/admin/applications/[applicationId]/action.js';
import {onRequest as middleware} from '../functions/_middleware.js';
import {canonicalJson} from '../functions/_lib/licence-delivery.js';
import {createAdminClient,adminActionNotice,canIssue} from '../src/lib/admin-client';
import {AdminApplicationDetail} from '../src/components/AdminApplicationDetail';

vi.setConfig({testTimeout:30000});
const admin='11111111-1111-4111-8111-111111111111', user='22222222-2222-4222-8222-222222222222';
const app='12345678-1234-4123-8123-123456789abc',aid='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const session='33333333-3333-4333-8333-333333333333',raw='synthetic-session-token-only';
const origin='https://quantumstudio.pages.dev',hash='d'.repeat(64),installation='dev_'+hash.slice(0,32);
const knownSeed=Buffer.from(Array.from({length:32},(_,i)=>i));
const privateKey=createPrivateKey({key:Buffer.concat([Buffer.from('302e020100300506032b657004220420','hex'),knownSeed]),format:'der',type:'pkcs8'});
// Known unit fixture public key, independent of any real deployed identity.
const publicKey=createPublicKey(privateKey).export({format:'der',type:'spki'}).subarray(-32).toString('base64url');
const stamp=(n)=>new Date(n*1000).toISOString().replace('.000Z','Z');
let env,db,root,now;
async function approve(){
  await db.prepare("UPDATE beta_applications SET status='UNDER_REVIEW' WHERE application_id=?").bind(app).run();
  await db.prepare("UPDATE beta_applications SET status='APPROVED' WHERE application_id=?").bind(app).run();
  await db.prepare("UPDATE beta_activations SET status='AUTHORIZED' WHERE activation_request_id=?").bind(aid).run();
}
async function envelope(){
  const e=await db.prepare('SELECT * FROM account_entitlements').first();
  const p={schema_version:1,licence_id:'lic_bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',account_id:'sub_'+app,subject_type:'beta_applicant',subject_id:'sub_'+app,
    approved_application_ref:app,product:'Quantum Studio',channel:'beta',plan_id:'pro',device_id:installation,device_public_key_hash:hash,
    issued_at:now,not_before:now,expires_at:Date.parse(e.expires_at)/1000,offline_until:Date.parse(e.expires_at)/1000,
    entitlement_version:1,feature_entitlements:['builder'],calculation_entitlements:[],registered_device_limit:1,concurrent_session_limit:1,
    offline_device_limit:1,nonce:'cccccccc-cccc-4ccc-8ccc-cccccccccccc',policy_profile:'PROFESSOR_BETA',issuer_label:'Quantum Studio Licence Manager',kid:'lic-unit-fixture'};
  return {...p,signature:sign(null,Buffer.from(canonicalJson(p)),privateKey).toString('base64url')};
}
function request(path,body,headers={}){
  return new Request(origin+path,{method:body?'POST':'GET',headers:{Cookie:'qs_session='+session+'.'+raw,...(body?{'Content-Type':'application/json',Origin:origin,'X-QuantumStudio-Admin':'1'}:{}),...headers},...(body?{body:JSON.stringify(body)}:{})});
}
const list=(headers={})=>listRoute({env,request:request('/api/admin/applications',undefined,headers)});
const detail=()=>detailRoute({env,params:{applicationId:app},request:request('/api/admin/applications/'+app)});
const action=(body,headers={})=>actionRoute({env,params:{applicationId:app},request:request('/api/admin/applications/'+app+'/action',body,headers)});
const issue=()=>action({schema_version:1,action:'issue',activation_id:aid});
beforeEach(async()=>{
  now=Math.floor(Date.now()/1000);root=mkdtempSync(join(tmpdir(),'qs-admin-'));db=new SQLiteD1(join(root,'db.sqlite'));
  db.script(readdirSync('migrations').filter(p=>p.endsWith('.sql')).sort().map(p=>readFileSync(join('migrations',p),'utf8')).join('\n'));
  for(const [id,name,email] of [[admin,'Operator','admin@example.test'],[user,'Researcher','applicant@example.test']])await db.prepare(`INSERT INTO users(user_id,full_name,institution,email,normalized_email,email_lookup_hash,status,email_verified_at,created_at,updated_at) VALUES(?,?,'Institute',?,?,?,'VERIFIED',?,?,?)`).bind(id,name,email,email,id,stamp(now-60),stamp(now-60),stamp(now-60)).run();
  await db.prepare(`INSERT INTO sessions(session_id,user_id,token_hash,created_at,expires_at,last_seen_at) VALUES(?,?,?,?,?,?)`).bind(session,admin,createHash('sha256').update(raw).digest('hex'),stamp(now-60),stamp(now+3600),stamp(now-60)).run();
  await db.prepare(`INSERT INTO beta_applications(application_id,user_id,full_name,email,normalized_email,email_lookup_hash,institution,country,research_area,operating_system,privacy_consent,privacy_version,terms_consent,terms_version,communications_consent,status,submitted_at,updated_at)
    VALUES(?,?,'Researcher','applicant@example.test','applicant@example.test','hash','Institute','Test','Materials','Windows',1,'1',1,'1',0,'APPLIED',?,?)`).bind(app,user,stamp(now-60),stamp(now-60)).run();
  await db.prepare(`INSERT INTO beta_activations(activation_request_id,user_id,application_id,installation_id,platform,architecture,app_version,status,created_at,updated_at,authorized_at,device_public_key_hash) VALUES(?,?,?,?,'windows','x86_64','0.2.0','FLAGGED',?,?,?,?)`).bind(aid,user,app,installation,stamp(now-60),stamp(now-60),stamp(now-60),hash).run();
  env={BETA_ENVIRONMENT:'staging',BETA_ALLOWED_ORIGIN:origin,BETA_DB:db,QS_ADMIN_ENABLED:'true',QS_ADMIN_USER_IDS:JSON.stringify([admin]),
    AUTH_OTP_PEPPER:'synthetic-otp',BETA_IDENTITY_PEPPER:'synthetic-identity',TURNSTILE_SECRET_KEY:'synthetic-turnstile',
    OPERATOR_SYNC_TOKEN:'synthetic-read',OPERATOR_STATUS_SYNC_TOKEN:'synthetic-status',OPERATOR_LICENCE_SYNC_TOKEN:'synthetic-metadata',
    OPERATOR_LICENCE_PUBLISH_TOKEN:'synthetic-publish',OPERATOR_ACTIVATION_REVOKE_TOKEN:'synthetic-revoke',BETA_PRIVACY_VERSION:'1',BETA_TERMS_VERSION:'1',
    QS_SIGNING_SERVICE_CALLER:JSON.stringify({schema_version:1,environment:'staging',caller:'pages-staging',secret:Buffer.alloc(32,0x53).toString('base64url')}),
    QS_LICENCE_TRUST:JSON.stringify({schema_version:1,environment:'staging',domain:'licence',algorithm:'Ed25519',keys:{'lic-unit-fixture':publicKey}}),
    SIGNING_SERVICE:{fetch:vi.fn(async()=>{const e=await envelope();return new Response(JSON.stringify({schema_version:1,result:'persisted',envelope:e,envelope_sha256:createHash('sha256').update(canonicalJson(e)).digest('hex')}),{headers:{'Content-Type':'application/json'}});})}};
  vi.stubGlobal('fetch',vi.fn(()=>{throw new Error('Real network forbidden');}));
});
afterEach(()=>{vi.unstubAllGlobals();vi.restoreAllMocks();for(const name of readdirSync(root))unlinkSync(join(root,name));rmdirSync(root);});

it.each([undefined,'false','TRUE'])('is disabled unless explicitly enabled (%s)',async value=>{
  env.QS_ADMIN_ENABLED=value;expect((await list()).status).toBe(503);expect((await issue()).status).toBe(503);expect(env.SIGNING_SERVICE.fetch).not.toHaveBeenCalled();
});
it.each([undefined,'[]','["bad"]','["admin@example.test"]','{bad',JSON.stringify([admin,admin])])('fails closed for missing or invalid admin allowlist #%#',async value=>{
  env.QS_ADMIN_USER_IDS=value;expect((await list()).status).toBe(503);
});
it('denies an unauthenticated browser and an operator bearer token without an admin session',async()=>{
  expect((await list({Cookie:''})).status).toBe(401);
  expect((await list({Cookie:'',Authorization:'Bearer '+env.OPERATOR_SYNC_TOKEN})).status).toBe(401);
});
it('denies a normal authenticated user and header-based impersonation',async()=>{
  await db.prepare('UPDATE sessions SET user_id=?').bind(user).run();
  expect((await list({'X-QS-Admin-User':admin})).status).toBe(403);expect((await issue()).status).toBe(403);
});
it.each(['expired','revoked','disabled','unverified','malformed-cookie','malformed-expiry'])('denies %s admin sessions',async kind=>{
  if(kind==='expired')await db.prepare('UPDATE sessions SET expires_at=?').bind(stamp(now-1)).run();
  if(kind==='revoked')await db.prepare('UPDATE sessions SET revoked_at=?').bind(stamp(now)).run();
  if(kind==='disabled')await db.prepare("UPDATE users SET status='DISABLED' WHERE user_id=?").bind(admin).run();
  if(kind==='unverified')await db.prepare('UPDATE users SET email_verified_at=NULL WHERE user_id=?').bind(admin).run();
  if(kind==='malformed-expiry')await db.prepare("UPDATE sessions SET expires_at='not-a-date'").run();
  const r=await list(kind==='malformed-cookie'?{Cookie:'qs_session=%ZZ'}:{});expect([401,403]).toContain(r.status);
});
it('protects admin page aliases while leaving the public homepage unchanged',async()=>{
  for(const path of ['/admin','/admin/','/admin/index.html','/admin.html','/admin%2Findex.html']){
    const next=vi.fn(async()=>new Response('private shell'));const r=await middleware({env,request:request(path,undefined,{Cookie:''}),next});expect(r.status).toBe(401);expect(next).not.toHaveBeenCalled();
  }
  const next=vi.fn(async()=>new Response('public homepage'));expect(await (await middleware({env,request:request('/',undefined,{Cookie:''}),next})).text()).toBe('public homepage');
  expect(next).toHaveBeenCalledOnce();
  const page=await middleware({env,request:request('/admin'),next:async()=>new Response('admin shell')});
  expect(page.status).toBe(200);expect(page.headers.get('Cache-Control')).toContain('no-store');expect(page.headers.get('X-Robots-Tag')).toContain('noindex');
});
it.each(['staging','production'])('%s admin lists and inspects authoritative D1 application, user, entitlement and activation data',async mode=>{
  env.BETA_ENVIRONMENT=mode;await approve();const r=await list();expect(r.status).toBe(200);expect(r.headers.get('Cache-Control')).toContain('no-store');
  const data=await r.json();expect(data.applications[0]).toMatchObject({application_id:app,user_id:user,email:'applicant@example.test',status:'APPROVED'});
  const d=await (await detail()).json();expect(d.entitlement).toMatchObject({plan_id:'beta',device_limit:1,revision:1,status:'CURRENT'});
  expect(d.activations[0]).toMatchObject({activation_request_id:aid,status:'AUTHORIZED',installation_id:installation});
  const serialized=JSON.stringify(d);for(const forbidden of ['token_hash','envelope_json','secret','OPERATOR_','QS_SIGNING_'])expect(serialized).not.toContain(forbidden);
});
it('preserves the review state machine and provisions the original entitlement exactly once',async()=>{
  const review=(status,expected_status)=>action({schema_version:1,action:'review',status,expected_status});
  expect((await review('APPROVED','APPLIED')).status).toBe(409);
  expect((await review('UNDER_REVIEW','APPLIED')).status).toBe(200);
  expect((await review('APPROVED','UNDER_REVIEW')).status).toBe(200);
  const ent=await db.prepare('SELECT * FROM account_entitlements').first();
  expect((await review('APPROVED','APPROVED')).status).toBe(200);expect(await db.prepare('SELECT * FROM account_entitlements').first()).toEqual(ent);
  expect((await db.prepare("SELECT * FROM beta_audit_events WHERE event_type='OPERATOR_STATUS_SYNC'").all()).results).toHaveLength(2);
});
it('supports the existing terminal rejection transition',async()=>{
  expect((await action({schema_version:1,action:'review',status:'UNDER_REVIEW',expected_status:'APPLIED'})).status).toBe(200);
  expect((await action({schema_version:1,action:'review',status:'REJECTED',expected_status:'UNDER_REVIEW'})).status).toBe(200);
  expect((await action({schema_version:1,action:'review',status:'APPROVED',expected_status:'REJECTED'})).status).toBe(409);
});
it.each([{Origin:'https://attacker.invalid'},{Origin:''},{'X-QuantumStudio-Admin':''},{'Sec-Fetch-Site':'cross-site'},{'Content-Type':'text/plain'}])('requires same-origin JSON and the admin action header %#',async headers=>{
  expect((await action({schema_version:1,action:'issue',activation_id:aid},headers)).status).toBe(403);expect(env.SIGNING_SERVICE.fetch).not.toHaveBeenCalled();
});
it('rejects mismatched origins and HTTP',async()=>{
  for(const url of ['http://quantumstudio.pages.dev/api/admin/applications','https://another.invalid/api/admin/applications'])expect((await listRoute({env,request:new Request(url,{headers:{Cookie:'qs_session='+session+'.'+raw}})})).status).toBe(403);
});
it('issues through the existing binding implementation, updates rendered licence state and retries immutably',async()=>{
  await approve();const before=await (await detail()).json();expect(renderToStaticMarkup(React.createElement(AdminApplicationDetail,{detail:before}))).not.toContain('lic_bbbbbbbb');
  // Simulates the browser automatically sending its existing HttpOnly cookie; no operator credential in client options.
  const browser=vi.fn(async(path,options)=>{
    const headers=new Headers(options.headers);expect(headers.has('Authorization')).toBe(false);headers.set('Cookie','qs_session='+session+'.'+raw);headers.set('Origin',origin);
    const req=new Request(origin+path,{...options,headers});return actionRoute({env,request:req,params:{applicationId:app}});
  });
  const client=createAdminClient(browser);
  const issued=await client.action(app,{schema_version:1,action:'issue',activation_id:aid});
  expect(issued.result).toBe('published');expect(env.SIGNING_SERVICE.fetch).toHaveBeenCalledOnce();
  const html=renderToStaticMarkup(React.createElement(AdminApplicationDetail,{detail:issued}));
  expect(html).toContain('lic_bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb');expect(html).toContain('lic-unit-fixture');expect(html).toContain('PUBLISHED');
  expect(adminActionNotice(issued.result)).toContain('Licence issued');
  const saved=await db.prepare('SELECT * FROM published_licences').first();
  expect((await client.action(app,{schema_version:1,action:'issue',activation_id:aid})).result).toBe('already_current');
  expect(await db.prepare('SELECT * FROM published_licences').first()).toEqual(saved);
  expect(JSON.stringify(issued)).not.toContain(env.OPERATOR_LICENCE_PUBLISH_TOKEN);
});
it.each(['unapproved','expired','FLAGGED','REVOKED'])('cannot issue %s activation/application',async kind=>{
  if(kind!=='unapproved')await approve();
  if(kind==='expired')await db.prepare('UPDATE account_entitlements SET starts_at=?,expires_at=?').bind(stamp(now-7776060),stamp(now-60)).run();
  if(['FLAGGED','REVOKED'].includes(kind))await db.prepare('UPDATE beta_activations SET status=?').bind(kind).run();
  expect((await issue()).status).toBe(409);expect(env.SIGNING_SERVICE.fetch).not.toHaveBeenCalled();
});
it('rejects arbitrary licence payloads and activation IDs outside the selected application',async()=>{
  await approve();expect((await action({schema_version:1,action:'issue',activation_id:aid,envelope:{expires_at:9999999999}})).status).toBe(400);
  expect((await action({schema_version:1,action:'issue',activation_id:'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'})).status).toBe(404);expect(env.SIGNING_SERVICE.fetch).not.toHaveBeenCalled();
});
it('reuses device revocation without changing signed bytes or account entitlement',async()=>{
  await approve();expect((await issue()).status).toBe(200);const saved=await db.prepare('SELECT * FROM published_licences').first(),ent=await db.prepare('SELECT * FROM account_entitlements').first();
  const body={schema_version:1,action:'revoke',activation_id:aid,reason_code:'DEVICE_REPLACED'};
  const r=await action(body);expect(r.status).toBe(200);expect((await r.json()).activations[0]).toMatchObject({status:'REVOKED',revocation_reason_code:'DEVICE_REPLACED',licence_id:'lic_bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'});
  expect((await action(body)).status).toBe(200);expect((await issue()).status).toBe(409);
  expect(await db.prepare('SELECT * FROM published_licences').first()).toEqual(saved);expect(await db.prepare('SELECT * FROM account_entitlements').first()).toEqual(ent);
});
it('fails safely without disclosing backend/Worker diagnostics or credentials',async()=>{
  await approve();env.SIGNING_SERVICE.fetch.mockRejectedValue(new Error('secret-diagnostic '+env.OPERATOR_SYNC_TOKEN));
  const log=vi.spyOn(console,'error').mockImplementation(()=>{});const r=await issue();expect(r.status).toBe(503);expect(await r.text()).toBe('{"error":{"code":"admin_action_unavailable"}}');expect(log).not.toHaveBeenCalled();
  vi.spyOn(db,'prepare').mockImplementation(()=>{throw new Error('sensitive SQL credentials');});expect(await (await list()).text()).not.toContain('sensitive');
});
it('keeps the local TEST workflow outside the admin boundary',async()=>{
  env.BETA_ENVIRONMENT='local';expect((await list()).status).toBe(503);expect(env.SIGNING_SERVICE.fetch).not.toHaveBeenCalled();
});
it('renders hostile applicant text safely and hides ineligible issue controls',async()=>{
  await approve();const d=await (await detail()).json();d.application.full_name='<script>alert(1)</script>';
  const html=renderToStaticMarkup(React.createElement(AdminApplicationDetail,{detail:d}));expect(html).toContain('&lt;script&gt;');expect(html).not.toContain('<script>');expect(html).toContain('Issue Licence');
  d.activations[0].status='REVOKED';expect(canIssue(d,d.activations[0])).toBe(false);expect(renderToStaticMarkup(React.createElement(AdminApplicationDetail,{detail:d}))).not.toContain('Issue Licence');
});
it('ignores raw error bodies in the public admin client',async()=>{
  const response=new Response('private_key=secret-diagnostic',{status:503});const read=vi.spyOn(response,'json');
  await expect(createAdminClient(vi.fn(async()=>response)).list()).rejects.toThrow('temporarily unavailable');expect(read).not.toHaveBeenCalled();
});

it('rejects malformed application identifiers and pagination input',async()=>{
  for(const query of ['offset=-1','offset=10001','offset=1&status=APPROVED']){
    const r=await listRoute({env,request:request('/api/admin/applications?'+query)});expect(r.status).toBe(400);
  }
  const r=await detailRoute({env,params:{applicationId:'not-a-uuid'},request:request('/api/admin/applications/not-a-uuid')});expect(r.status).toBe(400);
});
