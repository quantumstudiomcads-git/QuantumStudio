// Server-only admin authorization over the existing HttpOnly session mechanism.
import {getValidatedSessionFromRequest} from './auth.js';
import {validateDeployment} from './deployment.js';

const id = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
export const adminHeaders = {'Content-Type':'application/json; charset=utf-8','Cache-Control':'private, no-store',
  'Vary':'Cookie','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer',
  'X-Robots-Tag':'noindex, nofollow','X-Frame-Options':'DENY'};
export const adminJson = (status,body) => new Response(JSON.stringify(body),{status,headers:adminHeaders});
export const adminFailure = (status,code) => adminJson(status,{error:{code}});

export async function requireAdmin(request,env,{mutation=false}={}) {
  if (env?.QS_ADMIN_ENABLED !== 'true' || !validateDeployment(env).ok
      || !['staging','production'].includes(env.BETA_ENVIRONMENT)) {
    return {response:adminFailure(503,'admin_unavailable')};
  }
  let allowed;
  try {
    allowed=JSON.parse(env.QS_ADMIN_USER_IDS);
    if (!Array.isArray(allowed) || allowed.length<1 || allowed.length>20
        || allowed.some(value=>typeof value!=='string'||!id.test(value)) || new Set(allowed).size!==allowed.length) throw new Error();
  } catch {return {response:adminFailure(503,'admin_unavailable')};}
  const url=new URL(request.url);
  if(url.protocol!=='https:' || url.origin!==env.BETA_ALLOWED_ORIGIN.replace(/\/$/,'')) {
    return {response:adminFailure(403,'admin_origin_denied')};
  }
  if(request.headers.get('Sec-Fetch-Site')==='cross-site') return {response:adminFailure(403,'admin_origin_denied')};
  if(mutation && (request.method!=='POST' || request.headers.get('Origin')!==url.origin
      || request.headers.get('X-QuantumStudio-Admin')!=='1'
      || request.headers.get('Content-Type')?.split(';',1)[0].trim().toLowerCase()!=='application/json')) {
    return {response:adminFailure(403,'admin_origin_denied')};
  }
  try {
    // Malformed cookie encoding must never throw diagnostics into the response.
    let session;
    try {session=await getValidatedSessionFromRequest(request,env);}
    catch(error) {if(error instanceof URIError) return {response:adminFailure(401,'authentication_required')};throw error;}
    if(!session.ok) return {response:adminFailure(401,'authentication_required')};
    if(!allowed.includes(session.userId)) return {response:adminFailure(403,'admin_forbidden')};
    const user=await env.BETA_DB.prepare('SELECT status,email_verified_at FROM users WHERE user_id=?').bind(session.userId).first();
    const record=await env.BETA_DB.prepare('SELECT expires_at,revoked_at FROM sessions WHERE session_id=? AND user_id=?').bind(session.sessionId,session.userId).first();
    if(user?.status!=='VERIFIED' || !user.email_verified_at || !Number.isFinite(Date.parse(user.email_verified_at))
        || !record || record.revoked_at || !Number.isFinite(Date.parse(record.expires_at)) || Date.parse(record.expires_at)<=Date.now()) {
      return {response:adminFailure(403,'admin_forbidden')};
    }
    return {userId:session.userId};
  } catch {return {response:adminFailure(503,'admin_unavailable')};}
}
