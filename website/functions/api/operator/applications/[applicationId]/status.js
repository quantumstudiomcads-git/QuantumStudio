import {assertTransition} from '../../../../_lib/workflow.js';
import {constantTimeEquals, getBearerToken} from '../../../../_lib/operator-auth.js';

const JSON_HEADERS = Object.freeze({
  'Content-Type': 'application/json; charset=utf-8',
  'Cache-Control': 'no-store',
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'no-referrer',
  'Cross-Origin-Resource-Policy': 'same-site',
});
const MAX_REQUEST_BYTES = 1024;
const MAX_RESPONSE_BYTES = 4096;
const REVIEW_STATUSES = new Set(['APPLIED', 'UNDER_REVIEW', 'APPROVED', 'REJECTED']);
const APPLICATION_ID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function jsonResponse(status, payload) {
  const body = JSON.stringify(payload);
  const headers = new Headers(JSON_HEADERS);
  if (new TextEncoder().encode(body).byteLength > MAX_RESPONSE_BYTES) {
    return new Response('{"error":{"code":"response_too_large"}}', {status: 500, headers});
  }
  return new Response(body, {status, headers});
}

async function readBoundedBody(request) {
  if (!request.body) {
    return '';
  }
  const reader = request.body.getReader();
  const chunks = [];
  let byteLength = 0;
  try {
    while (true) {
      const {done, value} = await reader.read();
      if (done) {
        break;
      }
      byteLength += value.byteLength;
      if (byteLength > MAX_REQUEST_BYTES) {
        await reader.cancel();
        throw new RangeError('request_too_large');
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const bytes = new Uint8Array(byteLength);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return new TextDecoder('utf-8', {fatal: true}).decode(bytes);
}

function responseForState(applicationId, status, result) {
  return jsonResponse(200, {schema_version: 1, application_id: applicationId, status, result});
}

export async function onRequestPost({request, env, params}) {
  const applicationId = params?.applicationId;
  if (typeof applicationId !== 'string' || !APPLICATION_ID_PATTERN.test(applicationId)) {
    return jsonResponse(400, {error: {code: 'invalid_application_id'}});
  }
  if (!env?.BETA_DB) {
    return jsonResponse(503, {error: {code: 'service_unavailable'}});
  }
  const url = new URL(request.url);
  if (env.BETA_ENVIRONMENT === 'production' && url.protocol !== 'https:') {
    return jsonResponse(403, {error: {code: 'https_required'}});
  }
  const configuredToken = typeof env.OPERATOR_STATUS_SYNC_TOKEN === 'string'
    ? env.OPERATOR_STATUS_SYNC_TOKEN.trim()
    : '';
  if (!configuredToken) {
    return jsonResponse(503, {error: {code: 'service_unavailable'}});
  }
  const token = getBearerToken(request);
  if (!token) {
    return jsonResponse(401, {error: {code: 'unauthorized'}});
  }
  if (!constantTimeEquals(token, configuredToken)) {
    return jsonResponse(403, {error: {code: 'forbidden'}});
  }

  const contentLength = request.headers.get('Content-Length');
  if (contentLength && contentLength.trim() !== '' && Number(contentLength) > MAX_REQUEST_BYTES) {
    return jsonResponse(413, {error: {code: 'request_too_large'}});
  }
  if (request.headers.get('Content-Type')?.split(';', 1)[0].trim().toLowerCase() !== 'application/json') {
    return jsonResponse(415, {error: {code: 'unsupported_media_type'}});
  }
  let body;
  try {
    body = await readBoundedBody(request);
  } catch (error) {
    if (error instanceof RangeError) {
      return jsonResponse(413, {error: {code: 'request_too_large'}});
    }
    return jsonResponse(400, {error: {code: 'invalid_json'}});
  }
  let payload;
  try {
    payload = JSON.parse(body);
  } catch {
    return jsonResponse(400, {error: {code: 'invalid_json'}});
  }
  if (
    !payload
    || typeof payload !== 'object'
    || Array.isArray(payload)
    || Object.keys(payload).sort().join(',') !== 'schema_version,status'
    || payload.schema_version !== 1
    || !Number.isInteger(payload.schema_version)
  ) {
    return jsonResponse(400, {error: {code: 'invalid_payload'}});
  }
  if (typeof payload.status !== 'string' || !REVIEW_STATUSES.has(payload.status)) {
    return jsonResponse(400, {error: {code: 'invalid_status'}});
  }

  let application;
  try {
    application = await env.BETA_DB.prepare(
      'SELECT status FROM beta_applications WHERE application_id = ?'
    ).bind(applicationId).first();
  } catch {
    return jsonResponse(503, {error: {code: 'service_unavailable'}});
  }
  if (!application) {
    return jsonResponse(404, {error: {code: 'application_not_found'}});
  }
  if (application.status === payload.status) {
    return responseForState(applicationId, payload.status, 'already_current');
  }
  try {
    assertTransition(application.status, payload.status);
  } catch {
    return jsonResponse(409, {error: {code: 'invalid_transition'}});
  }

  const timestamp = new Date().toISOString();
  const eventId = crypto.randomUUID();
  const metadata = JSON.stringify({schema: 1, source: 'operator_status_sync'});
  let results;
  try {
    results = await env.BETA_DB.batch([
      env.BETA_DB.prepare(`UPDATE beta_applications
        SET status = ?, updated_at = ?,
            reviewed_at = CASE WHEN ? = 1 THEN ? ELSE reviewed_at END
        WHERE application_id = ? AND status = ?`)
        .bind(
          payload.status,
          timestamp,
          ['UNDER_REVIEW', 'APPROVED', 'REJECTED'].includes(payload.status) ? 1 : 0,
          timestamp,
          applicationId,
          application.status,
        ),
      env.BETA_DB.prepare(`INSERT INTO beta_audit_events
        (event_id, application_id, event_type, event_timestamp, actor_reference,
         old_status, new_status, metadata_json)
        SELECT ?, ?, 'OPERATOR_STATUS_SYNC', ?, 'operator-status-sync', ?, ?, ?
        WHERE changes() = 1`)
        .bind(
          eventId,
          applicationId,
          timestamp,
          application.status,
          payload.status,
          metadata,
        ),
    ]);
  } catch {
    return jsonResponse(503, {error: {code: 'service_unavailable'}});
  }

  if (results?.[0]?.meta?.changes === 1) {
    return responseForState(applicationId, payload.status, 'updated');
  }
  if (results?.[0]?.meta?.changes !== 0) {
    return jsonResponse(503, {error: {code: 'service_unavailable'}});
  }
  try {
    application = await env.BETA_DB.prepare(
      'SELECT status FROM beta_applications WHERE application_id = ?'
    ).bind(applicationId).first();
  } catch {
    return jsonResponse(503, {error: {code: 'service_unavailable'}});
  }
  if (application?.status === payload.status) {
    return responseForState(applicationId, payload.status, 'already_current');
  }
  return jsonResponse(409, {error: {code: 'status_conflict'}});
}
