import {handleActivationRequest} from '../../_lib/beta-activation.js';

export function onRequestGet({request, env}) {
  return handleActivationRequest(request, env, 'GET');
}

export function onRequestPost({request, env}) {
  return handleActivationRequest(request, env, 'POST');
}
