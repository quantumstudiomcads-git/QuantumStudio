import {createGoogleSession, getGoogleState, googleRuntimeValidation, requireGoogleAccountForIdentity, resolveGoogleUser, safeGoogleReturnTo, upsertGoogleState} from '../../../_lib/google-auth.js';

export async function onRequestGet(context) {
  const {request, env} = context;
  const runtime = googleRuntimeValidation(env);
  if (!runtime.ok) {
    return Response.redirect(new URL('/login', request.url), 302);
  }

  const url = new URL(request.url);
  const oauthError = url.searchParams.get('error');
  const state = url.searchParams.get('state');
  const code = url.searchParams.get('code');

  if (oauthError || !state || !code) {
    return Response.redirect(new URL('/login', url.origin), 302);
  }

  const stateRow = await getGoogleState(env, state);
  if (!stateRow || stateRow.used_at || new Date(stateRow.expires_at).getTime() <= Date.now()) {
    return Response.redirect(new URL('/login', url.origin), 302);
  }

  const googleUser = await resolveGoogleUser(env, code, stateRow.code_verifier);
  if (!googleUser.ok) {
    return Response.redirect(new URL('/login', url.origin), 302);
  }

  await env.BETA_DB.prepare(
    'UPDATE google_oauth_states SET google_sub = ?, google_email = ?, google_name = ?, email_verified = ? WHERE state_hash = ?',
  ).bind(googleUser.subject, googleUser.email ?? null, googleUser.name ?? '', googleUser.emailVerified ? 1 : 0, stateRow.state_hash).run();

  const existingAccount = await requireGoogleAccountForIdentity(env, googleUser.subject, googleUser.email);
  if (!existingAccount.userId) {
    const pendingSignup = await upsertGoogleState(env, {
      purpose: 'SIGNUP',
      returnTo: stateRow.return_to,
      codeVerifier: crypto.randomUUID(),
      googleSub: googleUser.subject,
      googleEmail: googleUser.email,
      googleName: googleUser.name,
      emailVerified: true,
    });

    await env.BETA_DB.prepare(
      'UPDATE google_oauth_states SET used_at = ? WHERE state_hash = ?',
    ).bind(new Date().toISOString(), stateRow.state_hash).run();

    const signupUrl = new URL('/signup', url.origin);
    signupUrl.searchParams.set('provider', 'google');
    signupUrl.searchParams.set('state', pendingSignup.state);
    return Response.redirect(signupUrl.toString(), 302);
  }

  if (existingAccount.linked) {
    const existingIdentity = await env.BETA_DB.prepare(
      'SELECT identity_id FROM auth_identities WHERE provider = ? AND provider_subject = ?',
    ).bind('GOOGLE', googleUser.subject).first();
    if (!existingIdentity) {
      await env.BETA_DB.prepare(
        'INSERT INTO auth_identities (identity_id, user_id, provider, provider_subject, provider_email, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
      ).bind(crypto.randomUUID(), existingAccount.userId, 'GOOGLE', googleUser.subject, googleUser.email ?? null, new Date().toISOString(), new Date().toISOString()).run();
    }
  }

  const session = await createGoogleSession(env, existingAccount.userId);
  await env.BETA_DB.prepare(
    'UPDATE google_oauth_states SET used_at = ? WHERE state_hash = ?',
  ).bind(new Date().toISOString(), stateRow.state_hash).run();

  const destination = new URL(safeGoogleReturnTo(stateRow.return_to, '/account'), url.origin);
  return new Response(null, {
    status: 302,
    headers: {
      Location: destination.toString(),
      'Set-Cookie': session.cookieHeader,
      'Cache-Control': 'no-store',
    },
  });
}
