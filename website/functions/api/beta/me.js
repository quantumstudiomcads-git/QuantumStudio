import {authRuntimeValidation, getValidatedSessionFromRequest, buildJsonResponse} from '../../_lib/auth.js';
import {errorResponse} from '../../_lib/beta-registration.js';

export async function onRequestGet({request, env}) {
  const runtime = authRuntimeValidation(env);
  if (!runtime.ok || !env.BETA_DB) {
    return errorResponse(503, 'service_unavailable', 'Beta status is temporarily unavailable.');
  }

  const session = await getValidatedSessionFromRequest(request, env);
  if (!session.ok) {
    return errorResponse(401, 'authentication_required', 'Sign in to view your beta application.');
  }

  let application;
  try {
    application = await env.BETA_DB.prepare(
      'SELECT application_id, status, submitted_at, updated_at FROM beta_applications WHERE user_id = ? LIMIT 1',
    ).bind(session.userId).first();
  } catch {
    return errorResponse(503, 'service_unavailable', 'Beta status is temporarily unavailable.');
  }

  return buildJsonResponse(200, {
    application: application ? {
      application_id: application.application_id,
      status: application.status,
      submitted_at: application.submitted_at,
      updated_at: application.updated_at,
    } : null,
  });
}

export function onRequestPost() {
  return errorResponse(405, 'method_not_allowed', 'Method not allowed.');
}
