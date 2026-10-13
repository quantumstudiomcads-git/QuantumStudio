import {buildGoogleAuthUrl, createPkcePair, googleRuntimeValidation, safeGoogleReturnTo, upsertGoogleState} from '../../../_lib/google-auth.js';

export async function onRequestGet(context) {
  const {request, env} = context;
  const runtime = googleRuntimeValidation(env);
  if (!runtime.ok) {
    return new Response(JSON.stringify({ok: false, message: 'Google authentication is temporarily unavailable.'}), {
      status: 503,
      headers: {'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store'},
    });
  }

  const url = new URL(request.url);
  const returnTo = safeGoogleReturnTo(url.searchParams.get('returnTo') ?? '/account', '/account');
  const pkce = await createPkcePair();
  const state = await upsertGoogleState(env, {
    purpose: 'LOGIN',
    returnTo,
    codeVerifier: pkce.verifier,
    emailVerified: false,
  });

  const authUrl = buildGoogleAuthUrl(env, state.state, pkce.challenge);
  return Response.redirect(authUrl, 302);
}
