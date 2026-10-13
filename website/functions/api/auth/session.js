import {getAuthenticatedUserResponse, getValidatedSessionFromRequest, buildJsonResponse, authRuntimeValidation} from '../../_lib/auth.js';

export async function onRequestGet(context) {
  const {request, env} = context;
  const runtime = authRuntimeValidation(env);
  if (!runtime.ok) {
    return buildJsonResponse(200, {authenticated: false, reason: runtime.reason});
  }

  const session = await getValidatedSessionFromRequest(request, env);
  if (!session.ok) {
    return buildJsonResponse(200, {authenticated: false});
  }

  const sessionUser = await getAuthenticatedUserResponse(env, session.userId);
  return buildJsonResponse(200, sessionUser ?? {authenticated: false});
}

export function onRequestOptions() {
  return new Response(null, {status: 204, headers: {'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'GET, OPTIONS', 'Access-Control-Allow-Headers': 'Content-Type, Cookie'}});
}
