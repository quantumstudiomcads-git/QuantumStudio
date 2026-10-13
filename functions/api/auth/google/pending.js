import {buildJsonResponse} from '../../../_lib/auth.js';
import {getGoogleState, safeGoogleReturnTo} from '../../../_lib/google-auth.js';

export async function onRequestGet(context) {
  const {request, env} = context;
  const state = new URL(request.url).searchParams.get('state');

  if (!state) {
    return buildJsonResponse(400, {ok: false, message: 'Missing Google OAuth state.'});
  }

  const row = await getGoogleState(env, state);
  if (!row || row.used_at || new Date(row.expires_at).getTime() <= Date.now()) {
    return buildJsonResponse(400, {ok: false, message: 'Google signup is unavailable.'});
  }

  return buildJsonResponse(200, {
    ok: true,
    email: row.google_email ?? '',
    name: row.google_name ?? '',
    returnTo: safeGoogleReturnTo(row.return_to, '/account'),
  });
}
