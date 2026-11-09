import {persistLicenceMetadata} from '../../../../_lib/licence-metadata.js';
import {isLocalDeployment} from '../../../../_lib/deployment.js';
import {constantTimeEquals, getBearerToken} from '../../../../_lib/operator-auth.js';

const MAX_BYTES = 4096;
const fields = ['schema_version', 'installation_id', 'licence_id', 'status', 'issued_at', 'expires_at', 'revoked_at'];
const uuid = '[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}';
const json = (status, body) => new Response(JSON.stringify(body), {status, headers: {
  'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store',
  'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
}});
const fail = (status, code) => json(status, {error: {code}});
const timestamp = (value) => typeof value === 'string'
  && /(?:Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value));

async function readJson(request) {
  const reader = request.body?.getReader();
  if (!reader) return null;
  let size = 0;
  const chunks = [];
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

export async function onRequestPost({request, env, params}) {
  if (!isLocalDeployment(env)) return fail(403, 'test_only');
  if (!env?.BETA_DB) return fail(503, 'service_unavailable');
  const configured = typeof env.OPERATOR_LICENCE_SYNC_TOKEN === 'string' ? env.OPERATOR_LICENCE_SYNC_TOKEN.trim() : '';
  if (!configured) return fail(503, 'service_unavailable');
  const bearer = getBearerToken(request);
  if (!bearer) return fail(401, 'unauthorized');
  if (!constantTimeEquals(bearer, configured)) return fail(403, 'forbidden');
  if (request.headers.get('Content-Type')?.split(';', 1)[0].trim().toLowerCase() !== 'application/json') {
    return fail(415, 'unsupported_media_type');
  }
  const activationId = params?.activationId;
  if (typeof activationId !== 'string' || !new RegExp(`^${uuid}$`, 'i').test(activationId)) return fail(400, 'invalid_activation_id');
  const body = await readJson(request);
  if (!body || typeof body !== 'object' || Array.isArray(body)
      || Object.keys(body).length !== fields.length || fields.some((field) => !(field in body))
      || body.schema_version !== 1
      || typeof body.installation_id !== 'string' || !/^dev_[0-9a-f]{32}$/.test(body.installation_id)
      || typeof body.licence_id !== 'string' || !new RegExp(`^lic_${uuid}$`).test(body.licence_id)
      || body.status !== 'ISSUED' || !timestamp(body.issued_at) || !timestamp(body.expires_at)
      || Date.parse(body.expires_at) <= Date.parse(body.issued_at) || body.revoked_at !== null) {
    return fail(400, 'invalid_metadata');
  }
  return persistLicenceMetadata(env, activationId, body);
}
