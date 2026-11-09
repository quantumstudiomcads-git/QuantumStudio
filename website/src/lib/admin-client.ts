// Public client: same-origin session cookies only, no privileged credentials.
export type Application = {application_id:string;user_id:string|null;full_name:string;email:string;institution:string;status:string;submitted_at:string;country?:string;academic_role?:string;research_area?:string;intended_evaluation?:string;review_note?:string|null};
export type Entitlement = {status:string;plan_id:string;starts_at:string;expires_at:string;device_limit:number;revision:number};
export type Activation = {activation_request_id:string;installation_id:string;platform:string;architecture:string;app_version:string;device_public_key_hash:string|null;status:string;authorized_at:string|null;revoked_at:string|null;flag_reason:string|null;licence_id:string|null;licence_status:string|null;licence_issued_at:string|null;licence_expires_at:string|null;licence_revoked_at:string|null;kid:string|null;publication_status:string|null;revocation_reason_code:string|null};
export type AdminDetail = {schema_version:1;application:Application;user:{user_id:string;full_name:string;email:string;institution:string;status:string;created_at:string}|null;entitlement:Entitlement|null;activations:Activation[];result?:string};
export type AdminList = {schema_version:1;applications:Application[];next_offset:number|null};
export type AdminAction = {schema_version:1;action:'review';status:string;expected_status:string}|{schema_version:1;action:'issue';activation_id:string}|{schema_version:1;action:'revoke';activation_id:string;reason_code:string};
export class AdminClientError extends Error {}
const unavailable='The admin service is temporarily unavailable. Refresh before retrying an action.';
export function adminActionNotice(result?:string):string {
  return result==='already_current'?'Already current. The existing licence or review state is unchanged.':
    result==='published'?'Licence issued and published.':result==='revoked'||result==='already_revoked'?'Device revoked. Existing signed licence bytes remain unchanged.':'Review updated.';
}
export function canIssue(detail:AdminDetail,activation:Activation):boolean {
  return activation.status==='AUTHORIZED'&&!!activation.authorized_at&&!activation.revoked_at&&!activation.flag_reason&&!!activation.device_public_key_hash
    &&['APPROVED','LICENSE_ISSUED'].includes(detail.application.status)&&detail.entitlement?.status==='CURRENT';
}
export function createAdminClient(fetcher:typeof fetch=fetch) {
  async function call<T>(path:string,body?:AdminAction):Promise<T> {
    const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),45000);
    try {
      const response=await fetcher(path,{method:body?'POST':'GET',credentials:'same-origin',cache:'no-store',redirect:'error',signal:controller.signal,
        headers:body?{'Content-Type':'application/json','X-QuantumStudio-Admin':'1'}:{Accept:'application/json'},...(body?{body:JSON.stringify(body)}:{})});
      if(!response.ok)throw new AdminClientError(response.status===401?'Sign in with an approved administrator account, then return to /admin.':
        response.status===403?'Administrator access or request verification was denied.':
        response.status===409?'The record changed or is not eligible. Refresh before retrying.':unavailable);
      const data=await response.json();
      if(data?.schema_version!==1 || (!Array.isArray(data.applications)&&(!data.application||!Array.isArray(data.activations))))throw new AdminClientError(unavailable);
      return data as T;
    }catch(error){if(error instanceof AdminClientError)throw error;throw new AdminClientError(unavailable);}
    finally{clearTimeout(timer);}
  }
  return {list:(offset=0)=>call<AdminList>('/api/admin/applications?offset='+offset),
    detail:(id:string)=>call<AdminDetail>('/api/admin/applications/'+encodeURIComponent(id)),
    action:(id:string,body:AdminAction)=>call<AdminDetail>('/api/admin/applications/'+encodeURIComponent(id)+'/action',body)};
}
