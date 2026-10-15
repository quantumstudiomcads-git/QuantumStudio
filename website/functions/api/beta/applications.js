import {errorResponse, handleApplicationPost, handleOptions} from '../../_lib/beta-registration.js';
import {authRuntimeValidation, getValidatedSessionFromRequest} from '../../_lib/auth.js';

export async function onRequestPost(context) {
  const {request, env} = context;
  const runtime = authRuntimeValidation(env);
  if (!runtime.ok) return errorResponse(503, 'service_unavailable', 'Beta registration is temporarily unavailable.');
  const session = await getValidatedSessionFromRequest(request, env);
  if (!session.ok) return errorResponse(401, 'authentication_required', 'Sign in before submitting a beta application.');
  return handleApplicationPost(request, env, {userId: session.userId});
}
export function onRequestOptions(context) { return handleOptions(context.request, context.env); }
export function onRequestGet() { return errorResponse(405, 'method_not_allowed', 'Method not allowed.'); }
