// Server-only orchestration: never return operator credentials or raw internal responses.
import {requireAdmin,adminJson,adminFailure} from './admin-auth.js';
import {readDeviceRequest,exactDeviceFields} from './licence-delivery.js';
import {issueLicenceViaService} from './signing-service.js';
import {onRequestPost as transitionApplication} from '../api/operator/applications/[applicationId]/status.js';
import {onRequestPost as revokeActivation} from '../api/operator/activations/[activationId]/revoke.js';

const id=/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const applicationFields='application_id,user_id,full_name,email,institution,country,academic_role,research_area,intended_evaluation,operating_system,status,submitted_at,reviewed_at,review_note';
const entFields='entitlement_id,plan_id,starts_at,expires_at,device_limit,revision';
const activationFields='activation_request_id,installation_id,platform,architecture,app_version,device_public_key_hash,status,authorized_at,revoked_at,flag_reason,licence_id,licence_status,licence_issued_at,licence_expires_at,licence_revoked_at,revocation_reason_code';
const bounded=(body)=>new TextEncoder().encode(JSON.stringify(body)).length<=2*1024*1024;

async function detail(env,applicationId) {
  const application=await env.BETA_DB.prepare(`SELECT ${applicationFields} FROM beta_applications WHERE application_id=?`).bind(applicationId).first();
  if(!application)return null;
  const user=application.user_id ? await env.BETA_DB.prepare('SELECT user_id,full_name,email,institution,status,created_at FROM users WHERE user_id=?').bind(application.user_id).first():null;
  const entitlement=await env.BETA_DB.prepare(`SELECT ${entFields} FROM account_entitlements WHERE application_id=? AND user_id=?`).bind(applicationId,application.user_id).first();
  if(entitlement) {
    const now=Date.now(),starts=Date.parse(entitlement.starts_at),expires=Date.parse(entitlement.expires_at);
    entitlement.status=!Number.isFinite(starts)||!Number.isFinite(expires)?'UNAVAILABLE':now<starts?'NOT_STARTED':now>=expires?'EXPIRED':'CURRENT';
  }
  const rows=await env.BETA_DB.prepare(`SELECT ${activationFields.split(',').map(field=>'a.'+field).join(',')},
    p.envelope_json,p.status AS publication_status,p.published_at
    FROM beta_activations a LEFT JOIN published_licences p ON p.activation_request_id=a.activation_request_id
    WHERE a.application_id=? AND a.user_id=? ORDER BY a.created_at DESC,a.activation_request_id LIMIT 201`).bind(applicationId,application.user_id).all();
  if((rows.results??[]).length>200)throw new Error();
  const activations=(rows.results??[]).map(({envelope_json,...row})=>{
    let kid=null;
    if(envelope_json){const e=JSON.parse(envelope_json);if(typeof e.kid!=='string'||e.kid.length>100)throw new Error();kid=e.kid;}
    return {...row,kid};
  });
  return {application,user,entitlement,activations};
}

export async function listAdminApplications({request,env}) {
  const guard=await requireAdmin(request,env);if(guard.response)return guard.response;
  try {
    const url=new URL(request.url),raw=url.searchParams.get('offset')??'0';
    if([...url.searchParams.keys()].some(key=>key!=='offset')||!/^\d{1,5}$/.test(raw)||Number(raw)>10000)return adminFailure(400,'invalid_request');
    const offset=Number(raw);
    const rows=await env.BETA_DB.prepare(`SELECT application_id,user_id,full_name,email,institution,status,submitted_at FROM beta_applications ORDER BY submitted_at DESC,application_id LIMIT 101 OFFSET ?`).bind(offset).all();
    const data={schema_version:1,applications:(rows.results??[]).slice(0,100),next_offset:(rows.results??[]).length>100?offset+100:null};
    return bounded(data)?adminJson(200,data):adminFailure(503,'admin_unavailable');
  }catch{return adminFailure(503,'admin_unavailable');}
}
export async function readAdminApplication({request,env,params}) {
  const guard=await requireAdmin(request,env);if(guard.response)return guard.response;
  if(typeof params?.applicationId!=='string'||!id.test(params.applicationId))return adminFailure(400,'invalid_request');
  try {
    const data=await detail(env,params.applicationId);
    return data?(bounded(data)?adminJson(200,{schema_version:1,...data}):adminFailure(503,'admin_unavailable')):adminFailure(404,'application_not_found');
  }catch{return adminFailure(503,'admin_unavailable');}
}
function internalRequest(env,path,token,body,extra={}) {
  return new Request(env.BETA_ALLOWED_ORIGIN+path,{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+token,...extra},body:JSON.stringify(body)});
}
export async function adminApplicationAction({request,env,params}) {
  const guard=await requireAdmin(request,env,{mutation:true});if(guard.response)return guard.response;
  if(typeof params?.applicationId!=='string'||!id.test(params.applicationId))return adminFailure(400,'invalid_request');
  try {
    // Existing bounded parser; additionally cap admin actions at 2 KiB before dispatch.
    if(Number(request.headers.get('Content-Length'))>2048)return adminFailure(413,'request_too_large');
    const body=await readDeviceRequest(request);
    if(!body||new TextEncoder().encode(JSON.stringify(body)).length>2048||body.schema_version!==1)return adminFailure(400,'invalid_request');
    const app=await env.BETA_DB.prepare('SELECT application_id,user_id,status FROM beta_applications WHERE application_id=?').bind(params.applicationId).first();
    if(!app)return adminFailure(404,'application_not_found');
    let result;
    if(body.action==='review') {
      if(!exactDeviceFields(body,['schema_version','action','status','expected_status'])
          ||!['UNDER_REVIEW','APPROVED','REJECTED'].includes(body.status)||typeof body.expected_status!=='string')return adminFailure(400,'invalid_request');
      result=await transitionApplication({env,params,request:internalRequest(env,'/api/operator/applications/'+app.application_id+'/status',
        env.OPERATOR_STATUS_SYNC_TOKEN,{schema_version:1,status:body.status},{'X-QuantumStudio-Expected-Status':body.expected_status})});
    } else if(['issue','revoke'].includes(body.action)) {
      const fields=body.action==='issue'?['schema_version','action','activation_id']:['schema_version','action','activation_id','reason_code'];
      if(!exactDeviceFields(body,fields)||typeof body.activation_id!=='string'||!id.test(body.activation_id))return adminFailure(400,'invalid_request');
      const activation=await env.BETA_DB.prepare('SELECT status FROM beta_activations WHERE activation_request_id=? AND application_id=? AND user_id=?').bind(body.activation_id,app.application_id,app.user_id).first();
      if(!activation)return adminFailure(404,'activation_not_found');
      if(body.action==='issue')result=await issueLicenceViaService(env,body.activation_id);
      else result=await revokeActivation({env,params:{activationId:body.activation_id},request:internalRequest(env,'/api/operator/activations/'+body.activation_id+'/revoke',
        env.OPERATOR_ACTIVATION_REVOKE_TOKEN,{schema_version:1,expected_status:'AUTHORIZED',reason_code:body.reason_code})});
    } else return adminFailure(400,'invalid_request');
    if(!result.ok)return adminFailure([400,403,404,409,413].includes(result.status)?result.status:503,
      result.status===409?'admin_conflict':result.status===400?'invalid_request':'admin_action_unavailable');
    const operation=await result.json();
    const data=await detail(env,app.application_id);
    if(!data||!bounded(data))return adminFailure(503,'admin_unavailable');
    return adminJson(200,{schema_version:1,result:['published','already_current','revoked','already_revoked','updated'].includes(operation.result)?operation.result:'completed',...data});
  }catch{return adminFailure(503,'admin_action_unavailable');}
}
