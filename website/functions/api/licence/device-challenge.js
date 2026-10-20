import {deviceChallenge} from '../../_lib/licence-delivery.js';
export function onRequestPost({request,env}) { return deviceChallenge(request,env); }
