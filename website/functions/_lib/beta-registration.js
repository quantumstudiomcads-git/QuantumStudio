const MAX_BODY_BYTES = 16_384;
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const OPERATING_SYSTEMS = new Set(['Windows', 'Linux', 'Both', 'Other']);
const FIELD_LIMITS = Object.freeze({fullName: 120, email: 254, institution: 160, country: 100, researchArea: 1500, operatingSystem: 32, academicRole: 120, evaluationDescription: 2000, turnstileToken: 2048});
const ALLOWED_FIELDS = new Set(['fullName', 'email', 'institution', 'country', 'researchArea', 'operatingSystem', 'academicRole', 'evaluationDescription', 'privacyAccepted', 'termsAccepted', 'communicationsAccepted', 'turnstileToken']);
const TURNSTILE_ENDPOINT = 'https://challenges.cloudflare.com/turnstile/v0/siteverify';

export function normalizeText(value) { return typeof value === 'string' ? value.trim().replace(/\s+/g, ' ') : ''; }

export function jsonResponse(status, payload, origin) {
  const headers = new Headers({'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer', 'Cross-Origin-Resource-Policy': 'same-site'});
  if (origin) { headers.set('Access-Control-Allow-Origin', origin); headers.set('Vary', 'Origin'); }
  return new Response(JSON.stringify(payload), {status, headers});
}

export function errorResponse(status, code, message, origin) { return jsonResponse(status, {error: {code, message}}, origin); }

export function expectedOrigin(env) {
  const value = normalizeText(env.BETA_ALLOWED_ORIGIN);
  if (!value) return null;
  try { const parsed = new URL(value); return parsed.origin === value.replace(/\/$/, '') ? parsed.origin : null; } catch { return null; }
}

export function validateRuntimeConfig(env) {
  const production = env.BETA_ENVIRONMENT === 'production';
  const origin = expectedOrigin(env);
  if (!origin || !normalizeText(env.BETA_PRIVACY_VERSION) || !normalizeText(env.BETA_TERMS_VERSION) || !normalizeText(env.BETA_IDENTITY_PEPPER)) return {ok: false, production};
  if (production && (!normalizeText(env.TURNSTILE_SECRET_KEY) || env.BETA_TURNSTILE_TEST_MODE === 'true')) return {ok: false, production};
  return {ok: true, production, origin};
}

export function validateApplication(raw) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {ok: false, errors: {body: 'A JSON object is required.'}};
  const unknown = Object.keys(raw).filter((key) => !ALLOWED_FIELDS.has(key));
  if (unknown.length) return {ok: false, errors: {body: 'Unexpected field.'}};
  const value = {
    fullName: normalizeText(raw.fullName), email: normalizeText(raw.email).toLowerCase(), institution: normalizeText(raw.institution), country: normalizeText(raw.country),
    researchArea: normalizeText(raw.researchArea), operatingSystem: normalizeText(raw.operatingSystem), academicRole: normalizeText(raw.academicRole),
    evaluationDescription: normalizeText(raw.evaluationDescription), turnstileToken: normalizeText(raw.turnstileToken),
    privacyAccepted: raw.privacyAccepted === true, termsAccepted: raw.termsAccepted === true, communicationsAccepted: raw.communicationsAccepted === true,
  };
  const errors = {};
  for (const field of ['fullName', 'email', 'institution', 'country', 'researchArea', 'operatingSystem', 'turnstileToken']) if (!value[field]) errors[field] = 'Required.';
  for (const [field, limit] of Object.entries(FIELD_LIMITS)) if (value[field] && value[field].length > limit) errors[field] = `Must be ${limit} characters or fewer.`;
  if (value.email && !EMAIL_PATTERN.test(value.email)) errors.email = 'Invalid email address.';
  if (value.operatingSystem && !OPERATING_SYSTEMS.has(value.operatingSystem)) errors.operatingSystem = 'Invalid operating system.';
  if (!value.privacyAccepted) errors.privacyAccepted = 'Privacy consent is required.';
  if (!value.termsAccepted) errors.termsAccepted = 'Beta terms consent is required.';
  return Object.keys(errors).length ? {ok: false, errors} : {ok: true, value};
}

export async function emailLookupHash(normalizedEmail, pepper) {
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(pepper), {name: 'HMAC', hash: 'SHA-256'}, false, ['sign']);
  const digest = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(normalizedEmail));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
}

export async function verifyTurnstile(token, env, request, fetchImpl = fetch, expectedAction = 'beta_registration') {
  if (!token || token.length > FIELD_LIMITS.turnstileToken) return {ok: false, reason: 'missing-or-invalid-token'};
  if (env.BETA_TURNSTILE_TEST_MODE === 'true' && env.BETA_ENVIRONMENT !== 'production') {
    if (token === 'test-pass') return {ok: true};
    if (token === 'test-hostname-mismatch') return {ok: false, reason: 'hostname-mismatch'};
    if (token === 'test-action-mismatch') return {ok: false, reason: 'action-mismatch'};
    return {ok: false, reason: 'timeout-or-duplicate'};
  }
  const secret = normalizeText(env.TURNSTILE_SECRET_KEY);
  const expected = expectedOrigin(env);
  if (!secret || !expected) return {ok: false, reason: 'verification-unavailable'};
  try {
    const form = new URLSearchParams({secret, response: token, idempotency_key: crypto.randomUUID()});
    const result = await fetchImpl(TURNSTILE_ENDPOINT, {method: 'POST', headers: {'Content-Type': 'application/x-www-form-urlencoded'}, body: form.toString()});
    if (!result.ok) return {ok: false, reason: 'verification-unavailable'};
    const body = await result.json();
    if (!body.success) return {ok: false, reason: Array.isArray(body['error-codes']) ? body['error-codes'][0] || 'invalid-token' : 'invalid-token'};
    if (body.hostname !== new URL(expected).hostname) return {ok: false, reason: 'hostname-mismatch'};
    if (body.action !== expectedAction) return {ok: false, reason: 'action-mismatch'};
    return {ok: true};
  } catch { return {ok: false, reason: 'verification-unavailable'}; }
}

function duplicateError(error) { return String(error?.message || error).toLowerCase().includes('unique'); }
function userApplicationDuplicateError(error) {
  return String(error?.message || error).toLowerCase().includes('beta_applications.user_id');
}

export async function handleApplicationPost(request, env, dependencies = {}) {
  const config = validateRuntimeConfig(env);
  if (!config.ok) return errorResponse(503, 'service_unavailable', 'Beta registration is temporarily unavailable.');
  const origin = request.headers.get('Origin');
  if (origin !== config.origin) return errorResponse(403, 'origin_denied', 'This request origin is not allowed.');
  if (typeof dependencies.userId !== 'string' || !dependencies.userId) {
    return errorResponse(401, 'authentication_required', 'Sign in before submitting a beta application.', config.origin);
  }
  if (!request.headers.get('Content-Type')?.toLowerCase().startsWith('application/json')) return errorResponse(415, 'unsupported_media_type', 'Send JSON content.', config.origin);
  const contentLength = Number(request.headers.get('Content-Length') || '0');
  if (Number.isFinite(contentLength) && contentLength > MAX_BODY_BYTES) return errorResponse(413, 'request_too_large', 'Request is too large.', config.origin);
  let rawText;
  try { rawText = await request.text(); } catch { return errorResponse(400, 'invalid_json', 'Invalid JSON request.', config.origin); }
  if (new TextEncoder().encode(rawText).byteLength > MAX_BODY_BYTES) return errorResponse(413, 'request_too_large', 'Request is too large.', config.origin);
  let raw;
  try { raw = JSON.parse(rawText); } catch { return errorResponse(400, 'invalid_json', 'Invalid JSON request.', config.origin); }
  const validated = validateApplication(raw);
  if (!validated.ok) return errorResponse(400, 'validation_failed', 'Application details need correction.', config.origin);
  try {
    const currentApplication = await env.BETA_DB.prepare(
      'SELECT application_id FROM beta_applications WHERE user_id = ? LIMIT 1',
    ).bind(dependencies.userId).first();
    if (currentApplication) {
      return errorResponse(409, 'application_exists', 'Your beta application has already been submitted.', config.origin);
    }
  } catch {
    return errorResponse(503, 'service_unavailable', 'Beta registration is temporarily unavailable. Please try again later.', config.origin);
  }
  const turnstile = await (dependencies.verifyTurnstile || verifyTurnstile)(validated.value.turnstileToken, env, request);
  if (!turnstile.ok) return errorResponse(400, 'verification_failed', 'Verification expired or failed. Please try again.', config.origin);
  const applicationId = crypto.randomUUID();
  const now = new Date().toISOString();
  const hash = await emailLookupHash(validated.value.email, env.BETA_IDENTITY_PEPPER);
  try {
    const insertApplication = env.BETA_DB.prepare(`INSERT INTO beta_applications (application_id, full_name, email, normalized_email, email_lookup_hash, institution, country, academic_role, research_area, intended_evaluation, operating_system, privacy_consent, privacy_version, terms_consent, terms_version, communications_consent, status, submitted_at, updated_at, user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, 1, ?, ?, 'APPLIED', ?, ?, ?)`)
      .bind(applicationId, validated.value.fullName, validated.value.email, validated.value.email, hash, validated.value.institution, validated.value.country, validated.value.academicRole || null, validated.value.researchArea, validated.value.evaluationDescription || null, validated.value.operatingSystem, env.BETA_PRIVACY_VERSION, env.BETA_TERMS_VERSION, validated.value.communicationsAccepted ? 1 : 0, now, now, dependencies.userId);
    const insertAudit = env.BETA_DB.prepare(`INSERT INTO beta_audit_events (event_id, application_id, event_type, event_timestamp, actor_reference, old_status, new_status, metadata_json) VALUES (?, ?, 'APPLICATION_SUBMITTED', ?, 'public-registration', NULL, 'APPLIED', ?)`)
      .bind(crypto.randomUUID(), applicationId, now, JSON.stringify({schema: 1}));
    await env.BETA_DB.batch([insertApplication, insertAudit]);
  } catch (error) {
    if (userApplicationDuplicateError(error)) {
      return errorResponse(409, 'application_exists', 'Your beta application has already been submitted.', config.origin);
    }
    if (duplicateError(error)) return jsonResponse(202, {accepted: true, applicationId: null, message: 'Your application is queued for review. We will contact you if access is approved.'}, config.origin);
    return errorResponse(503, 'service_unavailable', 'Beta registration is temporarily unavailable. Please try again later.', config.origin);
  }
  return jsonResponse(202, {accepted: true, applicationId, message: 'Your application is queued for manual review. We will contact you if access is approved.'}, config.origin);
}

export function handleOptions(request, env) {
  const origin = request.headers.get('Origin'); const expected = expectedOrigin(env);
  if (!expected || origin !== expected) return new Response(null, {status: 403});
  return new Response(null, {status: 204, headers: {'Access-Control-Allow-Origin': expected, 'Access-Control-Allow-Methods': 'POST, OPTIONS', 'Access-Control-Allow-Headers': 'Content-Type', 'Access-Control-Max-Age': '600', 'Vary': 'Origin'}});
}
