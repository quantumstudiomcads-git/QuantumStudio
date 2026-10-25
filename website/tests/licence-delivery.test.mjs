import {afterEach, beforeEach, beforeAll, describe, expect, it, vi} from 'vitest';
import {generateKeyPairSync, createHash, sign} from 'node:crypto';
import {execFile, execFileSync} from 'node:child_process';
import {promisify} from 'node:util';
import {createServer} from 'node:http';
import {onRequestPost as statusChallengeRoute} from '../functions/api/licence/device-status-challenge.js';
import {onRequestPost as statusProofRoute} from '../functions/api/licence/device-status.js';
import {existsSync, mkdtempSync, readFileSync, readdirSync, rmSync} from 'node:fs';
import {resolve, join} from 'node:path';
import {tmpdir} from 'node:os';
import {SQLiteD1} from './helpers/sqlite-d1.mjs';
import {canonicalJson} from '../functions/_lib/licence-delivery.js';
import {onRequestPost as revokeRoute} from '../functions/api/operator/activations/[activationId]/revoke.js';
import {onRequestPost as publishRoute} from '../functions/api/operator/activations/[activationId]/publish.js';
import {onRequestPost as challengeRoute} from '../functions/api/licence/device-challenge.js';
import {onRequestPost as retrieveRoute} from '../functions/api/licence/device-retrieve.js';

vi.setConfig({testTimeout:30000});
const activation = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const app = '12345678-1234-4123-8123-123456789abc';
const token = 'synthetic-publication-token';
const pair = generateKeyPairSync('ed25519');
const publicKey = pair.publicKey.export({format:'der',type:'spki'}).subarray(-32);
const digest = createHash('sha256').update(publicKey).digest('hex');
const installation = `dev_${digest.slice(0,32)}`;
let envelope, expectedHash, issuerPublic, root, db, env;
const pythonPath = resolve('..','.venv',process.platform === 'win32' ? 'Scripts/python.exe':'bin/python');
const python = process.env.QS_TEST_PYTHON || (existsSync(pythonPath) ? pythonPath : process.platform === 'win32' ? 'python':'python3');
beforeAll(() => {
  // This is the real M5 issuance implementation, not a second fixture licence format.
  const script = `import sys,json,tempfile,hashlib
sys.path.insert(0,'..')
from operator_tools.licence_manager.database import Database
from operator_tools.licence_manager.crypto import DataProtector
from operator_tools.licence_manager.signing import TestEphemeralAuthority
from operator_tools.licence_manager.issuance import issue_website_activation_for_testing
from operator_tools.licence_manager.website_sync import WebsiteActivation
from backend.licensing.canonical import canonical_json
from datetime import datetime,timezone
from tests.helpers.licensing import beta_entitlement
with tempfile.TemporaryDirectory() as root:
 db=Database(root,DataProtector.for_testing(b'T'*32))
 facts=json.load(sys.stdin)
 a=WebsiteActivation(activation_request_id=facts['activation'],application_id=facts['app'],installation_id=facts['installation'],device_public_key_hash=facts['hash'],platform='windows',architecture='x86_64',app_version='0.2.0',status='AUTHORIZED',flag_reason=None,created_at='2026-10-20T12:00:00Z',updated_at='2026-10-20T12:00:00Z',authorized_at='2026-10-20T12:00:00Z',revoked_at=None,account_entitlement=beta_entitlement())
 issuer=TestEphemeralAuthority()
 e=issue_website_activation_for_testing(db,issuer,a,now=int(datetime(2026,10,20,12,tzinfo=timezone.utc).timestamp()))
 print(json.dumps({'envelope':e,'sha':hashlib.sha256(canonical_json(e)).hexdigest(),'issuer_public':issuer.public_key.hex()})); db.close()`;
  const result = JSON.parse(execFileSync(python,['-c',script],{encoding:'utf8',input:JSON.stringify({activation,app,installation,hash:digest})}));
  envelope = result.envelope; expectedHash=result.sha;issuerPublic=result.issuer_public;
});
beforeEach(async () => {
  vi.useFakeTimers({toFake:['Date']}); vi.setSystemTime(new Date('2026-10-20T12:00:00Z'));
  root=mkdtempSync(join(tmpdir(),'qs-m7-'));
  db=new SQLiteD1(join(root,'local.sqlite3'));
  db.script(readdirSync('migrations').filter((p)=>p.endsWith('.sql')).sort().map((p)=>readFileSync(join('migrations',p),'utf8')).join('\n'));
  db.script(`INSERT INTO users(user_id,full_name,institution,email,normalized_email,email_lookup_hash,status,created_at,updated_at)
    VALUES('user-a','Researcher','Institute','a@example.test','a@example.test','hash','VERIFIED','2026-10-20','2026-10-20');
    INSERT INTO beta_applications(application_id,full_name,email,normalized_email,email_lookup_hash,institution,country,research_area,
    operating_system,privacy_consent,privacy_version,terms_consent,terms_version,communications_consent,status,submitted_at,updated_at,user_id)
    VALUES('${app}','Researcher','a@example.test','a@example.test','hash','Institute','Test','Materials','Windows',1,'1',1,'1',0,'APPROVED','2026-10-20','2026-10-20','user-a');`);
  await db.prepare(`INSERT INTO beta_activations(activation_request_id,user_id,application_id,installation_id,platform,architecture,app_version,
    status,created_at,updated_at,device_public_key_hash,licence_id,licence_status) VALUES(?,?,?,?,'windows','x86_64','0.2.0','AUTHORIZED','2026-10-20','2026-10-20',?,?,'ISSUED')`).bind(activation,'user-a',app,installation,digest,envelope.licence_id).run();
  env={BETA_DB:db,BETA_ENVIRONMENT:'local',BETA_ALLOWED_ORIGIN:'http://localhost:8788',BETA_IDENTITY_PEPPER:'synthetic-pepper',OPERATOR_LICENCE_PUBLISH_TOKEN:token};
});
afterEach(()=>{vi.useRealTimers();if(root)rmSync(root,{recursive:true,force:true});});
function post(route,body,bearer=null,extra={}) {
  return route({env,params:{activationId:activation},request:new Request('http://localhost:8788/api/test',{
    method:'POST',headers:{'Content-Type':'application/json',...(bearer ? {Authorization:`Bearer ${bearer}`} : {}),...extra},body:JSON.stringify(body)})});
}
const publish=(e=envelope,bearer=token)=>post(publishRoute,{schema_version:1,envelope:e},bearer);
const challenge=()=>post(challengeRoute,{installation_id:installation});
function proof(message,key=pair.privateKey,pub=publicKey) {
  return {challenge_id:message.challenge_id,installation_id:installation,public_key:pub.toString('base64url'),
    signature:sign(null,Buffer.from(canonicalJson(message)),key).toString('base64url')};
}
async function makeProof() { return proof((await (await challenge()).json()).challenge); }

describe('M7 immutable signed licence publication and real device proof',()=>{
  it('publishes a real M5 envelope, agrees with Python canonical SHA, and is idempotent',async()=>{
    const first=await publish(); expect(first.status).toBe(200);
    expect(await first.json()).toEqual({schema_version:1,result:'published',envelope_sha256:expectedHash});
    const row=await db.prepare('SELECT * FROM published_licences').first();
    vi.setSystemTime(Date.now()+1000);
    expect(await (await publish()).json()).toMatchObject({result:'already_current'});
    expect(await db.prepare('SELECT * FROM published_licences').first()).toEqual(row);
  });
  it('requires the separate publication credential',async()=>{
    expect((await publish(envelope,null)).status).toBe(401);
    expect((await publish(envelope,'read-token')).status).toBe(403);
    expect((await publish(envelope,'metadata-token')).status).toBe(403);
    env.OPERATOR_LICENCE_PUBLISH_TOKEN=''; expect((await publish()).status).toBe(503);
  });
  it('rejects conflicting envelopes without overwriting the original artifact',async()=>{
    await publish();
    const changed={...envelope,nonce:'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'};
    expect((await publish(changed)).status).toBe(409);
    expect((await db.prepare('SELECT envelope_sha256 FROM published_licences').first()).envelope_sha256).toBe(expectedHash);
  });
  it.each(['private_key','seed','protected_data','email'])('never accepts publication field %s',async(field)=>{
    const response=await publish({...envelope,[field]:'must-not-publish'});
    expect(response.status).toBe(400);
    expect(await response.json()).toEqual({error:{code:'invalid_envelope'}});
    expect((await db.prepare('SELECT * FROM published_licences').all()).results).toHaveLength(0);
  });
  it('requires current matching M5 metadata and authorized device binding',async()=>{
    await db.prepare('UPDATE beta_activations SET licence_id = NULL').run();
    expect((await publish()).status).toBe(409);
    await db.prepare("UPDATE beta_activations SET status = 'FLAGGED'").run();
    expect((await publish()).status).toBe(403);
  });
  it('creates random expiring domain-bound device challenges and returns pending only after valid proof',async()=>{
    const one=(await (await challenge()).json()).challenge;
    const two=(await (await challenge()).json()).challenge;
    expect(one.challenge_id).toMatch(/^[0-9a-f]{64}$/);expect(one.challenge_id).not.toBe(two.challenge_id);
    expect(one.nonce).not.toBe(two.nonce);
    expect(one.purpose).toBe('quantum-studio:licence-retrieve:v1');
    expect(one.expires_at).toBe(Math.floor(Date.now()/1000)+120);
    expect(await (await post(retrieveRoute,proof(one))).json()).toEqual({state:'pending'});
    expect((await post(retrieveRoute,proof(one))).status).toBe(409);
  });
  it('returns only the exact device envelope, safely repeatable with fresh proofs and no cookies',async()=>{
    await publish();
    for(let n=0;n<2;n++) {
      const response=await post(retrieveRoute,await makeProof());
      expect(response.status).toBe(200);expect(response.headers.get('Cache-Control')).toBe('no-store');
      const body=await response.json();
      expect(body).toEqual({state:'available',envelope,envelope_sha256:expectedHash});
      expect(JSON.stringify(body)).not.toContain('a@example.test');
      expect(body).not.toHaveProperty('public_key');
    }
    expect((await db.prepare('SELECT * FROM published_licences').all()).results).toHaveLength(1);
  });
  it('rejects wrong private/public keys, hash mismatches and device substitution',async()=>{
    await publish();
    const message=(await (await challenge()).json()).challenge;
    const wrong=generateKeyPairSync('ed25519');
    expect((await post(retrieveRoute,proof(message,wrong.privateKey))).status).toBe(403);
    const otherPub=wrong.publicKey.export({format:'der',type:'spki'}).subarray(-32);
    expect((await post(retrieveRoute,proof(message,wrong.privateKey,otherPub))).status).toBe(403);
    expect((await post(retrieveRoute,{...proof(message),installation_id:`dev_${'b'.repeat(32)}`})).status).toBe(403);
    expect((await post(retrieveRoute,{...proof(message),signature:'invalid'})).status).toBe(400);
  });
  it('rejects expired and replayed proofs',async()=>{
    const body=await makeProof(); vi.setSystemTime(Date.now()+120000);
    expect((await post(retrieveRoute,body)).status).toBe(409);
    const fresh=await makeProof();expect((await post(retrieveRoute,fresh)).status).toBe(200);
    expect((await post(retrieveRoute,fresh)).status).toBe(409);
  });
  it('rechecks revocation after challenge issuance',async()=>{
    await publish();const body=await makeProof();
    await db.prepare("UPDATE beta_activations SET status = 'REVOKED'").run();
    expect((await post(retrieveRoute,body)).status).toBe(403);
    expect((await challenge()).status).toBe(403);
  });
  it('rejects unknown and flagged installations and unauthenticated activation-ID-only download',async()=>{
    expect((await post(challengeRoute,{installation_id:`dev_${'b'.repeat(32)}`})).status).toBe(403);
    await db.prepare("UPDATE beta_activations SET status = 'FLAGGED'").run();
    expect((await challenge()).status).toBe(403);
    expect((await post(retrieveRoute,{activation_request_id:activation})).status).toBe(400);
  });
  it('checks immutable licence ID and artifact digest on retrieval',async()=>{
    await publish();
    await db.prepare("UPDATE beta_activations SET licence_id = 'different'").run();
    expect((await post(retrieveRoute,await makeProof())).status).toBe(409);
    await db.prepare('UPDATE beta_activations SET licence_id = ?').bind(envelope.licence_id).run();
    await db.prepare("UPDATE published_licences SET envelope_sha256 = 'wrong'").run();
    expect((await post(retrieveRoute,await makeProof())).status).toBe(409);
  });
  it('consumes a valid challenge once under concurrent retrieval',async()=>{
    await publish();const body=await makeProof();
    const results=await Promise.all([post(retrieveRoute,body),post(retrieveRoute,body)]);
    expect(results.map((r)=>r.status).sort()).toEqual([200,409]);
  });
  it('rate-limits device challenge requests',async()=>{
    await challenge(); await db.prepare('UPDATE desktop_auth_rate_limits SET attempts = 20').run();
    expect((await challenge()).status).toBe(429);
  });
  it('fails closed in production, including HTTP',async()=>{
    env.BETA_ENVIRONMENT='production';expect((await publish()).status).toBe(403);
    expect((await challenge()).status).toBe(403);
  });
});

it('M9B revocation preserves the actual published signed envelope and blocks publication as active authorization',async()=>{
  expect((await publish()).status).toBe(200);
  const original=await db.prepare('SELECT * FROM published_licences').first();
  const licence=await db.prepare('SELECT licence_id,licence_status FROM beta_activations').first();
  env.OPERATOR_ACTIVATION_REVOKE_TOKEN='synthetic-revoke';
  const response=await post(revokeRoute,{schema_version:1,reason_code:'DEVICE_LOST',expected_status:'AUTHORIZED'},'synthetic-revoke');
  expect(response.status).toBe(200);
  expect(await db.prepare('SELECT * FROM published_licences').first()).toEqual(original);
  expect(await db.prepare('SELECT licence_id,licence_status FROM beta_activations').first()).toEqual(licence);
  expect((await publish()).status).toBe(403);
  expect(await db.prepare('SELECT * FROM published_licences').first()).toEqual(original);
});

it('M9C real Python desktop becomes Active, learns revocation, and remains Revoked offline after restart',async()=>{
  expect((await publish()).status).toBe(200);
  // Match the historical test issuer's original account grant exactly.
  await db.prepare('UPDATE account_entitlements SET starts_at=?,expires_at=?')
    .bind(new Date((envelope.expires_at-90*86400)*1000).toISOString().replace('.000Z','Z'),new Date(envelope.expires_at*1000).toISOString().replace('.000Z','Z')).run();
  env.OPERATOR_ACTIVATION_REVOKE_TOKEN='synthetic-revoke';
  const server=createServer(async(incoming,outgoing)=>{
    try {
      if(incoming.url==='/test/revoke'){
        const response=await post(revokeRoute,{schema_version:1,reason_code:'DEVICE_REPLACED',expected_status:'AUTHORIZED'},'synthetic-revoke');
        outgoing.writeHead(response.status);outgoing.end(await response.text());return;
      }
      const chunks=[];for await(const chunk of incoming)chunks.push(chunk);
      const request=new Request('http://localhost:8788'+incoming.url,{method:incoming.method,headers:incoming.headers,body:Buffer.concat(chunks)});
      const route=incoming.url.endsWith('device-status-challenge')?statusChallengeRoute:statusProofRoute;
      const response=await route({env,request});outgoing.writeHead(response.status,Object.fromEntries(response.headers));outgoing.end(await response.text());
    }catch{outgoing.writeHead(500);outgoing.end();}
  });
  await new Promise((done)=>server.listen(0,'127.0.0.1',done));
  try {
    const code=`import sys,json,tempfile,urllib.request
sys.path.insert(0,'..')
from backend.licensing.service import LicensingService
from backend.licensing.connectors.device_status import WebsiteDeviceStatusConnector,DeviceStatusNetworkError
from backend.licensing.device_identity import DeviceIdentityService,InMemorySecureKeyStore
from backend.licensing.lease_store import LeaseStore
from backend.runtime.paths import runtime_paths
facts=json.loads(sys.argv[1]);url=sys.argv[2]
key=InMemorySecureKeyStore();key.save_private_key(bytes.fromhex(facts['device_private']))
identity=DeviceIdentityService(key);device=identity.load_or_create()
with tempfile.TemporaryDirectory() as root:
 store=LeaseStore(runtime_paths(environ={'QUANTUM_STUDIO_DATA_ROOT':root}))
 def service(connector):
  return LicensingService(trusted_public_keys={facts['envelope']['kid']:bytes.fromhex(facts['issuer_public'])},
    device_identity=device,lease_store=store,now=lambda:facts['now'],status_connector=connector,identity_service=identity)
 connector=WebsiteDeviceStatusConnector(url,allow_local_http=True)
 s=service(connector);s.accept_lease(facts['envelope'])
 assert s.can_start_protected_work().allowed,s.diagnostics_summary()
 assert s.diagnostics_summary()['status']=='active'
 urllib.request.urlopen(url+'/test/revoke').read()
 assert not s.can_start_protected_work().allowed
 assert s.diagnostics_summary()['status']=='revoked'
 class Offline:
  def challenge(self,*args): raise DeviceStatusNetworkError('offline')
 restarted=service(Offline())
 assert restarted.diagnostics_summary()['status']=='revoked'
 restarted.accept_lease(facts['envelope'])
 assert not restarted.can_start_protected_work().allowed
 assert restarted.diagnostics_summary()['status']=='revoked'
 assert store.load_lease()==facts['envelope']
 print('real desktop Active -> Revoked -> offline Revoked passed')`;
    const facts={envelope,issuer_public:issuerPublic,device_private:pair.privateKey.export({format:'der',type:'pkcs8'}).subarray(-32).toString('hex'),now:Date.now()/1000};
    const result=await promisify(execFile)(python,['-c',code,JSON.stringify(facts),`http://127.0.0.1:${server.address().port}`],{timeout:25000});
    expect(result.stdout.trim()).toBe('real desktop Active -> Revoked -> offline Revoked passed');
    expect((await db.prepare('SELECT * FROM published_licences').first()).envelope_json).toBe(canonicalJson(envelope));
  }finally{server.closeAllConnections();await new Promise((done)=>server.close(done));}
});
