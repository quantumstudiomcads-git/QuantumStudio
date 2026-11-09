import {readPublicLicenceState, currentPublicLicenceState} from './public-licence-state.js';
import {validateDeployment, isLocalDeployment} from './deployment.js';
import {sha256Hex, buildJsonResponse} from './auth.js';
import {expectedOrigin} from './beta-registration.js';
import {canonicalJson, readDeviceRequest as read, decodeDeviceProof as decode,
  exactDeviceFields as exact, deviceProofQuota as quota} from './licence-delivery.js';

const purpose = 'quantum-studio:device-status:v1';
const hex = /^[0-9a-f]{64}$/;
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const fail = (status, code) => buildJsonResponse(status, {error:{code}});
const random = () => Array.from(crypto.getRandomValues(new Uint8Array(32)),(b)=>b.toString(16).padStart(2,'0')).join('');
function gate(request, env) {
  if (!env?.BETA_DB) return fail(503,'service_unavailable');
  const url = new URL(request.url);
  if (url.protocol !== 'https:' && !( ['local','test'].includes(env.BETA_ENVIRONMENT)
      && ['localhost','127.0.0.1','[::1]'].includes(url.hostname))) return fail(403,'https_required');
  if (!validateDeployment(env).ok) return fail(503,'configuration_unavailable');
  const origin = request.headers.get('Origin');
  return origin && origin !== expectedOrigin(env) ? fail(403,'origin_denied') : null;
}
const lookup = (db, id) => db.prepare(`SELECT a.*, p.envelope_sha256, p.licence_id AS published_licence_id,
  p.status AS publication_status, e.entitlement_id, e.revision AS entitlement_revision,
  e.starts_at, e.expires_at AS entitlement_expires_at
  FROM beta_activations a LEFT JOIN published_licences p ON p.activation_request_id=a.activation_request_id
  LEFT JOIN account_entitlements e ON e.application_id=a.application_id AND e.user_id=a.user_id
  WHERE a.activation_request_id = ?`).bind(id).first();
function binding(row, message) {
  return row && ['AUTHORIZED','REVOKED'].includes(row.status)
    && row.activation_request_id === message.activation_request_id
    && row.installation_id === message.installation_id && row.device_public_key_hash === message.device_public_key_hash
    && (row.licence_id ?? null) === message.licence_id
    && (row.envelope_sha256 ?? null) === message.envelope_sha256
    && (row.published_licence_id == null ? message.envelope_sha256 === null
        : row.published_licence_id === message.licence_id && row.publication_status === 'PUBLISHED');
}
export async function deviceStatusChallenge(request, env) {
  const rejected = gate(request,env); if(rejected) return rejected;
  const body = await read(request);
  if ((!exact(body,['installation_id','licence_id','envelope_sha256'])
      && !exact(body,['installation_id','licence_id','envelope_sha256','activation_id']))
      || typeof body.installation_id !== 'string' || !/^dev_[0-9a-f]{32}$/.test(body.installation_id)
      || (body.activation_id !== undefined && (typeof body.activation_id !== 'string' || !uuid.test(body.activation_id)))
      || (body.licence_id === null ? !body.activation_id
        : typeof body.licence_id !== 'string' || !body.licence_id.startsWith('lic_') || !uuid.test(body.licence_id.slice(4)))
      || (body.envelope_sha256 !== null && (typeof body.envelope_sha256 !== 'string' || !hex.test(body.envelope_sha256)))) return fail(400,'invalid_binding');
  try {
    if(!await quota(request,env,'status-challenge',300,60)) return fail(429,'rate_limited');
    // A licence ID identifies the historical activation even after a same-device replacement.
    const a = await env.BETA_DB.prepare(`SELECT activation_request_id FROM beta_activations
      WHERE installation_id=? AND licence_id IS ? AND status IN ('AUTHORIZED','REVOKED')
        AND (? IS NULL OR activation_request_id=?)`).bind(body.installation_id,body.licence_id,body.activation_id??null,body.activation_id??null).first();
    const row = a && await lookup(env.BETA_DB,a.activation_request_id);
    if(!row || typeof row.device_public_key_hash !== 'string' || !hex.test(row.device_public_key_hash)
        || row.installation_id !== 'dev_'+row.device_public_key_hash.slice(0,32)) return fail(403,'activation_unavailable');
    const now = Math.floor(Date.now()/1000);
    const message = {schema_version:1,purpose,challenge_id:random(),nonce:random(),
      activation_request_id:row.activation_request_id,installation_id:row.installation_id,
      device_public_key_hash:row.device_public_key_hash,licence_id:body.licence_id,
      envelope_sha256:body.envelope_sha256,server_time:now,expires_at:now+120};
    if(!binding(row,message)) return fail(409,'binding_conflict');
    await env.BETA_DB.prepare(`DELETE FROM device_status_challenges WHERE challenge_id IN
      (SELECT challenge_id FROM device_status_challenges WHERE expires_at < ? LIMIT 100)`).bind(now-86400).run();
    await env.BETA_DB.prepare(`INSERT INTO device_status_challenges(challenge_id,activation_request_id,message_json,expires_at)
      VALUES(?,?,?,?)`).bind(message.challenge_id,row.activation_request_id,canonicalJson(message),message.expires_at).run();
    return buildJsonResponse(200,{challenge:message});
  } catch {return fail(503,'service_unavailable');}
}
export async function deviceStatus(request, env) {
  const rejected=gate(request,env); if(rejected) return rejected;
  const body=await read(request);
  if(!exact(body,['challenge_id','installation_id','public_key','signature'])
      || typeof body.challenge_id !== 'string' || !hex.test(body.challenge_id)) return fail(400,'invalid_proof');
  const pub=decode(body.public_key,32), signature=decode(body.signature,64);
  if(!pub || !signature) return fail(400,'invalid_proof');
  try {
    if(!await quota(request,env,'status-proof',60,120)) return fail(429,'rate_limited');
    const saved=await env.BETA_DB.prepare('SELECT * FROM device_status_challenges WHERE challenge_id=?').bind(body.challenge_id).first();
    const now=Math.floor(Date.now()/1000);
    if(!saved || saved.consumed_at !== null || saved.expires_at <= now) return fail(409,'challenge_unavailable');
    const message=JSON.parse(saved.message_json), digest=await sha256Hex(pub);
    if(message.purpose !== purpose || message.installation_id !== body.installation_id || message.device_public_key_hash !== digest
        || body.installation_id !== 'dev_'+digest.slice(0,32)) return fail(403,'invalid_proof');
    const key=await crypto.subtle.importKey('raw',pub,'Ed25519',false,['verify']);
    if(!await crypto.subtle.verify('Ed25519',key,signature,new TextEncoder().encode(saved.message_json))) return fail(403,'invalid_proof');
    const consumed=await env.BETA_DB.prepare(`UPDATE device_status_challenges SET consumed_at=?
      WHERE challenge_id=? AND consumed_at IS NULL AND expires_at>?`).bind(now,body.challenge_id,now).run();
    if(consumed.meta?.changes !== 1) return fail(409,'challenge_unavailable');
    const row=isLocalDeployment(env) ? await lookup(env.BETA_DB,saved.activation_request_id)
      : await readPublicLicenceState(env.BETA_DB,saved.activation_request_id);
    if(!binding(row,message)) return fail(409,'binding_conflict');
    if(!isLocalDeployment(env) && !await currentPublicLicenceState(row,{allowExpired:true})) return fail(409,'licence_unavailable');
    const starts=Date.parse(row.starts_at)/1000, expires=Date.parse(row.entitlement_expires_at)/1000;
    if(!row.entitlement_id || !Number.isSafeInteger(row.entitlement_revision) || row.entitlement_revision<1
        || !Number.isSafeInteger(row.authorization_revision) || row.authorization_revision<1
        || !Number.isFinite(starts) || !Number.isFinite(expires) || starts>now) return fail(409,'entitlement_unavailable');
    if(row.status==='REVOKED' && !Number.isFinite(Date.parse(row.revoked_at))) return fail(409,'revocation_unavailable');
    // No artifact, signature, feature grant, email, or operator credential is returned.
    return buildJsonResponse(200,{schema_version:1,challenge_id:message.challenge_id,
      activation_id:row.activation_request_id,installation_id:row.installation_id,device_public_key_hash:digest,
      authorization_state:row.status,authorization_revision:row.authorization_revision,
      licence_id:row.licence_id,envelope_sha256:row.envelope_sha256,
      entitlement_id:row.entitlement_id,entitlement_revision:row.entitlement_revision,
      entitlement_expires_at:expires,revoked_at:row.status==='REVOKED'?row.revoked_at:null,
      reason_code:row.status==='REVOKED'?row.revocation_reason_code:null,server_time:now,checked_at:now});
  } catch {return fail(503,'service_unavailable');}
}
