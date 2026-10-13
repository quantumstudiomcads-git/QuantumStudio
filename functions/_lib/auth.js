import {expectedOrigin, normalizeText, jsonResponse, errorResponse} from './beta-registration.js';
import {sendOtpEmail} from './email-delivery.js';

export const AUTH_SESSION_COOKIE = 'qs_session';
export const AUTH_CHALLENGE_PURPOSES = Object.freeze(['SIGNUP', 'LOGIN']);
export const AUTH_LIMITS = Object.freeze({
  otpTtlMs: 10 * 60 * 1000,
  otpIssueCooldownMs: 60 * 1000,
  otpMaxPerHour: 5,
  otpMaxAttempts: 5,
});

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function isProductionEnv(env) {
  return env.BETA_ENVIRONMENT === 'production';
}

export function normalizeEmail(value) {
  return normalizeText(value).toLowerCase();
}

export function authRuntimeValidation(env) {
  const production = isProductionEnv(env);
  const origin = expectedOrigin(env);

  if (production && env.AUTH_EMAIL_TEST_MODE === 'true') {
    return {ok: false, production, reason: 'auth-email-test-mode-disabled-in-production'};
  }

  if (production && env.BETA_TURNSTILE_TEST_MODE === 'true') {
    return {ok: false, production, reason: 'turnstile-test-mode-disabled-in-production'};
  }

  if (production && !normalizeText(env.AUTH_OTP_PEPPER)) {
    return {ok: false, production, reason: 'missing-auth-otp-pepper'};
  }

  if (production && (!origin || !normalizeText(env.TURNSTILE_SECRET_KEY))) {
    return {ok: false, production, reason: 'missing-production-auth-config'};
  }

  return {ok: true, production, origin};
}

export function buildGenericAuthMessage() {
  return 'If an eligible account exists for this email, a verification code has been sent.';
}

export async function sha256Hex(input) {
  const bytes = typeof input === 'string' ? new TextEncoder().encode(input) : input;
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
}

export async function hashOtpVerifier(pepper, challengeId, otp) {
  if (!normalizeText(pepper)) {
    throw new Error('AUTH_OTP_PEPPER is required for OTP verification.');
  }
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(pepper),
    {name: 'HMAC', hash: 'SHA-256'},
    false,
    ['sign'],
  );
  const payload = `${challengeId}:${String(otp).trim()}`;
  const digest = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(payload));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
}

export function isValidOtp(otp) {
  return typeof otp === 'string' && /^\d{6}$/.test(otp.trim());
}

export function buildAuthChallengePayload(raw) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return {ok: false, errors: {body: 'A JSON object is required.'}};
  }

  const value = {
    fullName: normalizeText(raw.fullName),
    institution: normalizeText(raw.institution),
    email: normalizeEmail(raw.email),
    turnstileToken: normalizeText(raw.turnstileToken),
    otp: normalizeText(raw.otp),
    purpose: normalizeText(raw.purpose).toUpperCase(),
  };

  const errors = {};
  if (value.email && !EMAIL_PATTERN.test(value.email)) {
    errors.email = 'Invalid email address.';
  }
  if (value.fullName && value.fullName.length > 120) {
    errors.fullName = 'Full name is too long.';
  }
  if (value.institution && value.institution.length > 160) {
    errors.institution = 'Institution is too long.';
  }
  if (value.turnstileToken && value.turnstileToken.length > 2048) {
    errors.turnstileToken = 'Verification token is too long.';
  }
  if (value.otp && !isValidOtp(value.otp)) {
    errors.otp = 'Verification code must be a 6-digit number.';
  }
  if (value.purpose && !AUTH_CHALLENGE_PURPOSES.includes(value.purpose)) {
    errors.purpose = 'Unsupported challenge purpose.';
  }

  return Object.keys(errors).length ? {ok: false, errors} : {ok: true, value};
}

export function setSessionCookieHeader({sessionId, rawToken, maxAgeSeconds, env}) {
  const secure = env.BETA_ENVIRONMENT === 'production';
  const expires = new Date(Date.now() + maxAgeSeconds * 1000).toUTCString();
  const value = `${sessionId}.${rawToken}`;
  return `${AUTH_SESSION_COOKIE}=${encodeURIComponent(value)}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${maxAgeSeconds}; Expires=${expires}${secure ? '; Secure' : ''}`;
}

export function clearSessionCookieHeader(env) {
  const secure = env.BETA_ENVIRONMENT === 'production';
  return `${AUTH_SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0; Expires=Thu, 01 Jan 1970 00:00:00 GMT${secure ? '; Secure' : ''}`;
}

export function parseSessionCookie(cookieHeader) {
  if (!cookieHeader) {
    return null;
  }

  const match = cookieHeader.match(new RegExp(`(?:^|;\\s*)${AUTH_SESSION_COOKIE}=([^;]+)`));
  if (!match) {
    return null;
  }

  const decoded = decodeURIComponent(match[1]);
  const separatorIndex = decoded.indexOf('.');
  if (separatorIndex <= 0 || separatorIndex === decoded.length - 1) {
    return null;
  }

  const sessionId = decoded.slice(0, separatorIndex);
  const rawToken = decoded.slice(separatorIndex + 1);
  if (!sessionId || !rawToken) {
    return null;
  }

  return {sessionId, rawToken};
}

export async function createSessionToken() {
  const raw = `${crypto.randomUUID()}-${crypto.randomUUID()}-${crypto.randomUUID()}`;
  return {rawToken: raw, tokenHash: await sha256Hex(raw)};
}

export async function getUserByEmail(env, normalizedEmail) {
  const row = await env.BETA_DB.prepare(
    'SELECT user_id, full_name, institution, email, normalized_email, email_verified_at, status, created_at, updated_at FROM users WHERE normalized_email = ?',
  ).bind(normalizedEmail).first();
  return row;
}

export async function getUserById(env, userId) {
  const row = await env.BETA_DB.prepare(
    'SELECT user_id, full_name, institution, email, normalized_email, email_verified_at, status, created_at, updated_at FROM users WHERE user_id = ?',
  ).bind(userId).first();
  return row;
}

export async function getLatestChallenge(env, normalizedEmail, purpose) {
  const row = await env.BETA_DB.prepare(
    'SELECT challenge_id, user_id, normalized_email, purpose, otp_hash, created_at, expires_at, used_at, attempt_count FROM auth_challenges WHERE normalized_email = ? AND purpose = ? ORDER BY created_at DESC LIMIT 1',
  ).bind(normalizedEmail, purpose).first();
  return row;
}

export async function getSessionRecord(env, sessionId) {
  return env.BETA_DB.prepare(
    'SELECT session_id, user_id, token_hash, created_at, expires_at, last_seen_at, revoked_at FROM sessions WHERE session_id = ?',
  ).bind(sessionId).first();
}

export async function enforceIssueLimits(env, normalizedEmail, purpose) {
  const cutoff = new Date(Date.now() - 60 * 60 * 1000).toISOString();
  const recent = await env.BETA_DB.prepare(
    'SELECT created_at FROM auth_challenges WHERE normalized_email = ? AND purpose = ? AND created_at >= ? ORDER BY created_at DESC LIMIT 6',
  ).bind(normalizedEmail, purpose, cutoff).all();

  const entries = recent.results ?? [];
  const newestCreatedAt = entries[0] ? new Date(entries[0].created_at).getTime() : 0;

  if (newestCreatedAt && Date.now() - newestCreatedAt < AUTH_LIMITS.otpIssueCooldownMs) {
    return {ok: false, status: 429, code: 'otp_issue_cooldown', message: 'Please wait before requesting another code.'};
  }

  if (entries.length >= AUTH_LIMITS.otpMaxPerHour) {
    return {ok: false, status: 429, code: 'otp_issue_limit_reached', message: 'Too many codes have been requested recently. Please wait and try again.'};
  }

  return {ok: true};
}

export async function issueChallengeForUser(env, userId, normalizedEmail, purpose) {
  const config = authRuntimeValidation(env);
  if (!config.ok) {
    return {ok: false, status: 503, code: 'auth_unavailable', message: 'Authentication is temporarily unavailable.'};
  }

  const limitCheck = await enforceIssueLimits(env, normalizedEmail, purpose);
  if (!limitCheck.ok) {
    return limitCheck;
  }

  const challengeId = crypto.randomUUID();
  const otp = String(Math.floor(100000 + Math.random() * 900000));
  const otpHash = await hashOtpVerifier(env.AUTH_OTP_PEPPER, challengeId, otp);
  const createdAt = new Date().toISOString();
  const expiresAt = new Date(Date.now() + AUTH_LIMITS.otpTtlMs).toISOString();

  await env.BETA_DB.prepare(
    'INSERT INTO auth_challenges (challenge_id, user_id, normalized_email, purpose, otp_hash, created_at, expires_at, used_at, attempt_count) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 0)',
  ).bind(challengeId, userId, normalizedEmail, purpose, otpHash, createdAt, expiresAt).run();

  const delivery = await sendOtpEmail({email: normalizedEmail, otp, purpose, expiryMinutes: 10, env});
  if (!delivery.ok) {
    return {ok: false, status: 503, code: 'email_delivery_unavailable', message: 'Verification delivery is temporarily unavailable.'};
  }

  return {
    ok: true,
    challengeId,
    otp,
    expiresAt,
    devOtp: delivery.devOtp,
    provider: delivery.provider,
  };
}

export async function verifyOtpChallenge(env, normalizedEmail, purpose, otp) {
  const challenge = await getLatestChallenge(env, normalizedEmail, purpose);
  if (!challenge) {
    return {ok: false, status: 400, code: 'invalid_otp', message: 'The code is invalid or expired.'};
  }

  if (challenge.used_at) {
    return {ok: false, status: 400, code: 'otp_reused', message: 'The code has already been used.'};
  }

  if (new Date(challenge.expires_at).getTime() <= Date.now()) {
    return {ok: false, status: 400, code: 'otp_expired', message: 'The code is invalid or expired.'};
  }

  const currentAttempts = Number(challenge.attempt_count || 0);
  if (currentAttempts >= AUTH_LIMITS.otpMaxAttempts) {
    return {ok: false, status: 429, code: 'otp_locked', message: 'Too many code attempts. Please request a new code.'};
  }

  const expectedHash = await hashOtpVerifier(env.AUTH_OTP_PEPPER, challenge.challenge_id, otp);
  const isValid = expectedHash === challenge.otp_hash;

  await env.BETA_DB.prepare(
    'UPDATE auth_challenges SET attempt_count = attempt_count + 1 WHERE challenge_id = ?',
  ).bind(challenge.challenge_id).run();

  if (!isValid) {
    return {ok: false, status: 400, code: 'invalid_otp', message: 'The code is invalid or expired.'};
  }

  await env.BETA_DB.prepare(
    'UPDATE auth_challenges SET used_at = ? WHERE challenge_id = ?',
  ).bind(new Date().toISOString(), challenge.challenge_id).run();

  return {ok: true, challengeId: challenge.challenge_id, userId: challenge.user_id};
}

export async function createSessionForUser(env, userId) {
  const sessionToken = await createSessionToken();
  const sessionId = crypto.randomUUID();
  const createdAt = new Date().toISOString();
  const expiresAt = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString();

  await env.BETA_DB.prepare(
    'INSERT INTO sessions (session_id, user_id, token_hash, created_at, expires_at, last_seen_at, revoked_at) VALUES (?, ?, ?, ?, ?, ?, NULL)',
  ).bind(sessionId, userId, sessionToken.tokenHash, createdAt, expiresAt, createdAt).run();

  return {sessionId, rawToken: sessionToken.rawToken, expiresAt};
}

export async function getValidatedSessionFromRequest(request, env) {
  const cookieHeader = request.headers.get('Cookie') ?? '';
  const parsed = parseSessionCookie(cookieHeader);

  if (!parsed) {
    return {ok: false, reason: 'missing-session-cookie'};
  }

  const sessionRow = await getSessionRecord(env, parsed.sessionId);
  if (!sessionRow) {
    return {ok: false, reason: 'session-not-found'};
  }

  const tokenHash = await sha256Hex(parsed.rawToken);
  if (sessionRow.token_hash !== tokenHash) {
    return {ok: false, reason: 'session-token-mismatch'};
  }

  if (sessionRow.revoked_at) {
    return {ok: false, reason: 'session-revoked'};
  }

  if (new Date(sessionRow.expires_at).getTime() <= Date.now()) {
    return {ok: false, reason: 'session-expired'};
  }

  await env.BETA_DB.prepare(
    'UPDATE sessions SET last_seen_at = ? WHERE session_id = ?',
  ).bind(new Date().toISOString(), sessionRow.session_id).run();

  return {ok: true, sessionId: sessionRow.session_id, userId: sessionRow.user_id};
}

export async function getAuthenticatedUserResponse(env, userId) {
  const user = await getUserById(env, userId);
  if (!user) {
    return null;
  }

  return {
    authenticated: true,
    user: {
      userId: user.user_id,
      fullName: user.full_name,
      institution: user.institution,
      email: user.email,
      status: user.status,
      emailVerifiedAt: user.email_verified_at,
    },
  };
}

export async function revokeSession(env, sessionId) {
  await env.BETA_DB.prepare(
    'UPDATE sessions SET revoked_at = ?, expires_at = ? WHERE session_id = ?',
  ).bind(new Date().toISOString(), new Date().toISOString(), sessionId).run();
}

export function readJsonBody(request) {
  return request.json();
}

export function guardRequestBody(request, maxBytes = 16_384) {
  const contentLength = Number(request.headers.get('Content-Length') || '0');
  if (Number.isFinite(contentLength) && contentLength > maxBytes) {
    return {ok: false, response: errorResponse(413, 'request_too_large', 'Request is too large.')};
  }

  return {ok: true};
}

export function withNoStoreHeaders(origin) {
  const headers = new Headers({
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'no-referrer',
  });

  if (origin) {
    headers.set('Access-Control-Allow-Origin', origin);
    headers.set('Vary', 'Origin');
  }

  return headers;
}

export function buildJsonResponse(status, payload, origin) {
  return new Response(JSON.stringify(payload), {status, headers: withNoStoreHeaders(origin)});
}

export function jsonSuccess(payload, origin) {
  return buildJsonResponse(200, payload, origin);
}

export function protectedRedirectResponse(origin, safeReturnPath) {
  const destination = new URL('/login', origin);
  const next = safeReturnPath && safeReturnPath.startsWith('/') && !safeReturnPath.startsWith('//') ? safeReturnPath : '/account';
  destination.searchParams.set('returnTo', next);
  return Response.redirect(destination.toString(), 302);
}
