import {deviceStatusChallenge} from '../../_lib/device-status.js';
export function onRequestPost({request,env}) {return deviceStatusChallenge(request,env);}
