// Pages Functions only. Never import into frontend/build configuration.
import {validateDeployment, isLocalDeployment} from './deployment.js';
import {buildJsonResponse, sha256Hex} from './auth.js';
import {canonicalJson, validEnvelope, readDeviceRequest, decodeDeviceProof,
  exactDeviceFields, persistPublishedLicence} from './licence-delivery.js';
import {persistLicenceMetadata} from './licence-metadata.js';

const path = '/v1/licences/issue';
const target = 'https://private-signing.internal' + path; // Service Binding target, never public fetch.
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const encode = (bytes) => btoa(String.fromCharCode(...new Uint8Array(bytes))).replaceAll('+','-').replaceAll('/','_').replace(/=+$/, '');
const hex = (bytes) => Array.from(new Uint8Array(bytes), b=>b.toString(16).padStart(2,'0')).join('');
const fail = (status,code) => buildJsonResponse(status,{error:{code}});
const exact = exactDeviceFields;
export const SIGNING_REQUEST_TIMEOUT_MS = 30000;

function configuration(env) {
  try {
    if (!validateDeployment(env).ok || !['staging','production'].includes(env.BETA_ENVIRONMENT)
        || typeof env.SIGNING_SERVICE?.fetch !== 'function') throw new Error();
    const caller = JSON.parse(env.QS_SIGNING_SERVICE_CALLER);
    if (!exact(caller,['schema_version','environment','caller','secret']) || caller.schema_version !== 1
        || caller.environment !== env.BETA_ENVIRONMENT || typeof caller.caller !== 'string'
        || !/^[a-z][a-z0-9_-]{0,63}$/.test(caller.caller) || !decodeDeviceProof(caller.secret,32)) throw new Error();
    const trust = JSON.parse(env.QS_LICENCE_TRUST);
    if (!exact(trust,['schema_version','environment','domain','algorithm','keys']) || trust.schema_version !== 1
        || trust.environment !== env.BETA_ENVIRONMENT || trust.domain !== 'licence' || trust.algorithm !== 'Ed25519'
        || !trust.keys || typeof trust.keys !== 'object' || Array.isArray(trust.keys)
        || !Object.keys(trust.keys).length || Object.keys(trust.keys).length > 32) throw new Error();
    for (const [kid,value] of Object.entries(trust.keys)) {
      if (!/^lic-[a-z0-9][a-z0-9._-]{0,63}$/.test(kid) || !decodeDeviceProof(value,32)) throw new Error();
    }
    return {caller,trust};
  } catch { return null; }
}

// Matches Python signing_service_auth._message exactly (all signed fields are ASCII).
export async function signingServiceHeaders(environment, caller, body, timestamp, nonce) {
  const message = canonicalJson({purpose:'quantum-studio:private-licence-issuance:v1',environment,
    caller:caller.caller,method:'POST',path,timestamp,nonce,body_sha256:await sha256Hex(body)});
  const key = await crypto.subtle.importKey('raw',decodeDeviceProof(caller.secret,32),
    {name:'HMAC',hash:'SHA-256'},false,['sign']);
  const signature = await crypto.subtle.sign('HMAC',key,new TextEncoder().encode(message));
  return {'Content-Type':'application/json','X-QS-Caller':caller.caller,'X-QS-Timestamp':String(timestamp),
    'X-QS-Nonce':nonce,Authorization:'QS-HMAC-SHA256 '+encode(signature)};
}

async function eligible(env,id) {
  const row = await env.BETA_DB.prepare(`SELECT a.*, app.status AS application_status,
    ent.entitlement_id, ent.plan_id, ent.starts_at, ent.expires_at, ent.device_limit,
    ent.revision, ent.user_id AS entitlement_user_id, ent.application_id AS entitlement_application_id
    FROM beta_activations a JOIN beta_applications app ON app.application_id=a.application_id AND app.user_id=a.user_id
    LEFT JOIN account_entitlements ent ON ent.application_id=a.application_id AND ent.user_id=a.user_id
    WHERE a.activation_request_id=?`).bind(id).first();
  const now = Math.floor(Date.now()/1000);
  if (!row || row.status !== 'AUTHORIZED' || row.flag_reason != null || row.revoked_at != null
      || !row.authorized_at || !['APPROVED','LICENSE_ISSUED'].includes(row.application_status)
      || !row.entitlement_id || row.entitlement_user_id !== row.user_id || row.entitlement_application_id !== row.application_id
      || row.plan_id !== 'beta' || !Number.isSafeInteger(row.device_limit) || row.device_limit < 1
      || !Number.isSafeInteger(row.revision) || row.revision < 1
      || !Number.isFinite(Date.parse(row.starts_at)) || !Number.isFinite(Date.parse(row.expires_at))
      || Date.parse(row.starts_at)/1000 > now || Date.parse(row.expires_at)/1000 <= now
      || typeof row.device_public_key_hash !== 'string' || !/^[0-9a-f]{64}$/.test(row.device_public_key_hash)
      || row.installation_id !== 'dev_'+row.device_public_key_hash.slice(0,32)
      || (row.licence_id == null && [row.licence_status,row.licence_issued_at,row.licence_expires_at,row.licence_revoked_at].some(x=>x!=null))
      || (row.licence_id != null && (row.licence_status !== 'ISSUED' || row.licence_revoked_at != null))) return null;
  return row;
}

async function checkedEnvelope(data,row,trust) {
  if (!exact(data,['schema_version','result','envelope_sha256','envelope']) || data.schema_version !== 1
      || !['persisted','already_current'].includes(data.result) || !validEnvelope(data.envelope,{deployed:true})) return null;
  const e = data.envelope;
  const now = Math.floor(Date.now()/1000);
  if (e.device_id !== row.installation_id || e.device_public_key_hash !== row.device_public_key_hash
      || e.approved_application_ref !== row.application_id || e.expires_at !== Date.parse(row.expires_at)/1000
      || e.registered_device_limit !== row.device_limit || e.not_before < Date.parse(row.starts_at)/1000
      || e.not_before > now || e.issued_at > now || e.offline_until !== e.expires_at
      || e.concurrent_session_limit !== 1 || e.offline_device_limit !== 1 || e.entitlement_version !== 1
      || e.policy_profile !== 'PROFESSOR_BETA'
      || (row.licence_id != null && (row.licence_id !== e.licence_id || row.licence_status !== 'ISSUED'
        || Date.parse(row.licence_issued_at)/1000 !== e.issued_at || Date.parse(row.licence_expires_at)/1000 !== e.expires_at))
      || !Object.hasOwn(trust.keys,e.kid) || await sha256Hex(canonicalJson(e)) !== data.envelope_sha256) return null;
  const key = await crypto.subtle.importKey('raw',decodeDeviceProof(trust.keys[e.kid],32),'Ed25519',false,['verify']);
  const {signature,...covered} = e;
  return await crypto.subtle.verify('Ed25519',key,decodeDeviceProof(signature,64),new TextEncoder().encode(canonicalJson(covered))) ? e : null;
}

export async function issueLicenceViaService(env,activationId) {
  // Local issuance remains owned by the existing TEST worker, no binding required.
  if (isLocalDeployment(env)) return fail(409,'local_worker_required');
  const config = configuration(env);
  if (!config) return fail(503,'signing_not_configured');
  if (typeof activationId !== 'string' || !uuid.test(activationId)) return fail(400,'invalid_activation_id');
  let timer;
  const controller = new AbortController();
  try {
    const row = await eligible(env,activationId);
    if (!row) return fail(409,'activation_unavailable');
    const body = canonicalJson({schema_version:1,activation_request_id:activationId});
    const headers = await signingServiceHeaders(env.BETA_ENVIRONMENT,config.caller,body,
      Math.floor(Date.now()/1000),hex(crypto.getRandomValues(new Uint8Array(32))));
    const timeout = new Promise(resolve=>{timer=setTimeout(()=>{controller.abort();resolve(null);},SIGNING_REQUEST_TIMEOUT_MS);});
    const attempt = async () => {
      try {
        const response = await env.SIGNING_SERVICE.fetch(new Request(target,{method:'POST',headers,body,
          redirect:'error',signal:controller.signal}));
        if (response.status !== 200) return {status:response.status,data:null}; // Never read diagnostics.
        return {status:200,data:await readDeviceRequest(response)};
      } catch { return null; }
    };
    const reply = await Promise.race([attempt(),timeout]);
    clearTimeout(timer); controller.abort();
    if (!reply) return fail(503,'signing_temporarily_unavailable');
    if ([401,403].includes(reply.status)) return fail(503,'signing_authentication_failed');
    if (reply.status === 409) return fail(409,'signing_conflict');
    if (reply.status !== 200) return fail(503,'signing_temporarily_unavailable');
    const current = await eligible(env,activationId);
    // Ignore metadata changes from a concurrent identical completion, but bind the full entitlement/device snapshot.
    for (const field of ['user_id','application_id','installation_id','device_public_key_hash','status','authorized_at',
      'entitlement_id','plan_id','starts_at','expires_at','device_limit','revision']) {
      if (!current || current[field] !== row[field]) return fail(409,'activation_changed');
    }
    const e = await checkedEnvelope(reply.data,current,config.trust);
    if (!e) return fail(502,'invalid_signing_response');
    const stamp = value => new Date(value*1000).toISOString().replace('.000Z','Z');
    const metadata = await persistLicenceMetadata(env,activationId,{schema_version:1,installation_id:e.device_id,
      licence_id:e.licence_id,status:'ISSUED',issued_at:stamp(e.issued_at),expires_at:stamp(e.expires_at),revoked_at:null});
    if (!metadata.ok) return fail(409,'licence_conflict');
    return await persistPublishedLicence(env,activationId,e,{deployed:true});
  } catch { return fail(503,'signing_temporarily_unavailable'); }
  finally { clearTimeout(timer); controller.abort(); }
}
