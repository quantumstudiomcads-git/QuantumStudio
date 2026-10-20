import {deviceRetrieve} from '../../_lib/licence-delivery.js';
export function onRequestPost({request,env}) { return deviceRetrieve(request,env); }
