import {errorResponse, handleApplicationPost, handleOptions} from '../../_lib/beta-registration.js';

export async function onRequestPost(context) { return handleApplicationPost(context.request, context.env); }
export function onRequestOptions(context) { return handleOptions(context.request, context.env); }
export function onRequestGet() { return errorResponse(405, 'method_not_allowed', 'Method not allowed.'); }
