import {buildJsonResponse, authRuntimeValidation, getValidatedSessionFromRequest} from './auth.js';
import {errorResponse, expectedOrigin} from './beta-registration.js';

const MAX_REQUEST_BYTES = 4096;
const DEFAULT_MAX_ACTIVE_DEVICES = 2;
const MAX_CONFIGURED_ACTIVE_DEVICES = 20;
const INSTALLATION_ID_PATTERN = /^dev_[0-9a-f]{32}$/;
const APP_VERSION_PATTERN = /^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$/;
const ACTIVATION_FIELDS = new Set(['installation_id', 'platform', 'architecture', 'app_version']);
const PUBLIC_ACTIVATION_STATUSES = new Set(['AUTHORIZED', 'FLAGGED', 'REVOKED']);

export function configuredMaxActiveDevices(env) {
  const raw = env.BETA_MAX_ACTIVE_DEVICES;
  if (raw === undefined || raw === null || raw === '') {
    return DEFAULT_MAX_ACTIVE_DEVICES;
  }
  if (!/^\d+$/.test(String(raw))) {
    return null;
  }
  const value = Number(raw);
  return Number.isSafeInteger(value)
    && value >= 1
    && value <= MAX_CONFIGURED_ACTIVE_DEVICES
    ? value
    : null;
}

function parseActivationPayload(rawText) {
  if (new TextEncoder().encode(rawText).byteLength > MAX_REQUEST_BYTES) {
    return {ok: false, response: errorResponse(413, 'request_too_large', 'Activation request is too large.')};
  }
  let payload;
  try {
    payload = JSON.parse(rawText);
  } catch {
    return {ok: false, response: errorResponse(400, 'invalid_json', 'Activation request must be valid JSON.')};
  }
  if (
    !payload
    || typeof payload !== 'object'
    || Array.isArray(payload)
    || Object.keys(payload).some((key) => !ACTIVATION_FIELDS.has(key) && key !== 'device_public_key_hash')
    || ![ACTIVATION_FIELDS.size, ACTIVATION_FIELDS.size + 1].includes(Object.keys(payload).length)
    || [...ACTIVATION_FIELDS].some((field) => !(field in payload))
  ) {
    return {ok: false, response: errorResponse(400, 'invalid_payload', 'Activation request contains unsupported fields.')};
  }
  if (
    typeof payload.installation_id !== 'string'
    || !INSTALLATION_ID_PATTERN.test(payload.installation_id)
    || typeof payload.platform !== 'string'
    || !['windows', 'linux'].includes(payload.platform)
    || typeof payload.architecture !== 'string'
    || payload.architecture !== 'x86_64'
    || typeof payload.app_version !== 'string'
    || payload.app_version.length > 64
    || !APP_VERSION_PATTERN.test(payload.app_version)
  ) {
    return {ok: false, response: errorResponse(400, 'invalid_activation_facts', 'Activation details are invalid or unsupported.')};
  }
  if ('device_public_key_hash' in payload && (
    typeof payload.device_public_key_hash !== 'string'
    || !/^[0-9a-f]{64}$/.test(payload.device_public_key_hash)
    || payload.installation_id !== `dev_${payload.device_public_key_hash.slice(0, 32)}`
  )) {
    return {ok: false, response: errorResponse(400, 'invalid_device_identity', 'Full device public-key hash must match the installation ID.')};
  }
  return {ok: true, value: payload};
}

async function readBoundedRequestBody(request) {
  const reader = request.body?.getReader();
  if (!reader) {
    return {ok: false, tooLarge: false};
  }
  const chunks = [];
  let totalBytes = 0;
  try {
    while (true) {
      const {done, value} = await reader.read();
      if (done) {
        break;
      }
      totalBytes += value.byteLength;
      if (totalBytes > MAX_REQUEST_BYTES) {
        await reader.cancel();
        return {ok: false, tooLarge: true};
      }
      chunks.push(value);
    }
  } catch {
    return {ok: false, tooLarge: false};
  }
  const bytes = new Uint8Array(totalBytes);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  try {
    return {ok: true, text: new TextDecoder('utf-8', {fatal: true}).decode(bytes)};
  } catch {
    return {ok: false, tooLarge: false};
  }
}

function userActivationPayload(row) {
  return {
    activation_request_id: row.activation_request_id,
    installation_id: row.installation_id,
    platform: row.platform,
    architecture: row.architecture,
    app_version: row.app_version,
    status: row.status,
    created_at: row.created_at,
    authorized_at: row.authorized_at,
  };
}

export async function handleActivationRequest(request, env, method) {
  const runtime = authRuntimeValidation(env);
  if (!runtime.ok || !env.BETA_DB) {
    return errorResponse(503, 'service_unavailable', 'Beta activation is temporarily unavailable.');
  }
  const session = await getValidatedSessionFromRequest(request, env);
  if (!session.ok) {
    return errorResponse(401, 'authentication_required', 'Sign in to manage beta device activation.');
  }
  if (method === 'GET') {
    try {
      const result = await env.BETA_DB.prepare(
        `SELECT activation_request_id, installation_id, platform, architecture,
                app_version, status, created_at, authorized_at
         FROM beta_activations
         WHERE user_id = ?
         ORDER BY created_at ASC, activation_request_id ASC
         LIMIT 100`,
      ).bind(session.userId).all();
      return buildJsonResponse(200, {
        activations: (result.results ?? []).map(userActivationPayload),
      });
    } catch {
      return errorResponse(503, 'service_unavailable', 'Beta activation is temporarily unavailable.');
    }
  }
  if (method !== 'POST') {
    return errorResponse(405, 'method_not_allowed', 'Method not allowed.');
  }

  const origin = request.headers.get('Origin');
  if (!expectedOrigin(env) || origin !== expectedOrigin(env)) {
    return errorResponse(403, 'origin_denied', 'This request origin is not allowed.');
  }
  if (request.headers.get('Content-Type')?.split(';', 1)[0].trim().toLowerCase() !== 'application/json') {
    return errorResponse(415, 'unsupported_media_type', 'Send JSON content.');
  }
  const contentLength = request.headers.get('Content-Length');
  if (contentLength && contentLength.trim() && Number(contentLength) > MAX_REQUEST_BYTES) {
    return errorResponse(413, 'request_too_large', 'Activation request is too large.');
  }
  const body = await readBoundedRequestBody(request);
  if (!body.ok && body.tooLarge) {
    return errorResponse(413, 'request_too_large', 'Activation request is too large.');
  }
  if (!body.ok) {
    return errorResponse(400, 'invalid_json', 'Activation request must be valid JSON.');
  }
  const parsed = parseActivationPayload(body.text);
  if (!parsed.ok) {
    return parsed.response;
  }
  const maxDevices = configuredMaxActiveDevices(env);
  if (maxDevices === null) {
    return errorResponse(503, 'service_unavailable', 'Beta activation is temporarily unavailable.');
  }

  let application;
  try {
    application = await env.BETA_DB.prepare(
      'SELECT application_id, status, licence_expires_at FROM beta_applications WHERE user_id = ? LIMIT 1',
    ).bind(session.userId).first();
  } catch {
    return errorResponse(503, 'service_unavailable', 'Beta activation is temporarily unavailable.');
  }
  if (!application) {
    return errorResponse(403, 'application_required', 'A linked beta application is required for device activation.');
  }

  const now = new Date().toISOString();
  const requestId = crypto.randomUUID();
  const {installation_id: installationId, platform, architecture, app_version: appVersion} = parsed.value;
  try {
    await env.BETA_DB.prepare(`
      INSERT INTO beta_activations (
        activation_request_id, user_id, application_id, installation_id, platform,
        architecture, app_version, status, flag_reason, created_at, updated_at,
        authorized_at, revoked_at, device_public_key_hash
      )
      SELECT ?, app.user_id, app.application_id, ?, ?, ?, ?,
        CASE
          WHEN app.status = 'APPROVED'
            OR (app.status = 'LICENSE_ISSUED' AND app.licence_expires_at > ?)
          THEN CASE WHEN (
            SELECT COUNT(*) FROM beta_activations active
            WHERE active.user_id = app.user_id
              AND active.status = 'AUTHORIZED'
              AND active.installation_id <> ?
          ) < ? THEN 'AUTHORIZED' ELSE 'FLAGGED' END
          ELSE 'FLAGGED'
        END,
        CASE
          WHEN app.status = 'APPROVED'
            OR (app.status = 'LICENSE_ISSUED' AND app.licence_expires_at > ?)
          THEN CASE WHEN (
            SELECT COUNT(*) FROM beta_activations active
            WHERE active.user_id = app.user_id
              AND active.status = 'AUTHORIZED'
              AND active.installation_id <> ?
          ) < ? THEN NULL ELSE 'DEVICE_LIMIT' END
          ELSE 'APPLICATION_NOT_ELIGIBLE'
        END,
        ?, ?, CASE
          WHEN app.status = 'APPROVED'
            OR (app.status = 'LICENSE_ISSUED' AND app.licence_expires_at > ?)
          THEN CASE WHEN (
            SELECT COUNT(*) FROM beta_activations active
            WHERE active.user_id = app.user_id
              AND active.status = 'AUTHORIZED'
              AND active.installation_id <> ?
          ) < ? THEN ? ELSE NULL END
          ELSE NULL
        END,
        NULL, ?
      FROM beta_applications app
      WHERE app.user_id = ? AND 1 = 1
      LIMIT 1
      ON CONFLICT(user_id, installation_id) DO UPDATE SET
        device_public_key_hash = COALESCE(beta_activations.device_public_key_hash, excluded.device_public_key_hash),
        platform = excluded.platform,
        architecture = excluded.architecture,
        app_version = excluded.app_version,
        status = CASE WHEN beta_activations.status = 'REVOKED'
          THEN 'REVOKED' ELSE excluded.status END,
        flag_reason = CASE WHEN beta_activations.status = 'REVOKED'
          THEN 'INSTALLATION_REVOKED' ELSE excluded.flag_reason END,
        updated_at = excluded.updated_at,
        authorized_at = CASE
          WHEN beta_activations.status = 'REVOKED' THEN beta_activations.authorized_at
          WHEN excluded.status = 'AUTHORIZED'
            THEN COALESCE(beta_activations.authorized_at, excluded.authorized_at)
          ELSE NULL
        END
      WHERE (beta_activations.device_public_key_hash IS NULL
        OR excluded.device_public_key_hash IS NULL
        OR beta_activations.device_public_key_hash = excluded.device_public_key_hash)
        AND (beta_activations.status <> excluded.status
        OR beta_activations.flag_reason IS NOT excluded.flag_reason
        OR beta_activations.platform <> excluded.platform
        OR beta_activations.architecture <> excluded.architecture
        OR beta_activations.app_version <> excluded.app_version
        OR (beta_activations.device_public_key_hash IS NULL AND excluded.device_public_key_hash IS NOT NULL))
    `).bind(
      requestId,
      installationId,
      platform,
      architecture,
      appVersion,
      now,
      installationId,
      maxDevices,
      now,
      installationId,
      maxDevices,
      now,
      now,
      now,
      installationId,
      maxDevices,
      now,
      parsed.value.device_public_key_hash ?? null,
      session.userId,
    ).run();
    const activation = await env.BETA_DB.prepare(
      `SELECT activation_request_id, installation_id, platform, architecture,
              app_version, status, created_at, updated_at, authorized_at, device_public_key_hash
       FROM beta_activations
       WHERE user_id = ? AND installation_id = ?`,
    ).bind(session.userId, installationId).first();
    if (!activation || !PUBLIC_ACTIVATION_STATUSES.has(activation.status)) {
      return errorResponse(403, 'application_required', 'A linked beta application is required for device activation.');
    }
    if (parsed.value.device_public_key_hash && activation.device_public_key_hash !== parsed.value.device_public_key_hash) {
      return errorResponse(409, 'device_identity_conflict', 'The installation already has a different public device identity.');
    }
    return buildJsonResponse(200, {
      activation: userActivationPayload(activation),
      message: activation.status === 'FLAGGED'
        ? 'Activation needs additional review. Please contact Quantum Studio support.'
        : undefined,
    });
  } catch {
    return errorResponse(503, 'service_unavailable', 'Beta activation is temporarily unavailable.');
  }
}
