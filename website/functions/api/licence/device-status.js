import {deviceStatus} from '../../_lib/device-status.js';
export function onRequestPost({request,env}) {return deviceStatus(request,env);}
