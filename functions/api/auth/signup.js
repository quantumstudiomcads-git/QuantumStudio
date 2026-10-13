import {verifyTurnstile} from '../../_lib/beta-registration.js';
import {authRuntimeValidation, buildGenericAuthMessage, buildAuthChallengePayload, createSessionForUser, getUserByEmail, getValidatedSessionFromRequest, issueChallengeForUser, jsonSuccess, normalizeEmail, setSessionCookieHeader, verifyOtpChallenge} from '../../_lib/auth.js';

export async function onRequestPost(context) {
  const {request, env} = context;
  const runtime = authRuntimeValidation(env);
  if (!runtime.ok) {
    return new Response(JSON.stringify({ok: false, message: 'Authentication is temporarily unavailable.'}), {status: 503, headers: {'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store'}});
  }

  if (!request.headers.get('Content-Type')?.toLowerCase().includes('application/json')) {
    return new Response(JSON.stringify({ok: false, message: 'Send JSON content.'}), {status: 415, headers: {'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store'}});
  }

  let raw;
  try {
    raw = await request.json();
  } catch {
    return new Response(JSON.stringify({ok: false, message: 'Invalid JSON request.'}), {status: 400, headers: {'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store'}});
  }

  const parsed = buildAuthChallengePayload({
    fullName: raw.fullName,
    institution: raw.institution,
    email: raw.email,
    turnstileToken: raw.turnstileToken,
  });

  if (!parsed.ok) {
    return new Response(JSON.stringify({ok: false, errors: parsed.errors}), {status: 400, headers: {'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store'}});
  }

  const turnstile = await verifyTurnstile(parsed.value.turnstileToken, env, request, undefined, 'auth_otp');
  if (!turnstile.ok) {
    return new Response(JSON.stringify({ok: false, message: 'Verification expired or failed.'}), {status: 400, headers: {'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store'}});
  }

  const normalizedEmail = normalizeEmail(parsed.value.email);
  const existingUser = await getUserByEmail(env, normalizedEmail);

  const userId = existingUser ? existingUser.user_id : crypto.randomUUID();
  const now = new Date().toISOString();

  if (!existingUser) {
    await env.BETA_DB.prepare(
      'INSERT INTO users (user_id, full_name, institution, email, normalized_email, email_lookup_hash, email_verified_at, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)',
    ).bind(userId, parsed.value.fullName, parsed.value.institution, normalizedEmail, normalizedEmail, normalizedEmail, 'PENDING', now, now).run();
  } else {
    await env.BETA_DB.prepare(
      'UPDATE users SET full_name = ?, institution = ?, email = ?, normalized_email = ?, updated_at = ? WHERE user_id = ?',
    ).bind(parsed.value.fullName, parsed.value.institution, normalizedEmail, normalizedEmail, now, userId).run();
  }

  const challengeResult = await issueChallengeForUser(env, userId, normalizedEmail, 'SIGNUP');
  if (!challengeResult.ok) {
    return new Response(JSON.stringify({ok: false, message: challengeResult.message}), {status: challengeResult.status || 503, headers: {'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store'}});
  }

  return new Response(JSON.stringify({ok: true, message: buildGenericAuthMessage(), devOtp: challengeResult.devOtp ?? null}), {
    status: 200,
    headers: {'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store'},
  });
}

export async function onRequestGet() {
  return new Response(JSON.stringify({ok: false, message: 'Method not allowed.'}), {status: 405, headers: {'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store'}});
}
