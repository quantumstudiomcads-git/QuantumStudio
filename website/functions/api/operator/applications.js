import {APPLICATION_STATUSES} from '../../_lib/workflow.js';
import {constantTimeEquals, getBearerToken} from '../../_lib/operator-auth.js';

const JSON_HEADERS = Object.freeze({
  'Content-Type': 'application/json; charset=utf-8',
  'Cache-Control': 'no-store',
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'no-referrer',
  'Cross-Origin-Resource-Policy': 'same-site',
});
const MAX_EXPORT_APPLICATIONS = 1000;
const MAX_EXPORT_BYTES = 2 * 1024 * 1024;

function jsonResponse(status, payload, extraHeaders = {}) {
  const headers = new Headers(JSON_HEADERS);
  for (const [name, value] of Object.entries(extraHeaders)) {
    headers.set(name, value);
  }
  return new Response(JSON.stringify(payload), {status, headers});
}

export async function onRequestGet(context) {
  const {request, env} = context;
  if (!env || !env.BETA_DB) {
    return jsonResponse(503, {error: {code: 'service_unavailable', message: 'Beta application export is temporarily unavailable.'}});
  }
  const url = new URL(request.url);
  if (env.BETA_ENVIRONMENT === 'production' && url.protocol !== 'https:') {
    return jsonResponse(403, {error: {code: 'https_required', message: 'HTTPS is required.'}});
  }
  const configuredToken = typeof env.OPERATOR_SYNC_TOKEN === 'string' ? env.OPERATOR_SYNC_TOKEN.trim() : '';
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

  const hasStatusFilter = url.searchParams.has('status');
  const requestedStatus = url.searchParams.get('status');
  if (hasStatusFilter && !APPLICATION_STATUSES.includes(requestedStatus)) {
    return jsonResponse(400, {error: {code: 'invalid_status', message: 'Unsupported status filter.'}});
  }

  const SELECT_FIELDS = [
    'application_id', 'full_name', 'email', 'institution', 'country', 'academic_role',
    'research_area', 'intended_evaluation', 'operating_system', 'privacy_consent', 'privacy_version',
    'terms_consent', 'terms_version', 'communications_consent', 'status', 'submitted_at', 'updated_at',
    'reviewed_at', 'review_note', 'licence_id', 'licence_issued_at', 'licence_expires_at', 'revoked_at',
  ];

  let query = `SELECT ${SELECT_FIELDS.join(', ')} FROM beta_applications`;
  const bindings = [];
  if (hasStatusFilter) {
    query += ' WHERE status = ?';
    bindings.push(requestedStatus);
  }
  query += ` ORDER BY submitted_at ASC, application_id ASC LIMIT ${MAX_EXPORT_APPLICATIONS + 1}`;

  let dbRows;
  try {
    const result = await env.BETA_DB.prepare(query).bind(...bindings).all();
    dbRows = Array.isArray(result.results) ? result.results : [];
  } catch {
    return jsonResponse(503, {error: {code: 'service_unavailable', message: 'Unable to read beta applications.'}});
  }
  if (dbRows.length > MAX_EXPORT_APPLICATIONS) {
    return jsonResponse(413, {error: {code: 'export_too_large', message: 'Application export exceeds the configured limit.'}});
  }

  const applications = dbRows.map((row) => ({
    application_id: row.application_id ?? null,
    full_name: row.full_name ?? null,
    email: row.email ?? null,
    institution: row.institution ?? null,
    country: row.country ?? null,
    academic_role: row.academic_role ?? '',
    research_area: row.research_area ?? null,
    intended_evaluation: row.intended_evaluation ?? '',
    operating_system: row.operating_system ?? null,
    privacy_consent: row.privacy_consent ?? null,
    privacy_version: row.privacy_version ?? null,
    terms_consent: row.terms_consent ?? null,
    terms_version: row.terms_version ?? null,
    communications_consent: row.communications_consent ?? null,
    status: row.status ?? null,
    submitted_at: row.submitted_at ?? null,
    updated_at: row.updated_at ?? null,
    reviewed_at: row.reviewed_at ?? null,
    review_note: row.review_note ?? null,
    licence_id: row.licence_id ?? null,
    licence_issued_at: row.licence_issued_at ?? null,
    licence_expires_at: row.licence_expires_at ?? null,
    revoked_at: row.revoked_at ?? null,
  }));

  const payload = {schema_version: 1, applications};
  if (new TextEncoder().encode(JSON.stringify(payload)).length > MAX_EXPORT_BYTES) {
    return jsonResponse(413, {error: {code: 'export_too_large', message: 'Application export exceeds the configured limit.'}});
  }
  return jsonResponse(200, payload);
}

export function onRequestOptions() {
  return jsonResponse(204, null, {'Allow': 'GET, OPTIONS'});
}
