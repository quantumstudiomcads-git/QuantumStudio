import {buildJsonResponse, createSessionForUser, getUserByEmail, normalizeEmail, setSessionCookieHeader} from '../../../_lib/auth.js';
import {getGoogleState, googleRuntimeValidation, safeGoogleReturnTo} from '../../../_lib/google-auth.js';

export async function onRequestPost(context) {
  const {request, env} = context;
  const runtime = googleRuntimeValidation(env);
  if (!runtime.ok) {
    return buildJsonResponse(503, {ok: false, message: 'Google authentication is temporarily unavailable.'});
  }

  if (!request.headers.get('Content-Type')?.toLowerCase().includes('application/json')) {
    return buildJsonResponse(415, {ok: false, message: 'Send JSON content.'});
  }

  let raw;
  try {
    raw = await request.json();
  } catch {
    return buildJsonResponse(400, {ok: false, message: 'Invalid JSON request.'});
  }

  const state = String(raw.state || '').trim();
  const institution = String(raw.institution || '').trim();
  if (!state || !institution) {
    return buildJsonResponse(400, {ok: false, message: 'Institution is required.'});
  }

  const stateRow = await getGoogleState(env, state);
  if (!stateRow || stateRow.purpose !== 'SIGNUP' || stateRow.used_at || new Date(stateRow.expires_at).getTime() <= Date.now()) {
    return buildJsonResponse(400, {ok: false, message: 'Google signup is unavailable.'});
  }

  if (institution.length < 2 || institution.length > 160) {
    return buildJsonResponse(400, {ok: false, message: 'Institution or organization must be between 2 and 160 characters.'});
  }

  const normalizedEmail = normalizeEmail(stateRow.google_email ?? '');
  const existingUser = normalizedEmail ? await getUserByEmail(env, normalizedEmail) : null;
  const now = new Date().toISOString();
  const userId = existingUser ? existingUser.user_id : crypto.randomUUID();

  if (!existingUser) {
    await env.BETA_DB.prepare(
      'INSERT INTO users (user_id, full_name, institution, email, normalized_email, email_lookup_hash, email_verified_at, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
    ).bind(
      userId,
      stateRow.google_name ?? '',
      institution,
      normalizedEmail,
      normalizedEmail,
      normalizedEmail,
      now,
      'VERIFIED',
      now,
      now,
    ).run();
  } else {
    await env.BETA_DB.prepare(
      'UPDATE users SET full_name = ?, institution = ?, email = ?, normalized_email = ?, email_verified_at = ?, status = ?, updated_at = ? WHERE user_id = ?',
    ).bind(
      stateRow.google_name ?? existingUser.full_name,
      institution,
      normalizedEmail,
      normalizedEmail,
      now,
      'VERIFIED',
      now,
      userId,
    ).run();
  }

  const identityRow = await env.BETA_DB.prepare(
    'SELECT identity_id FROM auth_identities WHERE provider = ? AND provider_subject = ?',
  ).bind('GOOGLE', stateRow.google_sub).first();

  if (!identityRow) {
    await env.BETA_DB.prepare(
      'INSERT INTO auth_identities (identity_id, user_id, provider, provider_subject, provider_email, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
    ).bind(crypto.randomUUID(), userId, 'GOOGLE', stateRow.google_sub, normalizedEmail, now, now).run();
  }

  const session = await createSessionForUser(env, userId);
  const cookieHeader = setSessionCookieHeader({sessionId: session.sessionId, rawToken: session.rawToken, maxAgeSeconds: 30 * 24 * 60 * 60, env});
  await env.BETA_DB.prepare(
    'UPDATE google_oauth_states SET used_at = ? WHERE state_hash = ?',
  ).bind(new Date().toISOString(), stateRow.state_hash).run();

  const destination = safeGoogleReturnTo(stateRow.return_to, '/account');
  const response = buildJsonResponse(200, {
    ok: true,
    message: 'Authenticated successfully.',
    redirectTo: destination,
    user: {
      userId,
      fullName: stateRow.google_name ?? '',
      institution,
      email: normalizedEmail,
      status: 'VERIFIED',
    },
  });
  response.headers.set('Set-Cookie', cookieHeader);
  return response;
}
