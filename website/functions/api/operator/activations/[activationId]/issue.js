import {buildJsonResponse} from '../../../../_lib/auth.js';
import {constantTimeEquals, getBearerToken} from '../../../../_lib/operator-auth.js';
import {readDeviceRequest, exactDeviceFields} from '../../../../_lib/licence-delivery.js';
import {issueLicenceViaService} from '../../../../_lib/signing-service.js';
import {isLocalDeployment, validateDeployment} from '../../../../_lib/deployment.js';

const fail = (status,code) => buildJsonResponse(status,{error:{code}});
export async function onRequestPost({request,env,params}) {
  if (isLocalDeployment(env)) return fail(409,'local_worker_required');
  if (!validateDeployment(env).ok) return fail(503,'signing_not_configured');
  if (new URL(request.url).protocol !== 'https:') return fail(403,'https_required');
  const origin = request.headers.get('Origin');
  if (origin && origin !== env.BETA_ALLOWED_ORIGIN) return fail(403,'origin_denied');
  const bearer = getBearerToken(request);
  if (!bearer || !constantTimeEquals(bearer,env.OPERATOR_LICENCE_PUBLISH_TOKEN)) return fail(401,'unauthorized');
  const body = await readDeviceRequest(request);
  if (!exactDeviceFields(body,['schema_version']) || body.schema_version !== 1) return fail(400,'invalid_request');
  return issueLicenceViaService(env,params?.activationId);
}
