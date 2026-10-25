import {constantTimeEquals, getBearerToken} from '../../../../_lib/operator-auth.js';

const REASONS = new Set(['DEVICE_REPLACED', 'DEVICE_LOST', 'USER_REQUEST',
  'BETA_ACCESS_REVOKED', 'ADMINISTRATIVE', 'OTHER']);
const ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const MAX_BYTES = 2048;
const headers = {'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store',
  'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer'};
const json = (status, value) => new Response(JSON.stringify(value), {status, headers});
const failure = (status, code) => json(status, {error: {code}});
const readActivation = (db, id) => db.prepare(`SELECT application_id, status, revoked_at,
  revocation_reason_code, revocation_reason_text FROM beta_activations WHERE activation_request_id = ?`).bind(id).first();
const matches = (row, payload) => row?.status === 'REVOKED' && row.revoked_at
  && row.revocation_reason_code === payload.reason_code
  && row.revocation_reason_text === (payload.reason_text ?? null);
const success = (id, row, result) => json(200, {schema_version: 1, activation_request_id: id,
  status: 'REVOKED', result, revoked_at: row.revoked_at, reason_code: row.revocation_reason_code});

export async function onRequestPost({request, env, params}) {
  const id = params?.activationId;
  if (typeof id !== 'string' || !ID.test(id)) return failure(400, 'invalid_activation_id');
  if (!env?.BETA_DB) return failure(503, 'service_unavailable');
  if (env.BETA_ENVIRONMENT === 'production' && new URL(request.url).protocol !== 'https:') {
    return failure(403, 'https_required');
  }
  const credential = env.OPERATOR_ACTIVATION_REVOKE_TOKEN;
  if (typeof credential !== 'string' || !credential.trim() || credential.trim() !== credential) {
    return failure(503, 'service_unavailable');
  }
  const token = getBearerToken(request);
  if (!token) return failure(401, 'unauthorized');
  if (!constantTimeEquals(token, credential)) return failure(403, 'forbidden');
  if (request.headers.get('Content-Type')?.split(';')[0].trim().toLowerCase() !== 'application/json') {
    return failure(415, 'unsupported_media_type');
  }
  if (Number(request.headers.get('Content-Length')) > MAX_BYTES) return failure(413, 'request_too_large');
  let payload;
  try {
    const reader = request.body?.getReader();
    if (!reader) return failure(400, 'invalid_json');
    const chunks = []; let length = 0;
    try {
      while (true) {
        const {done, value} = await reader.read(); if (done) break;
        length += value.byteLength;
        if (length > MAX_BYTES) {await reader.cancel(); return failure(413, 'request_too_large');}
        chunks.push(value);
      }
    } finally {reader.releaseLock();}
    const bytes = new Uint8Array(length); let offset = 0;
    for (const chunk of chunks) {bytes.set(chunk, offset); offset += chunk.byteLength;}
    payload = JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(bytes));
  } catch {return failure(400, 'invalid_json');}
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)
      || Object.keys(payload).some((key) => !['schema_version', 'reason_code', 'reason_text', 'expected_status'].includes(key))
      || payload.schema_version !== 1 || !REASONS.has(payload.reason_code)
      || typeof payload.expected_status !== 'string'
      || ('reason_text' in payload && (typeof payload.reason_text !== 'string'
        || payload.reason_text.length < 1 || payload.reason_text.length > 240
        || payload.reason_text.trim() !== payload.reason_text || /[\x00-\x1f\x7f]/.test(payload.reason_text)))) {
    return failure(400, 'invalid_payload');
  }
  // No activation revision exists in M9A. Require the precise source state;
  // REVOKED is terminal, so identical retries cannot encounter an ABA transition.
  if (payload.expected_status !== 'AUTHORIZED') return failure(409, 'activation_conflict');
  const db = env.BETA_DB;
  try {
    const row = await readActivation(db, id);
    if (!row) return failure(404, 'activation_not_found');
    if (row.status === 'REVOKED') {
      return matches(row, payload) ? success(id, row, 'already_revoked') : failure(409, 'activation_conflict');
    }
    if (row.status !== 'AUTHORIZED') return failure(409, 'activation_conflict');
    const now = new Date().toISOString();
    const results = await db.batch([
      db.prepare(`UPDATE beta_activations SET status = 'REVOKED', revoked_at = ?, updated_at = ?,
        revocation_reason_code = ?, revocation_reason_text = ?
        WHERE activation_request_id = ? AND status = 'AUTHORIZED' AND revoked_at IS NULL`)
        .bind(now, now, payload.reason_code, payload.reason_text ?? null, id),
      db.prepare(`INSERT INTO beta_audit_events
        (event_id, application_id, event_type, event_timestamp, actor_reference, old_status, new_status, metadata_json)
        SELECT ?, ?, 'OPERATOR_DEVICE_REVOKED', ?, 'operator-device-revocation', 'AUTHORIZED', 'REVOKED', ?
        WHERE changes() = 1`)
        .bind(crypto.randomUUID(), row.application_id, now,
          JSON.stringify({schema: 1, activation_id: id, reason_code: payload.reason_code})),
    ]);
    const changes = results?.[0]?.meta?.changes;
    if (!Number.isSafeInteger(changes) || changes < 0) return failure(503, 'service_unavailable');
    const current = await readActivation(db, id);
    if (!matches(current, payload)) return failure(409, 'activation_conflict');
    return success(id, current, changes > 0 ? 'revoked' : 'already_revoked');
  } catch {return failure(503, 'service_unavailable');}
}
