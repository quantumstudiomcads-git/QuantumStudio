import {authRuntimeValidation, buildAuthChallengePayload, createSessionForUser, getUserByEmail, normalizeEmail, setSessionCookieHeader, verifyOtpChallenge, getAuthenticatedUserResponse} from '../../_lib/auth.js';

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

  const parsed = buildAuthChallengePayload({email: raw.email, otp: raw.otp, purpose: raw.purpose});
  if (!parsed.ok) {
    return new Response(JSON.stringify({ok: false, errors: parsed.errors}), {status: 400, headers: {'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store'}});
  }

  const normalizedEmail = normalizeEmail(parsed.value.email);
  const user = await getUserByEmail(env, normalizedEmail);
  if (!user) {
    return new Response(JSON.stringify({ok: false, message: 'The code is invalid or expired.'}), {status: 400, headers: {'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store'}});
  }

  const verification = await verifyOtpChallenge(env, normalizedEmail, parsed.value.purpose, parsed.value.otp);
  if (!verification.ok) {
    return new Response(JSON.stringify({ok: false, message: verification.message}), {status: verification.status || 400, headers: {'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store'}});
  }

  const session = await createSessionForUser(env, verification.userId);
  await env.BETA_DB.prepare(
    'UPDATE users SET email_verified_at = ?, status = ?, updated_at = ? WHERE user_id = ?',
  ).bind(new Date().toISOString(), 'VERIFIED', new Date().toISOString(), verification.userId).run();

  const cookieHeader = setSessionCookieHeader({sessionId: session.sessionId, rawToken: session.rawToken, maxAgeSeconds: 30 * 24 * 60 * 60, env});

  return new Response(JSON.stringify({ok: true, message: 'Authenticated successfully.', user: {userId: user.user_id, fullName: user.full_name, institution: user.institution, email: user.email, status: 'VERIFIED'}}), {
    status: 200,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
      'Set-Cookie': cookieHeader,
    },
  });
}

export async function onRequestGet() {
  return new Response(JSON.stringify({ok: false, message: 'Method not allowed.'}), {status: 405, headers: {'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store'}});
}
