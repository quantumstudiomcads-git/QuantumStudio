import {verifyTurnstile} from '../../_lib/beta-registration.js';
import {authRuntimeValidation, buildGenericAuthMessage, buildAuthChallengePayload, getUserByEmail, issueChallengeForUser, normalizeEmail} from '../../_lib/auth.js';

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

  const parsed = buildAuthChallengePayload({email: raw.email, turnstileToken: raw.turnstileToken, purpose: raw.purpose});
  if (!parsed.ok) {
    return new Response(JSON.stringify({ok: false, errors: parsed.errors}), {status: 400, headers: {'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store'}});
  }

  const turnstile = await verifyTurnstile(parsed.value.turnstileToken, env, request, undefined, 'auth_otp');
  if (!turnstile.ok) {
    return new Response(JSON.stringify({ok: false, message: 'Verification expired or failed.'}), {status: 400, headers: {'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store'}});
  }

  const normalizedEmail = normalizeEmail(parsed.value.email);
  const user = await getUserByEmail(env, normalizedEmail);

  if (!user || !user.email_verified_at) {
    return new Response(JSON.stringify({ok: true, message: buildGenericAuthMessage()}), {status: 200, headers: {'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store'}});
  }

  const challenge = await issueChallengeForUser(env, user.user_id, normalizedEmail, parsed.value.purpose || 'LOGIN');
  if (!challenge.ok) {
    return new Response(JSON.stringify({ok: false, message: challenge.message}), {status: challenge.status || 503, headers: {'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store'}});
  }

  return new Response(JSON.stringify({ok: true, message: buildGenericAuthMessage(), devOtp: challenge.devOtp ?? null}), {status: 200, headers: {'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store'}});
}

export async function onRequestGet() {
  return new Response(JSON.stringify({ok: false, message: 'Method not allowed.'}), {status: 405, headers: {'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store'}});
}
