import {handleDesktopAuth} from '../../_lib/desktop-auth.js';

export function onRequestPost({request, env}) {
  return handleDesktopAuth(request, env, 'cancel');
}
