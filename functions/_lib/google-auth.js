import {createSessionForUser, getUserByEmail, normalizeEmail, setSessionCookieHeader, sha256Hex} from './auth.js';

export function googleRuntimeValidation(env) {
  if (!env.GOOGLE_CLIENT_ID || !env.GOOGLE_CLIENT_SECRET || !env.GOOGLE_REDIRECT_URI) {
    return {ok: false, reason: 'missing-google-config'};
  }
  return {ok: true};
}

export function safeGoogleReturnTo(value, fallback = '/account') {
  if (!value || !value.startsWith('/') || value.startsWith('//') || value.includes('\\')) {
    return fallback;
  }

  try {
    const target = new URL(value, 'https://quantumstudio.invalid');
    if (target.origin !== 'https://quantumstudio.invalid') {
      return fallback;
    }
    const normalized = `${target.pathname}${target.search}${target.hash}`;
    return normalized || fallback;
  } catch {
    return fallback;
  }
}

function toBase64Url(value) {
  if (typeof Buffer !== 'undefined') {
    return Buffer.from(value).toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
  }
  const binary = String.fromCharCode(...new Uint8Array(value));
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

export async function createPkcePair() {
  const verifierBytes = new Uint8Array(32);
  crypto.getRandomValues(verifierBytes);
  const verifier = toBase64Url(verifierBytes);
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier));
  const challenge = toBase64Url(new Uint8Array(digest));
  return {verifier, challenge};
}

export async function upsertGoogleState(env, {purpose, returnTo, codeVerifier, googleSub, googleEmail, googleName, emailVerified}) {
  const safeReturnTo = safeGoogleReturnTo(returnTo, '/account');
  const state = `${crypto.randomUUID()}-${crypto.randomUUID()}-${crypto.randomUUID()}`;
  const stateHash = await sha256Hex(state);
  const createdAt = new Date().toISOString();
  const expiresAt = new Date(Date.now() + 10 * 60 * 1000).toISOString();

  await env.BETA_DB.prepare(
    'INSERT INTO google_oauth_states (state_hash, purpose, return_to, code_verifier, google_sub, google_email, google_name, email_verified, created_at, expires_at, used_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)',
  ).bind(
    stateHash,
    purpose,
    safeReturnTo,
    codeVerifier,
    googleSub ?? null,
    googleEmail ?? null,
    googleName ?? null,
    emailVerified ? 1 : 0,
    createdAt,
    expiresAt,
  ).run();

  return {state, stateHash, expiresAt};
}

export async function getGoogleState(env, rawState) {
  if (!rawState) {
    return null;
  }

  const stateHash = await sha256Hex(rawState);
  return env.BETA_DB.prepare(
    'SELECT state_hash, purpose, return_to, code_verifier, google_sub, google_email, google_name, email_verified, created_at, expires_at, used_at FROM google_oauth_states WHERE state_hash = ?',
  ).bind(stateHash).first();
}

export async function consumeGoogleState(env, rawState) {
  const row = await getGoogleState(env, rawState);
  if (!row) {
    return {ok: false, reason: 'missing-state'};
  }
  if (row.used_at) {
    return {ok: false, reason: 'reused-state'};
  }
  if (new Date(row.expires_at).getTime() <= Date.now()) {
    return {ok: false, reason: 'expired-state'};
  }

  await env.BETA_DB.prepare(
    'UPDATE google_oauth_states SET used_at = ? WHERE state_hash = ?',
  ).bind(new Date().toISOString(), row.state_hash).run();

  return {ok: true, state: row};
}

export function decodeJwtPayload(token) {
  if (!token || typeof token !== 'string') {
    return null;
  }
  const parts = token.split('.');
  if (parts.length < 2) {
    return null;
  }

  try {
    const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4);
    const payload = typeof Buffer !== 'undefined' ? Buffer.from(padded, 'base64').toString('utf-8') : atob(padded);
    return JSON.parse(payload);
  } catch {
    return null;
  }
}

export function buildGoogleAuthUrl(env, state, codeChallenge) {
  const authUrl = new URL('https://accounts.google.com/o/oauth2/v2/auth');
  authUrl.searchParams.set('client_id', env.GOOGLE_CLIENT_ID);
  authUrl.searchParams.set('redirect_uri', env.GOOGLE_REDIRECT_URI);
  authUrl.searchParams.set('response_type', 'code');
  authUrl.searchParams.set('scope', 'openid email profile');
  authUrl.searchParams.set('state', state);
  authUrl.searchParams.set('code_challenge', codeChallenge);
  authUrl.searchParams.set('code_challenge_method', 'S256');
  authUrl.searchParams.set('prompt', 'select_account');
  return authUrl.toString();
}

export async function exchangeGoogleCode(env, code, codeVerifier) {
  const tokenRequest = new URL('https://oauth2.googleapis.com/token');
  const body = new URLSearchParams({
    client_id: env.GOOGLE_CLIENT_ID,
    client_secret: env.GOOGLE_CLIENT_SECRET,
    code,
    grant_type: 'authorization_code',
    redirect_uri: env.GOOGLE_REDIRECT_URI,
    code_verifier: codeVerifier,
  });

  const response = await fetch(tokenRequest, {
    method: 'POST',
    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
    body: body.toString(),
  });

  if (!response.ok) {
    return {ok: false, reason: 'google-token-exchange-failed'};
  }

  const tokenData = await response.json();
  if (!tokenData || typeof tokenData !== 'object' || !tokenData.id_token) {
    return {ok: false, reason: 'google-id-token-missing'};
  }

  return {ok: true, tokenData};
}

export async function resolveGoogleUser(env, code, codeVerifier) {
  const tokenResult = await exchangeGoogleCode(env, code, codeVerifier);
  if (!tokenResult.ok) {
    return tokenResult;
  }

  const payload = decodeJwtPayload(tokenResult.tokenData.id_token);
  if (!payload) {
    return {ok: false, reason: 'invalid-id-token'};
  }

  const issuer = payload.iss;
  const audience = payload.aud;
  if (issuer !== 'https://accounts.google.com' && issuer !== 'accounts.google.com') {
    return {ok: false, reason: 'invalid-google-issuer'};
  }
  if (audience !== env.GOOGLE_CLIENT_ID) {
    return {ok: false, reason: 'invalid-google-audience'};
  }
  if (typeof payload.exp !== 'number' || payload.exp * 1000 <= Date.now()) {
    return {ok: false, reason: 'expired-google-token'};
  }
  if (payload.email_verified !== true) {
    return {ok: false, reason: 'google-email-unverified'};
  }
  const googleSub = typeof payload.sub === 'string' && payload.sub ? payload.sub : null;
  if (!googleSub) {
    return {ok: false, reason: 'missing-google-sub'};
  }

  return {
    ok: true,
    subject: googleSub,
    email: typeof payload.email === 'string' ? payload.email : null,
    name: typeof payload.name === 'string' ? payload.name : '',
    emailVerified: true,
  };
}

export async function createGoogleSession(env, userId) {
  const session = await createSessionForUser(env, userId);
  const cookieHeader = setSessionCookieHeader({sessionId: session.sessionId, rawToken: session.rawToken, maxAgeSeconds: 30 * 24 * 60 * 60, env});
  return {session, cookieHeader};
}

export async function requireGoogleAccountForIdentity(env, providerSubject, providerEmail) {
  const normalizedEmail = providerEmail ? normalizeEmail(providerEmail) : null;
  const identity = await env.BETA_DB.prepare(
    'SELECT identity_id, user_id, provider, provider_subject, provider_email, created_at, updated_at FROM auth_identities WHERE provider = ? AND provider_subject = ?',
  ).bind('GOOGLE', providerSubject).first();

  if (identity) {
    return {ok: true, userId: identity.user_id, linked: false, existingIdentity: true};
  }

  if (!normalizedEmail) {
    return {ok: true, userId: null, linked: false, existingIdentity: false, reason: 'missing-email'};
  }

  const user = await getUserByEmail(env, normalizedEmail);
  if (user && user.email_verified_at) {
    return {ok: true, userId: user.user_id, linked: true, existingIdentity: false};
  }

  return {ok: true, userId: null, linked: false, existingIdentity: false};
}
