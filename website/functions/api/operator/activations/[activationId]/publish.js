import {publishLicence} from '../../../../_lib/licence-delivery.js';
export function onRequestPost({request,env,params}) { return publishLicence(request,env,params?.activationId); }
