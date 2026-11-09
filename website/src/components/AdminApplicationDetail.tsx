import React,{useState} from 'react';
import {canIssue,type AdminDetail,type AdminAction} from '../lib/admin-client';
import styles from './AdminLicenceManager.module.css';

const reasons=['DEVICE_REPLACED','DEVICE_LOST','USER_REQUEST','BETA_ACCESS_REVOKED','ADMINISTRATIVE','OTHER'];
const shown=(value:unknown)=>value===null||value===undefined||value===''?'Not recorded':String(value);
function Fields({values}:{values:Record<string,unknown>}) {
  return <dl className={styles.fields}>{Object.entries(values).map(([name,value])=><React.Fragment key={name}><dt>{name}</dt><dd>{shown(value)}</dd></React.Fragment>)}</dl>;
}
export function AdminApplicationDetail({detail,busy=false,onAction=()=>{}}:{detail:AdminDetail;busy?:boolean;onAction?:(body:AdminAction)=>void}) {
  const [confirm,setConfirm]=useState<string|null>(null),[reason,setReason]=useState('ADMINISTRATIVE');
  const app=detail.application;
  return <section className={styles.panel} aria-label="Selected application"><h2>{app.full_name}</h2>
    <Fields values={{'Application ID':app.application_id,'User ID':app.user_id,Email:app.email,Institution:app.institution,Status:app.status,
      Submitted:app.submitted_at,Country:app.country,'Academic role':app.academic_role,'Research area':app.research_area,'Intended evaluation':app.intended_evaluation,'Review note':app.review_note}}/>
    <div className={styles.actions}>
      {app.status==='APPLIED'&&<button disabled={busy} onClick={()=>onAction({schema_version:1,action:'review',status:'UNDER_REVIEW',expected_status:app.status})}>Begin review</button>}
      {app.status==='UNDER_REVIEW'&&<><button disabled={busy} onClick={()=>onAction({schema_version:1,action:'review',status:'APPROVED',expected_status:app.status})}>Approve</button>
      <button disabled={busy} onClick={()=>{if(window.confirm('Reject this application? Rejection is terminal.'))onAction({schema_version:1,action:'review',status:'REJECTED',expected_status:app.status});}}>Reject</button></>}
    </div>
    <h3>User</h3>{detail.user?<Fields values={{'User ID':detail.user.user_id,Name:detail.user.full_name,Email:detail.user.email,Status:detail.user.status,Created:detail.user.created_at}}/>:<p>No linked user.</p>}
    <h3>Account entitlement</h3>{detail.entitlement?<Fields values={{Status:detail.entitlement.status,Plan:detail.entitlement.plan_id,Starts:detail.entitlement.starts_at,
      Expires:detail.entitlement.expires_at,'Device limit':detail.entitlement.device_limit,Revision:detail.entitlement.revision}}/>:<p>No account entitlement.</p>}
    <h3>Devices and licences</h3>{!detail.activations.length&&<p>No device activations.</p>}
    {detail.activations.map(a=><article className={styles.device} key={a.activation_request_id}>
      <Fields values={{'Activation ID':a.activation_request_id,'Installation ID':a.installation_id,Platform:a.platform,Version:a.app_version,
        'Device hash':a.device_public_key_hash? a.device_public_key_hash.slice(0,12)+'...'+a.device_public_key_hash.slice(-8):null,
        Status:a.status,Authorized:a.authorized_at,Revoked:a.revoked_at,'Flag reason':a.flag_reason,'Revocation reason':a.revocation_reason_code,
        'Licence ID':a.licence_id,'Licence status':a.licence_status,'Licence issued':a.licence_issued_at,'Licence expiry':a.licence_expires_at,
        'Licence revoked':a.licence_revoked_at,'Signing issuer':a.kid,Publication:a.publication_status}}/>
      {a.status==='REVOKED'&&<p>Device authorization is revoked. A signed envelope does not authorize this device.</p>}
      <div className={styles.actions}>
        {canIssue(detail,a)&&<button disabled={busy} onClick={()=>onAction({schema_version:1,action:'issue',activation_id:a.activation_request_id})}>{a.licence_id?'Confirm / retry licence issuance':'Issue Licence'}</button>}
        {a.status==='AUTHORIZED'&&<button disabled={busy} onClick={()=>{setConfirm(a.activation_request_id);setReason('ADMINISTRATIVE');}}>Revoke Device</button>}
      </div>
      {confirm===a.activation_request_id&&<div role="group" aria-label="Confirm device revocation"><p>Revocation is terminal for this activation. The account entitlement and its original expiry remain unchanged.</p>
        <label>Reason <select disabled={busy} value={reason} onChange={e=>setReason(e.target.value)}>{reasons.map(r=><option key={r}>{r}</option>)}</select></label>
        <div className={styles.actions}><button disabled={busy} onClick={()=>{setConfirm(null);onAction({schema_version:1,action:'revoke',activation_id:a.activation_request_id,reason_code:reason});}}>Confirm revocation</button>
        <button disabled={busy} onClick={()=>setConfirm(null)}>Cancel</button></div></div>}
    </article>)}
  </section>;
}
