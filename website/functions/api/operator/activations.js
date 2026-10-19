import {constantTimeEquals, getBearerToken} from '../../_lib/operator-auth.js';

const JSON_HEADERS = Object.freeze({
  'Content-Type': 'application/json; charset=utf-8',
  'Cache-Control': 'no-store',
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'no-referrer',
  'Cross-Origin-Resource-Policy': 'same-site',
});
const MAX_EXPORT_ACTIVATIONS = 2000;
const MAX_EXPORT_BYTES = 512 * 1024;
const ACTIVATION_FIELDS = Object.freeze([
  'activation_request_id',
  'application_id',
  'installation_id',
  'platform',
  'architecture',
  'app_version',
  'status',
  'flag_reason',
  'created_at',
  'updated_at',
  'authorized_at',
  'revoked_at',
  'device_public_key_hash',
  'licence_id',
  'licence_status',
  'licence_issued_at',
  'licence_expires_at',
  'licence_revoked_at',
]);

function jsonResponse(status, payload) {
  return new Response(JSON.stringify(payload), {status, headers: JSON_HEADERS});
}

export async function onRequestGet({request, env}) {
  if (!env?.BETA_DB) {
    return jsonResponse(503, {error: {code: 'service_unavailable', message: 'Activation export is temporarily unavailable.'}});
  }
  const url = new URL(request.url);
  if (env.BETA_ENVIRONMENT === 'production' && url.protocol !== 'https:') {
    return jsonResponse(403, {error: {code: 'https_required', message: 'HTTPS is required.'}});
  }
  const configuredToken = typeof env.OPERATOR_SYNC_TOKEN === 'string'
    ? env.OPERATOR_SYNC_TOKEN.trim()
    : '';
  if (!configuredToken) {
    return jsonResponse(503, {error: {code: 'service_unavailable', message: 'Operator sync is not configured.'}});
  }
  const token = getBearerToken(request);
  if (!token) {
    return jsonResponse(401, {error: {code: 'unauthorized', message: 'Authentication required.'}});
  }
  if (!constantTimeEquals(token, configuredToken)) {
    return jsonResponse(403, {error: {code: 'forbidden', message: 'Authentication failed.'}});
  }

  let rows;
  try {
    const result = await env.BETA_DB.prepare(
      `SELECT ${ACTIVATION_FIELDS.join(', ')}
       FROM beta_activations
       ORDER BY created_at ASC, activation_request_id ASC
       LIMIT ${MAX_EXPORT_ACTIVATIONS + 1}`,
    ).all();
    rows = Array.isArray(result.results) ? result.results : [];
  } catch {
    return jsonResponse(503, {error: {code: 'service_unavailable', message: 'Unable to read beta activations.'}});
  }
  if (rows.length > MAX_EXPORT_ACTIVATIONS) {
    return jsonResponse(413, {error: {code: 'export_too_large', message: 'Activation export exceeds the configured limit.'}});
  }

  const activations = rows.map((row) => Object.fromEntries(
    ACTIVATION_FIELDS.map((field) => [field, row[field] ?? null]),
  ));
  const payload = {schema_version: 1, activations};
  if (new TextEncoder().encode(JSON.stringify(payload)).byteLength > MAX_EXPORT_BYTES) {
    return jsonResponse(413, {error: {code: 'export_too_large', message: 'Activation export exceeds the configured limit.'}});
  }
  return jsonResponse(200, payload);
}
