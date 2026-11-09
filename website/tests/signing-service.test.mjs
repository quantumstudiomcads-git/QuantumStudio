import {beforeEach,afterEach,it,expect,vi} from 'vitest';
import {createPrivateKey,createPublicKey,createHash,sign} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {mkdtempSync,readFileSync,readdirSync,unlinkSync,rmdirSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {SQLiteD1} from './helpers/sqlite-d1.mjs';
import {canonicalJson} from '../functions/_lib/licence-delivery.js';
import {issueLicenceViaService,signingServiceHeaders,SIGNING_REQUEST_TIMEOUT_MS} from '../functions/_lib/signing-service.js';
import {onRequestPost as issueRoute} from '../functions/api/operator/activations/[activationId]/issue.js';

vi.setConfig({testTimeout:30000});
const aid='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', app='12345678-1234-4123-8123-123456789abc';
const token='synthetic-publish-token', secret=Buffer.from(Array.from({length:32},(_,i)=>i+32));
const caller={schema_version:1,environment:'staging',caller:'pages-staging',secret:secret.toString('base64url')};
// Publicly known unit seed, never a staging identity or deployable secret.
const privateKey=createPrivateKey({key:Buffer.concat([Buffer.from('302e020100300506032b657004220420','hex'),Buffer.from(Array.from({length:32},(_,i)=>i))]),format:'der',type:'pkcs8'});
const publicKey=createPublicKey(privateKey).export({format:'der',type:'spki'}).subarray(-32).toString('base64url');
const kid='lic-unit-fixture', hash='d'.repeat(64), installation='dev_'+hash.slice(0,32);
const stamp=n=>new Date(n*1000).toISOString().replace('.000Z','Z');
const python=resolve('..','.venv','Scripts','python.exe');
let root,db,env,envelope,now;
const resign=e=>{const {signature,...payload}=e;return {...payload,signature:sign(null,Buffer.from(canonicalJson(payload)),privateKey).toString('base64url')};};
const response=e=>new Response(JSON.stringify({schema_version:1,result:'persisted',envelope_sha256:createHash('sha256').update(canonicalJson(e)).digest('hex'),envelope:e}),{headers:{'Content-Type':'application/json'}});
const call=(body={schema_version:1},auth=token)=>issueRoute({env,params:{activationId:aid},request:new Request('https://quantumstudio.pages.dev/api/operator/activations/'+aid+'/issue',{method:'POST',headers:{'Content-Type':'application/json',...(auth?{Authorization:'Bearer '+auth}:{})},body:JSON.stringify(body)})});
beforeEach(async()=>{
  now=Math.floor(Date.now()/1000);
  root=mkdtempSync(join(tmpdir(),'qs-pages-signing-'));db=new SQLiteD1(join(root,'test.sqlite'));
  db.script(readdirSync('migrations').filter(x=>x.endsWith('.sql')).sort().map(x=>readFileSync(join('migrations',x),'utf8')).join('\n'));
  db.script(`INSERT INTO users(user_id,full_name,institution,email,normalized_email,email_lookup_hash,status,created_at,updated_at)
    VALUES('u','Researcher','Institute','u@example.test','u@example.test','hash','VERIFIED','${stamp(now-60)}','${stamp(now-60)}');
    INSERT INTO beta_applications(application_id,full_name,email,normalized_email,email_lookup_hash,institution,country,research_area,
    operating_system,privacy_consent,privacy_version,terms_consent,terms_version,communications_consent,status,submitted_at,updated_at,user_id)
    VALUES('${app}','Researcher','u@example.test','u@example.test','hash','Institute','Test','Materials','Windows',1,'1',1,'1',0,'APPROVED','${stamp(now-60)}','${stamp(now-60)}','u');`);
  await db.prepare(`INSERT INTO beta_activations(activation_request_id,user_id,application_id,installation_id,platform,architecture,app_version,
    status,created_at,updated_at,authorized_at,device_public_key_hash) VALUES(?,'u',?,?,'windows','x86_64','0.2.0','AUTHORIZED',?,?,?,?)`).bind(aid,app,installation,stamp(now-60),stamp(now-60),stamp(now-60),hash).run();
  const ent=await db.prepare('SELECT * FROM account_entitlements').first();
  envelope=resign({schema_version:1,licence_id:'lic_bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',account_id:'sub_'+app,subject_type:'beta_applicant',subject_id:'sub_'+app,
    approved_application_ref:app,product:'Quantum Studio',channel:'beta',plan_id:'pro',device_id:installation,device_public_key_hash:hash,
    issued_at:now-2,not_before:now-2,expires_at:Date.parse(ent.expires_at)/1000,offline_until:Date.parse(ent.expires_at)/1000,
    entitlement_version:1,feature_entitlements:['builder'],calculation_entitlements:[],registered_device_limit:1,concurrent_session_limit:1,
    offline_device_limit:1,nonce:'cccccccc-cccc-4ccc-8ccc-cccccccccccc',policy_profile:'PROFESSOR_BETA',issuer_label:'Quantum Studio Licence Manager',kid});
  env={BETA_ENVIRONMENT:'staging',BETA_ALLOWED_ORIGIN:'https://quantumstudio.pages.dev',BETA_DB:db,
    AUTH_OTP_PEPPER:'synthetic-otp',BETA_IDENTITY_PEPPER:'synthetic-identity',TURNSTILE_SECRET_KEY:'synthetic-turnstile',
    OPERATOR_SYNC_TOKEN:'synthetic-read',OPERATOR_STATUS_SYNC_TOKEN:'synthetic-status',OPERATOR_LICENCE_SYNC_TOKEN:'synthetic-metadata',
    OPERATOR_LICENCE_PUBLISH_TOKEN:token,OPERATOR_ACTIVATION_REVOKE_TOKEN:'synthetic-revoke',BETA_PRIVACY_VERSION:'1',BETA_TERMS_VERSION:'1',
    QS_SIGNING_SERVICE_CALLER:JSON.stringify(caller),QS_LICENCE_TRUST:JSON.stringify({schema_version:1,environment:'staging',domain:'licence',algorithm:'Ed25519',keys:{[kid]:publicKey}}),
    SIGNING_SERVICE:{fetch:vi.fn(async()=>response(envelope))}};
  vi.stubGlobal('fetch',vi.fn(()=>{throw new Error('Public fetch forbidden');}));
});
afterEach(()=>{vi.useRealTimers();vi.unstubAllGlobals();vi.restoreAllMocks();for(const name of readdirSync(root))unlinkSync(join(root,name));rmdirSync(root);});

it.each(['staging','production'])('%s uses the private binding, publishes exactly once and retries immutably',async mode=>{
  env.BETA_ENVIRONMENT=mode;env.QS_SIGNING_SERVICE_CALLER=JSON.stringify({...caller,environment:mode});
  env.QS_LICENCE_TRUST=JSON.stringify({...JSON.parse(env.QS_LICENCE_TRUST),environment:mode});
  expect((await call()).status).toBe(200);
  const saved=await db.prepare('SELECT * FROM published_licences').first();
  expect(saved.envelope_json).toBe(canonicalJson(envelope));
  expect(await (await call()).json()).toMatchObject({result:'already_current',envelope_sha256:saved.envelope_sha256});
  expect(await db.prepare('SELECT * FROM published_licences').first()).toEqual(saved);
  const req=env.SIGNING_SERVICE.fetch.mock.calls[0][0];
  expect(req.url).toBe('https://private-signing.internal/v1/licences/issue');
  expect(JSON.parse(await req.text())).toEqual({schema_version:1,activation_request_id:aid});
  expect(req.headers.get('X-QS-Nonce')).not.toBe(env.SIGNING_SERVICE.fetch.mock.calls[1][0].headers.get('X-QS-Nonce'));
  expect(fetch).not.toHaveBeenCalled();
});
it('matches the existing Python HMAC authenticator and RuntimeEd25519Signer/LeaseVerifier',async()=>{
  const body=canonicalJson({schema_version:1,activation_request_id:aid});
  const headers=await signingServiceHeaders('staging',caller,body,now,'a'.repeat(64));
  const code=`import sys,json
sys.path.insert(0,'..')
from backend.licensing.configuration import Environment
from operator_tools.licence_manager.signing_service_auth import HmacServiceAuthenticator
from operator_tools.licence_manager.signing_runtime import RuntimeEd25519Signer
from tests.licensing.test_production_signing import configuration
from backend.licensing.models import DeviceIdentity
from backend.licensing.verifier import LeaseVerifier
v=json.load(sys.stdin)
a=HmacServiceAuthenticator(Environment.STAGING,json.dumps({'schema_version':1,'environment':'staging','callers':{v['caller']['caller']:v['caller']['secret']}}))
a.authenticate({k.lower():val for k,val in v['headers'].items()},v['body'].encode(),v['now'])
s=RuntimeEd25519Signer(configuration('staging'),bind_environment=True)
p=v['payload']; p.pop('signature'); p.pop('kid')
e=s.sign_licence(p)
LeaseVerifier({s.kid:s.public_key}).verify(e,DeviceIdentity(p['device_id'],b'',p['device_public_key_hash']))
print(json.dumps(e))`;
  const signed=JSON.parse(execFileSync(python,['-B','-c',code],{encoding:'utf8',input:JSON.stringify({caller,headers,body,now,payload:envelope})}));
  expect(signed).toEqual(envelope);
});
it('local mode keeps the TEST worker flow without a binding',async()=>{
  env.BETA_ENVIRONMENT='local';delete env.SIGNING_SERVICE;delete env.QS_SIGNING_SERVICE_CALLER;
  expect(await (await issueLicenceViaService(env,aid)).json()).toEqual({error:{code:'local_worker_required'}});
});
it.each(['SIGNING_SERVICE','QS_SIGNING_SERVICE_CALLER','QS_LICENCE_TRUST'])('missing %s fails closed',async name=>{
  delete env[name];expect((await call()).status).toBe(503);expect(await db.prepare('SELECT * FROM published_licences').first()).toBeNull();
});
it.each(['{bad',JSON.stringify({...caller,environment:'production'}),JSON.stringify({...caller,secret:'short'}),JSON.stringify({...caller,caller:'bad caller'}),JSON.stringify({...caller,extra:'x'})])('invalid caller config fails closed #%#',async config=>{
  env.QS_SIGNING_SERVICE_CALLER=config;expect((await call()).status).toBe(503);expect(env.SIGNING_SERVICE.fetch).not.toHaveBeenCalled();
});
it.each([401,403,409,500,503])('contains service auth/replay/unavailable HTTP %s diagnostics',async status=>{
  const logs=vi.spyOn(console,'error').mockImplementation(()=>{});
  env.SIGNING_SERVICE.fetch.mockResolvedValue(new Response(JSON.stringify({secret:caller.secret,error:'internal-secret-diagnostic'}),{status}));
  const r=await call();expect(r.status).toBe(status===409?409:503);
  expect(await r.text()).not.toMatch(/internal-secret|secret|pages-staging/);expect(logs).not.toHaveBeenCalled();
  expect(await db.prepare('SELECT * FROM published_licences').first()).toBeNull();
});
it('contains transport exceptions',async()=>{
  env.SIGNING_SERVICE.fetch.mockRejectedValue(new Error(caller.secret));
  expect(await (await call()).json()).toEqual({error:{code:'signing_temporarily_unavailable'}});
});
it('bounds a hanging private service call',async()=>{
  vi.useFakeTimers();env.SIGNING_SERVICE.fetch.mockImplementation(()=>new Promise(()=>{}));
  const pending=call();await vi.waitFor(()=>expect(env.SIGNING_SERVICE.fetch).toHaveBeenCalled());
  await vi.advanceTimersByTimeAsync(SIGNING_REQUEST_TIMEOUT_MS+1);
  expect((await pending).status).toBe(503);
});
it.each(['signature','device','expiry','issuer','digest','schema','extra','json'])('rejects malformed/mismatched worker %s',async kind=>{
  let e={...envelope},r;
  if(kind==='signature')e.signature='a'.repeat(86);
  if(kind==='device')e=resign({...e,device_public_key_hash:'e'.repeat(64),device_id:'dev_'+'e'.repeat(32)});
  if(kind==='expiry')e=resign({...e,expires_at:e.expires_at-1,offline_until:e.expires_at-1});
  if(kind==='issuer')e=resign({...e,kid:'lic-untrusted'});
  r=response(e);
  if(['digest','schema','extra'].includes(kind)){
    const b=await r.json();if(kind==='digest')b.envelope_sha256='0'.repeat(64);if(kind==='schema')b.schema_version=2;if(kind==='extra')b.private_key='never-persist';
    r=new Response(JSON.stringify(b),{headers:{'Content-Type':'application/json'}});
  }
  if(kind==='json')r=new Response('{bad',{headers:{'Content-Type':'application/json'}});
  env.SIGNING_SERVICE.fetch.mockResolvedValue(r);expect((await call()).status).toBe(502);
  expect(await db.prepare('SELECT * FROM published_licences').first()).toBeNull();
});
it.each(['REVOKED','FLAGGED','expired','device','metadata','application'])('rejects ineligible %s before calling worker',async kind=>{
  if(['REVOKED','FLAGGED'].includes(kind))await db.prepare('UPDATE beta_activations SET status=?').bind(kind).run();
  if(kind==='expired')await db.prepare('UPDATE account_entitlements SET starts_at=?,expires_at=?').bind(stamp(now-7776060),stamp(now-60)).run();
  if(kind==='device')await db.prepare('UPDATE beta_activations SET device_public_key_hash=NULL').run();
  if(kind==='metadata')await db.prepare("UPDATE beta_activations SET licence_status='ISSUED'").run();
  if(kind==='application')await db.prepare("UPDATE beta_applications SET status='REVOKED'").run();
  expect((await call()).status).toBe(409);expect(env.SIGNING_SERVICE.fetch).not.toHaveBeenCalled();
});
it('rejects a concurrent revocation before metadata/publication',async()=>{
  env.SIGNING_SERVICE.fetch.mockImplementation(async()=>{await db.prepare("UPDATE beta_activations SET status='REVOKED'").run();return response(envelope);});
  expect((await call()).status).toBe(409);expect(await db.prepare('SELECT * FROM published_licences').first()).toBeNull();
});
it('resumes after metadata persisted but publication failed',async()=>{
  const prepare=db.prepare.bind(db);let failOnce=true;
  vi.spyOn(db,'prepare').mockImplementation(sql=>{if(failOnce&&sql.includes('INSERT INTO published_licences')){failOnce=false;throw new Error('fixture interruption');}return prepare(sql);});
  expect((await call()).status).toBe(503);expect((await db.prepare('SELECT licence_id FROM beta_activations').first()).licence_id).toBe(envelope.licence_id);
  expect((await call()).status).toBe(200);
});
it('rejects a different signed envelope after publication',async()=>{
  expect((await call()).status).toBe(200);
  env.SIGNING_SERVICE.fetch.mockImplementation(async()=>response(resign({...envelope,nonce:'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee'})));
  expect((await call()).status).toBe(409);expect((await db.prepare('SELECT envelope_json FROM published_licences').first()).envelope_json).toBe(canonicalJson(envelope));
});
it('browser/session callers cannot request arbitrary payloads or bypass operator authentication',async()=>{
  expect((await call({schema_version:1},null)).status).toBe(401);
  expect((await call({schema_version:1},'wrong')).status).toBe(401);
  expect((await call({schema_version:1,envelope})).status).toBe(400);
  expect((await call({schema_version:1,activation_request_id:aid})).status).toBe(400);
  expect(env.SIGNING_SERVICE.fetch).not.toHaveBeenCalled();
});

it('rejects entitlement changes while the private call is in flight',async()=>{
  env.SIGNING_SERVICE.fetch.mockImplementation(async()=>{await db.prepare('UPDATE account_entitlements SET revision=revision+1').run();return response(envelope);});
  expect((await call()).status).toBe(409);expect(await db.prepare('SELECT * FROM published_licences').first()).toBeNull();
});
it.each(['environment','test-issuer','key'])('rejects mismatched or malformed public trust: %s',async kind=>{
  const t=JSON.parse(env.QS_LICENCE_TRUST);
  if(kind==='environment')t.environment='production';
  if(kind==='test-issuer')t.keys={'test-lic-fixture':publicKey};
  if(kind==='key')t.keys={[kid]:'not-a-public-key'};
  env.QS_LICENCE_TRUST=JSON.stringify(t);expect((await call()).status).toBe(503);expect(env.SIGNING_SERVICE.fetch).not.toHaveBeenCalled();
});
it('does not return the caller credential or envelope in a successful operator response',async()=>{
  const r=await call();expect(r.status).toBe(200);const text=await r.text();
  expect(text).not.toContain(caller.secret);expect(text).not.toContain('envelope"');expect(text).not.toContain('device_public_key_hash');
});
it('rejects non-JSON and oversized private responses',async()=>{
  env.SIGNING_SERVICE.fetch.mockResolvedValueOnce(new Response(JSON.stringify(envelope),{headers:{'Content-Type':'text/plain'}}));
  expect((await call()).status).toBe(502);
  env.SIGNING_SERVICE.fetch.mockResolvedValueOnce(new Response('x'.repeat(65537),{headers:{'Content-Type':'application/json'}}));
  expect((await call()).status).toBe(502);
});
