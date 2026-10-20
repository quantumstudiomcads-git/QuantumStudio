import {sha256Hex, buildJsonResponse} from './auth.js';
import {constantTimeEquals, getBearerToken} from './operator-auth.js';
import {expectedOrigin} from './beta-registration.js';

const MAX_BYTES = 65536;
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const installation = /^dev_[0-9a-f]{32}$/;
const hex = /^[0-9a-f]{64}$/;
const purpose = 'quantum-studio:licence-retrieve:v1';
const random = () => Array.from(crypto.getRandomValues(new Uint8Array(32)), (b) => b.toString(16).padStart(2, '0')).join('');
const fail = (status, code) => buildJsonResponse(status, {error: {code}});
export const envelopeFields = [
  'schema_version','licence_id','account_id','subject_type','subject_id','approved_application_ref',
  'product','channel','plan_id','device_id','device_public_key_hash','issued_at','not_before','expires_at',
  'offline_until','entitlement_version','feature_entitlements','calculation_entitlements',
  'registered_device_limit','concurrent_session_limit','offline_device_limit','nonce','policy_profile',
  'issuer_label','kid','signature',
];
export function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  if (value !== null && typeof value === 'object') return `{${Object.keys(value).sort().map((k) => `${JSON.stringify(k)}:${canonicalJson(value[k])}`).join(',')}}`;
  return JSON.stringify(value);
}
function exact(value, fields) {
  return value && typeof value === 'object' && !Array.isArray(value)
    && Object.keys(value).length === fields.length && fields.every((k) => Object.hasOwn(value, k));
}
function decode(value, size) {
  if (typeof value !== 'string' || !/^[A-Za-z0-9_-]+$/.test(value)) return null;
  try {
    const text = atob(value.replaceAll('-', '+').replaceAll('_', '/') + '='.repeat((4 - value.length % 4) % 4));
    const bytes = Uint8Array.from(text, (c) => c.charCodeAt(0));
    const encoded = btoa(text).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/, '');
    return bytes.length === size && encoded === value ? bytes : null;
  } catch { return null; }
}
async function read(request) {
  if (request.headers.get('Content-Type')?.split(';', 1)[0].trim().toLowerCase() !== 'application/json') return null;
  const reader = request.body?.getReader();
  if (!reader) return null;
  const chunks = [];
  let size = 0;
  try {
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_BYTES) { await reader.cancel(); return null; }
      chunks.push(value);
    }
    const bytes = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
    return JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(bytes));
  } catch { return null; }
}
function validEnvelope(e) {
  if (!exact(e, envelopeFields) || e.schema_version !== 1 || e.product !== 'Quantum Studio'
      || e.channel !== 'beta' || e.subject_type !== 'beta_applicant' || e.plan_id !== 'pro'
      || typeof e.kid !== 'string' || !/^test-lic-[a-zA-Z0-9._-]{1,80}$/.test(e.kid)
      || typeof e.licence_id !== 'string' || !e.licence_id.startsWith('lic_') || !uuid.test(e.licence_id.slice(4))
      || !uuid.test(e.approved_application_ref) || e.account_id !== `sub_${e.approved_application_ref}`
      || e.subject_id !== e.account_id || !installation.test(e.device_id) || !hex.test(e.device_public_key_hash)
      || e.device_id !== `dev_${e.device_public_key_hash.slice(0,32)}` || !decode(e.signature,64)) return false;
  for (const key of ['issued_at','not_before','expires_at','offline_until','entitlement_version',
    'registered_device_limit','concurrent_session_limit','offline_device_limit']) {
    if (!Number.isSafeInteger(e[key]) || e[key] < (key === 'not_before' ? 0 : 1)) return false;
  }
  if (e.expires_at <= e.issued_at || e.not_before > e.expires_at || e.offline_until > e.expires_at) return false;
  for (const key of ['feature_entitlements','calculation_entitlements']) {
    if (!Array.isArray(e[key]) || e[key].length > 1000 || e[key].some((x) => typeof x !== 'string' || !/^[A-Za-z0-9:_.*-]{1,200}$/.test(x))) return false;
  }
  return typeof e.nonce === 'string' && uuid.test(e.nonce)
    && ['PROFESSOR_BETA','INTERNAL_VALIDATION'].includes(e.policy_profile)
    && e.issuer_label === 'Quantum Studio Licence Manager';
}
function gate(request, env) {
  if (env?.BETA_ENVIRONMENT === 'production' && new URL(request.url).protocol !== 'https:') return fail(403,'https_required');
  if (!['local','test'].includes(env?.BETA_ENVIRONMENT)) return fail(403,'test_only');
  if (!env.BETA_DB) return fail(503,'service_unavailable');
  const origin = request.headers.get('Origin');
  if (origin && origin !== expectedOrigin(env)) return fail(403,'origin_denied');
  return null;
}
async function quota(request, env, name, interval, limit) {
  const now = Math.floor(Date.now()/1000);
  const window = now - now % interval;
  const key = await sha256Hex(`licence:${name}:${env.BETA_IDENTITY_PEPPER || ''}:${request.headers.get('CF-Connecting-IP') || 'local'}`);
  const row = await env.BETA_DB.prepare(`INSERT INTO desktop_auth_rate_limits(bucket_key,window_start,attempts)
    VALUES(?,?,1) ON CONFLICT(bucket_key) DO UPDATE SET
    attempts = CASE WHEN window_start = excluded.window_start THEN attempts + 1 ELSE 1 END,
    window_start = excluded.window_start RETURNING attempts`).bind(key,window).first();
  return row && row.attempts <= limit;
}

export async function publishLicence(request, env, activationId) {
  const rejected = gate(request,env);
  if (rejected) return rejected;
  const token = typeof env.OPERATOR_LICENCE_PUBLISH_TOKEN === 'string' ? env.OPERATOR_LICENCE_PUBLISH_TOKEN.trim() : '';
  if (!token) return fail(503,'publication_not_configured');
  const bearer = getBearerToken(request);
  if (!bearer) return fail(401,'unauthorized');
  if (!constantTimeEquals(bearer,token)) return fail(403,'forbidden');
  if (typeof activationId !== 'string' || !uuid.test(activationId)) return fail(400,'invalid_activation_id');
  const body = await read(request);
  if (!exact(body,['schema_version','envelope']) || body.schema_version !== 1 || !validEnvelope(body.envelope)) return fail(400,'invalid_envelope');
  const e = body.envelope;
  try {
    const row = await env.BETA_DB.prepare('SELECT * FROM beta_activations WHERE activation_request_id = ?').bind(activationId).first();
    if (!row || row.status !== 'AUTHORIZED' || row.installation_id !== e.device_id
        || row.device_public_key_hash !== e.device_public_key_hash || row.application_id !== e.approved_application_ref) return fail(403,'activation_unavailable');
    if (row.licence_id !== e.licence_id || row.licence_status !== 'ISSUED') return fail(409,'metadata_not_current');
    const json = canonicalJson(e);
    const digest = await sha256Hex(json);
    const inserted = await env.BETA_DB.prepare(`INSERT INTO published_licences
      (activation_request_id,licence_id,envelope_json,envelope_sha256,published_at,status)
      SELECT ?,?,?,?,?, 'PUBLISHED' FROM beta_activations WHERE activation_request_id = ?
        AND status = 'AUTHORIZED' AND licence_id = ? AND device_public_key_hash = ?
      ON CONFLICT DO NOTHING`).bind(activationId,e.licence_id,json,digest,Math.floor(Date.now()/1000),activationId,e.licence_id,e.device_public_key_hash).run();
    const saved = await env.BETA_DB.prepare('SELECT * FROM published_licences WHERE activation_request_id = ? OR licence_id = ?').bind(activationId,e.licence_id).first();
    if (!saved || saved.activation_request_id !== activationId || saved.licence_id !== e.licence_id
        || saved.envelope_sha256 !== digest || saved.envelope_json !== json) return fail(409,'publication_conflict');
    return buildJsonResponse(200,{schema_version:1,result:inserted.meta?.changes === 1 ? 'published':'already_current',envelope_sha256:digest});
  } catch { return fail(503,'service_unavailable'); }
}

export async function deviceChallenge(request,env) {
  const rejected = gate(request,env);
  if (rejected) return rejected;
  const body = await read(request);
  if ((!exact(body,['installation_id']) && !exact(body,['installation_id','activation_request_id']))
      || typeof body.installation_id !== 'string' || !installation.test(body.installation_id)
      || (body.activation_request_id !== undefined && (typeof body.activation_request_id !== 'string' || !uuid.test(body.activation_request_id)))) return fail(400,'invalid_device');
  try {
    if (!await quota(request,env,'challenge',300,20)) return fail(429,'rate_limited');
    const rows = await env.BETA_DB.prepare(`SELECT * FROM beta_activations WHERE installation_id = ?
      AND status = 'AUTHORIZED' AND (? IS NULL OR activation_request_id = ?) LIMIT 2`).bind(
      body.installation_id,body.activation_request_id ?? null,body.activation_request_id ?? null).all();
    if (rows.results?.length !== 1) return fail(403,'activation_unavailable');
    const row = rows.results[0];
    if (typeof row.device_public_key_hash !== 'string' || !hex.test(row.device_public_key_hash)
        || row.installation_id !== `dev_${row.device_public_key_hash.slice(0,32)}`) return fail(403,'activation_unavailable');
    const now = Math.floor(Date.now()/1000);
    await env.BETA_DB.prepare(`DELETE FROM licence_device_challenges WHERE challenge_id IN
      (SELECT challenge_id FROM licence_device_challenges WHERE expires_at < ? LIMIT 100)`).bind(now-86400).run();
    const message = {schema_version:1,purpose,challenge_id:random(),nonce:random(),
      activation_request_id:row.activation_request_id,installation_id:row.installation_id,
      device_public_key_hash:row.device_public_key_hash,expires_at:now+120};
    await env.BETA_DB.prepare(`INSERT INTO licence_device_challenges
      (challenge_id,activation_request_id,installation_id,device_public_key_hash,message_json,expires_at)
      VALUES(?,?,?,?,?,?)`).bind(message.challenge_id,row.activation_request_id,row.installation_id,row.device_public_key_hash,canonicalJson(message),message.expires_at).run();
    return buildJsonResponse(200,{challenge:message});
  } catch { return fail(503,'service_unavailable'); }
}

export async function deviceRetrieve(request,env) {
  const rejected = gate(request,env);
  if (rejected) return rejected;
  const body = await read(request);
  if (!exact(body,['challenge_id','installation_id','public_key','signature'])
      || typeof body.challenge_id !== 'string' || !hex.test(body.challenge_id)
      || typeof body.installation_id !== 'string' || !installation.test(body.installation_id)) return fail(400,'invalid_proof');
  const pub = decode(body.public_key,32), signature = decode(body.signature,64);
  if (!pub || !signature) return fail(400,'invalid_proof');
  try {
    if (!await quota(request,env,'retrieve',60,60)) return fail(429,'rate_limited');
    const row = await env.BETA_DB.prepare('SELECT * FROM licence_device_challenges WHERE challenge_id = ?').bind(body.challenge_id).first();
    const now = Math.floor(Date.now()/1000);
    if (!row || row.consumed_at !== null || row.expires_at <= now) return fail(409,'challenge_unavailable');
    const digest = await sha256Hex(pub);
    if (row.installation_id !== body.installation_id || row.device_public_key_hash !== digest
        || body.installation_id !== `dev_${digest.slice(0,32)}`) return fail(403,'invalid_proof');
    const key = await crypto.subtle.importKey('raw',pub,'Ed25519',false,['verify']);
    if (!await crypto.subtle.verify('Ed25519',key,signature,new TextEncoder().encode(row.message_json))) return fail(403,'invalid_proof');
    const consumed = await env.BETA_DB.prepare(`UPDATE licence_device_challenges SET consumed_at = ?
      WHERE challenge_id = ? AND consumed_at IS NULL AND expires_at > ?`).bind(now,body.challenge_id,Math.floor(Date.now()/1000)).run();
    if (consumed.meta?.changes !== 1) return fail(409,'challenge_unavailable');
    const activation = await env.BETA_DB.prepare('SELECT * FROM beta_activations WHERE activation_request_id = ?').bind(row.activation_request_id).first();
    if (!activation || activation.status !== 'AUTHORIZED' || activation.installation_id !== row.installation_id
        || activation.device_public_key_hash !== digest) return fail(403,'activation_unavailable');
    const saved = await env.BETA_DB.prepare('SELECT * FROM published_licences WHERE activation_request_id = ?').bind(row.activation_request_id).first();
    if (!saved) return buildJsonResponse(200,{state:'pending'});
    if (saved.status !== 'PUBLISHED' || saved.licence_id !== activation.licence_id
        || activation.licence_status !== 'ISSUED' || await sha256Hex(saved.envelope_json) !== saved.envelope_sha256) return fail(409,'publication_conflict');
    const envelope = JSON.parse(saved.envelope_json);
    if (envelope.licence_id !== saved.licence_id || envelope.device_id !== row.installation_id
        || envelope.device_public_key_hash !== digest) return fail(409,'publication_conflict');
    return buildJsonResponse(200,{state:'available',envelope,envelope_sha256:saved.envelope_sha256});
  } catch { return fail(503,'service_unavailable'); }
}
