import {authRuntimeValidation, getValidatedSessionFromRequest, sha256Hex, buildJsonResponse} from './auth.js';
import {expectedOrigin, errorResponse} from './beta-registration.js';
import {parseActivationPayload, registerActivationForUser} from './beta-activation.js';
import {constantTimeEquals} from './operator-auth.js';

const TTL = 300;
const INTERVAL = 3;
const opaque = /^[0-9a-f]{64}$/;
const randomCode = () => Array.from(crypto.getRandomValues(new Uint8Array(32)), (b) => b.toString(16).padStart(2, '0')).join('');
const fail = (status, code) => errorResponse(status, code, {
  authentication_required: 'Sign in on the website to confirm this device.',
  invalid_challenge: 'This desktop activation challenge is invalid.',
  challenge_expired: 'This desktop activation challenge expired. Start again in Quantum Studio.',
  challenge_used: 'This challenge has already been completed or cancelled.',
  origin_denied: 'This request origin is not allowed.',
  slow_down: 'Wait before polling again.',
  rate_limited: 'Too many activation attempts. Please wait before starting again.',
}[code] || 'Desktop activation could not be completed. Start again in Quantum Studio.');

async function readBody(request) {
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
      if (size > 4096) { await reader.cancel(); return null; }
      chunks.push(value);
    }
    const bytes = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
    return JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(bytes));
  } catch { return null; }
}

function exact(body, fields) {
  return body && typeof body === 'object' && !Array.isArray(body)
    && Object.keys(body).length === fields.length && fields.every((key) => Object.hasOwn(body, key));
}

export async function handleDesktopAuth(request, env, action) {
  env = env || {};
  const origin = expectedOrigin(env);
  if (!env?.BETA_DB || !origin || !authRuntimeValidation(env).ok) return fail(503, 'service_unavailable');
  if (env.BETA_ENVIRONMENT === 'production' && new URL(request.url).protocol !== 'https:') return fail(403, 'https_required');
  const suppliedOrigin = request.headers.get('Origin');
  const browser = action === 'confirm' || action === 'details';
  if ((action === 'confirm' && suppliedOrigin !== origin) || (suppliedOrigin && suppliedOrigin !== origin)) return fail(403, 'origin_denied');
  const now = Math.floor(Date.now() / 1000);
  try {
    if (action === 'start') {
      const facts = await readBody(request);
      const parsed = parseActivationPayload(JSON.stringify(facts));
      if (!parsed.ok || !facts?.device_public_key_hash) return fail(400, 'invalid_device_identity');
      // Atomic fixed-window quota. The edge supplies CF-Connecting-IP; no raw IP is stored.
      const ip = request.headers.get('CF-Connecting-IP') || 'local';
      const key = await sha256Hex(`desktop-start:${env.BETA_IDENTITY_PEPPER || ''}:${ip}`);
      const window = now - now % TTL;
      const quota = await env.BETA_DB.prepare(`INSERT INTO desktop_auth_rate_limits(bucket_key, window_start, attempts)
        VALUES(?, ?, 1) ON CONFLICT(bucket_key) DO UPDATE SET
        attempts = CASE WHEN window_start = excluded.window_start THEN attempts + 1 ELSE 1 END,
        window_start = excluded.window_start RETURNING attempts`).bind(key, window).first();
      if (!quota || quota.attempts > 10) return fail(429, 'rate_limited');
      // Bounded opportunistic cleanup retains terminal states for one day.
      await env.BETA_DB.prepare(`DELETE FROM desktop_auth_challenges WHERE challenge_id IN
        (SELECT challenge_id FROM desktop_auth_challenges WHERE expires_at < ? LIMIT 100)`).bind(now - 86400).run();
      await env.BETA_DB.prepare(`DELETE FROM desktop_auth_rate_limits WHERE bucket_key IN
        (SELECT bucket_key FROM desktop_auth_rate_limits WHERE window_start < ? LIMIT 100)`).bind(window - TTL).run();
      const id = randomCode();
      const deviceCode = randomCode();
      await env.BETA_DB.prepare(`INSERT INTO desktop_auth_challenges
        (challenge_id, device_code_hash, facts_json, state, created_at, expires_at, next_poll_at)
        VALUES(?, ?, ?, 'PENDING', ?, ?, ?)`).bind(id, await sha256Hex(deviceCode), JSON.stringify(parsed.value), now, now + TTL, now).run();
      return buildJsonResponse(200, {challenge_id: id, device_code: deviceCode,
        verification_url: `${origin}/desktop-auth?challenge=${id}`, expires_in: TTL, interval: INTERVAL});
    }
    let body;
    if (action === 'details') {
      body = {challenge_id: new URL(request.url).searchParams.get('challenge')};
    } else {
      body = await readBody(request);
    }
    if (!exact(body, browser ? ['challenge_id'] : ['challenge_id', 'device_code'])
        || typeof body.challenge_id !== 'string' || !opaque.test(body.challenge_id)
        || (!browser && (typeof body.device_code !== 'string' || !opaque.test(body.device_code)))) return fail(400, 'invalid_challenge');
    if (browser) {
      const session = await getValidatedSessionFromRequest(request, env);
      if (!session.ok) return fail(401, 'authentication_required');
      body.userId = session.userId; // Never supplied by the browser body.
    }
    const row = await env.BETA_DB.prepare('SELECT * FROM desktop_auth_challenges WHERE challenge_id = ?').bind(body.challenge_id).first();
    if (!row || (!browser && !constantTimeEquals(await sha256Hex(body.device_code), row.device_code_hash))) return fail(400, 'invalid_challenge');
    if (now >= row.expires_at) {
      await env.BETA_DB.prepare(`UPDATE desktop_auth_challenges SET state = 'EXPIRED'
        WHERE challenge_id = ? AND state NOT IN ('CONSUMED','CANCELLED')`).bind(body.challenge_id).run();
      return browser ? fail(410, 'challenge_expired') : buildJsonResponse(200, {state: 'expired'});
    }
    if (action === 'details') {
      if (row.state !== 'PENDING') return fail(409, 'challenge_used');
      const facts = JSON.parse(row.facts_json);
      return buildJsonResponse(200, {state: 'pending', installation_id: facts.installation_id,
        platform: facts.platform, app_version: facts.app_version, expires_at: row.expires_at});
    }
    if (action === 'confirm') {
      const claim = await env.BETA_DB.prepare(`UPDATE desktop_auth_challenges SET state = 'PROCESSING'
        WHERE challenge_id = ? AND state = 'PENDING' AND expires_at > ?`).bind(body.challenge_id, now).run();
      if (claim.meta?.changes !== 1) return fail(409, 'challenge_used');
      const response = await registerActivationForUser(env, body.userId, JSON.parse(row.facts_json));
      const result = await response.json();
      const activation = result.activation;
      const safe = response.ok && activation ? {activation_request_id: activation.activation_request_id,
        installation_id: activation.installation_id, status: activation.status} : null;
      const finishedAt = Math.floor(Date.now() / 1000);
      const completed = await env.BETA_DB.prepare(`UPDATE desktop_auth_challenges
        SET state = ?, result_json = ?, completed_at = ?
        WHERE challenge_id = ? AND state = 'PROCESSING' AND expires_at > ?`).bind(
        safe ? 'COMPLETED' : 'FAILED', safe ? JSON.stringify(safe) : null, finishedAt, body.challenge_id, finishedAt).run();
      if (completed.meta?.changes !== 1) return fail(409, 'challenge_used');
      return safe ? buildJsonResponse(200, {state: 'completed'}) : fail(response.status, 'activation_failed');
    }
    if (action === 'cancel') {
      const cancelled = await env.BETA_DB.prepare(`UPDATE desktop_auth_challenges SET state = 'CANCELLED'
        WHERE challenge_id = ? AND state IN ('PENDING','PROCESSING','COMPLETED')`).bind(body.challenge_id).run();
      return cancelled.meta?.changes === 1 || row.state === 'CANCELLED'
        ? buildJsonResponse(200, {state: 'cancelled'}) : fail(409, 'challenge_used');
    }
    if (['CONSUMED', 'CANCELLED', 'FAILED'].includes(row.state)) return buildJsonResponse(200, {state: row.state.toLowerCase()});
    const polled = await env.BETA_DB.prepare(`UPDATE desktop_auth_challenges SET next_poll_at = ?
      WHERE challenge_id = ? AND next_poll_at <= ? AND state IN ('PENDING','PROCESSING','COMPLETED')`).bind(now + INTERVAL, body.challenge_id, now).run();
    if (polled.meta?.changes !== 1) return fail(429, 'slow_down');
    if (row.state !== 'COMPLETED') return buildJsonResponse(200, {state: 'pending'});
    const consumed = await env.BETA_DB.prepare(`UPDATE desktop_auth_challenges SET state = 'CONSUMED', consumed_at = ?
      WHERE challenge_id = ? AND state = 'COMPLETED' AND expires_at > ?`).bind(now, body.challenge_id, now).run();
    if (consumed.meta?.changes !== 1) return fail(409, 'challenge_used');
    return buildJsonResponse(200, {state: 'completed', activation: JSON.parse(row.result_json)});
  } catch {
    return fail(503, 'service_unavailable');
  }
}
