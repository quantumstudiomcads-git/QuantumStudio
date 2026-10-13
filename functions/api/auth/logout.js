import {clearSessionCookieHeader, getValidatedSessionFromRequest, revokeSession, authRuntimeValidation} from '../../_lib/auth.js';

export async function onRequestPost(context) {
  const {request, env} = context;
  const runtime = authRuntimeValidation(env);
  if (!runtime.ok) {
    return new Response(JSON.stringify({ok: false, message: 'Authentication is unavailable.'}), {status: 503, headers: {'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store'}});
  }

  const parsed = await getValidatedSessionFromRequest(request, env);
  if (parsed.ok) {
    await revokeSession(env, parsed.sessionId);
  }

  return new Response(JSON.stringify({ok: true}), {
    status: 200,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
      'Set-Cookie': clearSessionCookieHeader(env),
    },
  });
}
