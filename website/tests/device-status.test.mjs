import {beforeEach, afterEach, describe, it, expect, vi} from 'vitest';
import {mkdtempSync,readFileSync,readdirSync,rmSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {generateKeyPairSync,createHash,sign} from 'node:crypto';
import {SQLiteD1} from './helpers/sqlite-d1.mjs';
import {canonicalJson} from '../functions/_lib/licence-delivery.js';
import {onRequestPost as challengeRoute} from '../functions/api/licence/device-status-challenge.js';
import {onRequestPost as statusRoute} from '../functions/api/licence/device-status.js';
import {onRequestPost as deliveryChallenge} from '../functions/api/licence/device-challenge.js';
import {onRequestPost as retrieveRoute} from '../functions/api/licence/device-retrieve.js';
import {onRequestPost as revokeRoute} from '../functions/api/operator/activations/[activationId]/revoke.js';
vi.setConfig({testTimeout:30000});
const id='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',app='12345678-1234-4123-8123-123456789abc';
const licence='lic_bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const pair=generateKeyPairSync('ed25519');
const pub=pair.publicKey.export({format:'der',type:'spki'}).subarray(-32);
const hash=createHash('sha256').update(pub).digest('hex'),installation='dev_'+hash.slice(0,32);
const envelope='historical immutable signed bytes',digest=createHash('sha256').update(envelope).digest('hex');
let db,env,root;
const post=(route,body)=>route({env,params:{activationId:id},request:new Request('http://localhost:8788/api/test',{
  method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer synthetic-revoke'},body:JSON.stringify(body)})});
const challenge=()=>post(challengeRoute,{installation_id:installation,licence_id:licence,envelope_sha256:digest});
const proof=(m,key=pair.privateKey,keyBytes=pub)=>({challenge_id:m.challenge_id,installation_id:installation,
  public_key:keyBytes.toString('base64url'),signature:sign(null,Buffer.from(canonicalJson(m)),key).toString('base64url')});
const message=async()=>{const response=await challenge();expect(response.status).toBe(200);return (await response.json()).challenge;};
const revoke=()=>post(revokeRoute,{schema_version:1,reason_code:'DEVICE_REPLACED',expected_status:'AUTHORIZED'});
beforeEach(()=>{
  vi.useFakeTimers({toFake:['Date']});vi.setSystemTime(new Date('2026-10-25T12:00:00Z'));
  root=mkdtempSync(join(tmpdir(),'qs-m9c-'));db=new SQLiteD1(join(root,'db.sqlite3'));
  db.script(readdirSync('migrations').filter((f)=>f.endsWith('.sql')).sort().map((f)=>readFileSync(join('migrations',f),'utf8')).join('\n'));
  db.script(`INSERT INTO users(user_id,full_name,institution,email,normalized_email,email_lookup_hash,status,created_at,updated_at)
    VALUES('u','Test','Test','a@example.test','a@example.test','hash','VERIFIED','2026-10-25','2026-10-25');
    INSERT INTO beta_applications(application_id,user_id,full_name,email,normalized_email,email_lookup_hash,institution,country,research_area,
      operating_system,privacy_consent,privacy_version,terms_consent,terms_version,communications_consent,status,submitted_at,updated_at)
    VALUES('${app}','u','Test','a@example.test','a@example.test','hash','Test','Test','Test','Windows',1,'1',1,'1',0,'APPROVED','2026-10-25','2026-10-25');
    INSERT INTO beta_activations(activation_request_id,user_id,application_id,installation_id,platform,architecture,app_version,status,
      created_at,updated_at,authorized_at,device_public_key_hash,licence_id,licence_status)
    VALUES('${id}','u','${app}','${installation}','windows','x86_64','0.2.0','AUTHORIZED','2026-10-25','2026-10-25','2026-10-25','${hash}','${licence}','ISSUED');
    INSERT INTO published_licences VALUES('${id}','${licence}','${envelope}','${digest}',1,'PUBLISHED');`);
  env={BETA_DB:db,BETA_ENVIRONMENT:'local',BETA_ALLOWED_ORIGIN:'http://localhost:8788',OPERATOR_ACTIVATION_REVOKE_TOKEN:'synthetic-revoke'};
});
afterEach(()=>{vi.useRealTimers();rmSync(root,{recursive:true,force:true});});

describe('M9C authenticated status is separate from artifact delivery',()=>{
  it('returns only bound authorization metadata with current entitlement and server time',async()=>{
    const m=await message();expect(m.purpose).toBe('quantum-studio:device-status:v1');
    expect(m.expires_at-m.server_time).toBe(120);
    const response=await post(statusRoute,proof(m));expect(response.status).toBe(200);
    const data=await response.json();
    expect(data).toMatchObject({schema_version:1,challenge_id:m.challenge_id,activation_id:id,installation_id:installation,
      device_public_key_hash:hash,licence_id:licence,envelope_sha256:digest,authorization_state:'AUTHORIZED',authorization_revision:1,
      entitlement_revision:1,revoked_at:null,reason_code:null,server_time:Date.now()/1000,checked_at:Date.now()/1000});
    expect(Object.keys(data).sort()).toEqual(['schema_version','challenge_id','activation_id','installation_id','device_public_key_hash',
      'licence_id','envelope_sha256','authorization_state','authorization_revision','entitlement_id','entitlement_revision',
      'entitlement_expires_at','revoked_at','reason_code','server_time','checked_at'].sort());
    expect(JSON.stringify(data)).not.toContain(envelope);expect(JSON.stringify(data)).not.toContain('a@example.test');
  });
  it('authenticates a revoked activation without delivering an artifact or changing entitlement/history',async()=>{
    const original=await db.prepare('SELECT * FROM account_entitlements').first();
    const publication=await db.prepare('SELECT * FROM published_licences').first();
    expect((await revoke()).status).toBe(200);
    const m=await message();const response=await post(statusRoute,proof(m));expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({authorization_state:'REVOKED',authorization_revision:2,reason_code:'DEVICE_REPLACED'});
    expect((await post(deliveryChallenge,{installation_id:installation,activation_request_id:id})).status).toBe(403);
    expect((await post(retrieveRoute,proof(m))).status).toBe(409);
    expect(await db.prepare('SELECT * FROM published_licences').first()).toEqual(publication);
    expect(await db.prepare('SELECT * FROM account_entitlements').first()).toEqual(original);
  });
  it('rejects replay, including concurrent consumption',async()=>{
    const p=proof(await message());const responses=await Promise.all([post(statusRoute,p),post(statusRoute,p)]);
    expect(responses.map((r)=>r.status).sort()).toEqual([200,409]);expect((await post(statusRoute,p)).status).toBe(409);
  });
  it('rejects expired challenges',async()=>{
    const m=await message();vi.setSystemTime(new Date(m.expires_at*1000));
    expect((await post(statusRoute,proof(m))).status).toBe(409);
  });
  it('rejects a different device key, modified signed challenge, or bad signature',async()=>{
    const m=await message(),wrong=generateKeyPairSync('ed25519');
    expect((await post(statusRoute,proof(m,wrong.privateKey,wrong.publicKey.export({format:'der',type:'spki'}).subarray(-32)))).status).toBe(403);
    expect((await post(statusRoute,proof({...m,purpose:'quantum-studio:licence-retrieve:v1'}))).status).toBe(403);
    expect((await post(statusRoute,{...proof(m),signature:Buffer.alloc(64).toString('base64url')})).status).toBe(403);
  });
  it('does not accept a delivery-domain challenge for status',async()=>{
    const response=await post(deliveryChallenge,{installation_id:installation});expect(response.status).toBe(200);
    expect((await post(statusRoute,proof((await response.json()).challenge))).status).toBe(409);
  });
  it('uses current state after revocation races challenge issuance',async()=>{
    const m=await message();await revoke();
    expect(await (await post(statusRoute,proof(m))).json()).toMatchObject({authorization_state:'REVOKED',authorization_revision:2});
  });
  it.each([{licence_id:'lic_cccccccc-cccc-4ccc-8ccc-cccccccccccc'},{envelope_sha256:'0'.repeat(64)},{installation_id:'dev_'+'0'.repeat(32)}])(
    'rejects mismatched bindings %j',async(changes)=>{
      const response=await post(challengeRoute,{installation_id:installation,licence_id:licence,envelope_sha256:digest,...changes});
      expect([403,409]).toContain(response.status);
    });
  it('returns expired entitlement time without inferring expiry from the local device clock',async()=>{
    const expiry=Date.parse((await db.prepare('SELECT expires_at FROM account_entitlements').first()).expires_at)/1000;
    vi.setSystemTime(new Date((expiry+1)*1000));
    const data=await (await post(statusRoute,proof(await message()))).json();
    expect(data.entitlement_expires_at).toBe(expiry);expect(data.server_time).toBeGreaterThan(data.entitlement_expires_at);
  });
  it('rejects changed publication digest between challenge and status',async()=>{
    const m=await message();await db.prepare('UPDATE published_licences SET envelope_sha256=?').bind('0'.repeat(64)).run();
    expect((await post(statusRoute,proof(m))).status).toBe(409);
  });
  it('fails closed for absent entitlements or insecure non-local access',async()=>{
    const m=await message();await db.prepare('DELETE FROM account_entitlements').run();
    expect((await post(statusRoute,proof(m))).status).toBe(409);
    env.BETA_ENVIRONMENT='production';expect((await challenge()).status).toBe(403);
  });
});

it('permits status proof without an artifact but cannot grant or return a licence',async()=>{
  await db.prepare('DELETE FROM published_licences').run();
  await db.prepare('UPDATE beta_activations SET licence_id=NULL,licence_status=NULL').run();
  const response=await post(challengeRoute,{activation_id:id,installation_id:installation,licence_id:null,envelope_sha256:null});
  expect(response.status).toBe(200);const m=(await response.json()).challenge;
  expect(m.licence_id).toBeNull();expect(m.envelope_sha256).toBeNull();
  const data=await (await post(statusRoute,proof(m))).json();
  expect(data.authorization_state).toBe('AUTHORIZED');expect(data.licence_id).toBeNull();expect(data.envelope_sha256).toBeNull();
  expect(data).not.toHaveProperty('envelope');expect(data).not.toHaveProperty('feature_entitlements');
});
