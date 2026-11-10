import React,{useState} from 'react';
import {canIssue,type AdminDetail,type AdminAction} from '../lib/admin-client';
import styles from './AdminLicenceManager.module.css';

const reasons=['DEVICE_REPLACED','DEVICE_LOST','USER_REQUEST','BETA_ACCESS_REVOKED','ADMINISTRATIVE','OTHER'];
const shown=(value:unknown)=>value===null||value===undefined||value===''?'Not recorded':String(value);
export function AdminStatus({value}:{value:string|null}) {
  return <span className={styles.badge} data-status={value??'UNKNOWN'}>{value??'Not recorded'}</span>;
}
export function adminDate(value:string|null) {
  if(!value)return 'Not recorded';
  const date=new Date(value);
  return Number.isNaN(date.getTime())?'Not recorded':new Intl.DateTimeFormat('en-GB',{day:'2-digit',month:'short',year:'numeric',timeZone:'UTC'}).format(date);
}
function Fields({values}:{values:Record<string,unknown>}) {
  return <dl className={styles.fields}>{Object.entries(values).map(([name,value])=><div key={name}><dt>{name}</dt><dd>{shown(value)}</dd></div>)}</dl>;
}
export function AdminApplicationDetail({detail,busy=false,onAction=()=>{}}:{detail:AdminDetail;busy?:boolean;onAction?:(body:AdminAction)=>void}) {
  const [confirm,setConfirm]=useState<string|null>(null),[reason,setReason]=useState('ADMINISTRATIVE'),[copyNotice,setCopyNotice]=useState('');
  const app=detail.application;
  async function copy(value:string,label:string) {
    try{await navigator.clipboard.writeText(value);setCopyNotice(label+' copied.');}
    catch{setCopyNotice('Copy unavailable. Select the identifier below to copy manually.');}
  }
  return <section className={styles.detail} aria-label="Selected application" aria-busy={busy}>
    <section className={styles.panel} id="admin-applicant"><div className={styles.sectionHead}><div><p className={styles.eyebrow}>Applicant</p><h2>{app.full_name}</h2></div><AdminStatus value={app.status}/></div>
      <p className={styles.email}>{app.email}</p>
      <Fields values={{Institution:app.institution,Submitted:adminDate(app.submitted_at),Country:app.country,'Academic role':app.academic_role,'Research area':app.research_area}}/>
      <div className={styles.prose}><h3>Intended evaluation</h3><p>{shown(app.intended_evaluation)}</p>{app.review_note&&<><h3>Review note</h3><p>{app.review_note}</p></>}</div>
      <details className={styles.metadata}><summary>Identifiers &amp; account metadata</summary>
        <div className={styles.actions}><button disabled={busy} onClick={()=>copy(app.application_id,'Application ID')}>Copy application ID</button>{app.user_id&&<button disabled={busy} onClick={()=>copy(app.user_id!,'User ID')}>Copy user ID</button>}</div>
        <p role="status">{copyNotice}</p><Fields values={{'Application ID':app.application_id,'User ID':app.user_id,'Account status':detail.user?.status,'Account created':adminDate(detail.user?.created_at??null)}}/>
      </details>
      <div className={styles.actionBlock}><h3>Application actions</h3><div className={styles.actions}>
        {app.status==='APPLIED'&&<button className={styles.primary} disabled={busy} onClick={()=>onAction({schema_version:1,action:'review',status:'UNDER_REVIEW',expected_status:app.status})}>Begin review</button>}
        {app.status==='UNDER_REVIEW'&&<><button className={styles.primary} disabled={busy} onClick={()=>onAction({schema_version:1,action:'review',status:'APPROVED',expected_status:app.status})}>Approve</button>
          <button className={styles.danger} disabled={busy} onClick={()=>{if(window.confirm('Reject this application? Rejection is terminal.'))onAction({schema_version:1,action:'review',status:'REJECTED',expected_status:app.status});}}>Reject</button></>}
        {!['APPLIED','UNDER_REVIEW'].includes(app.status)&&<p className={styles.muted}>No review actions available for this status.</p>}
      </div></div>
    </section>
    <section className={styles.panel} id="admin-entitlements"><div className={styles.sectionHead}><h2>Entitlement</h2>{detail.entitlement&&<AdminStatus value={detail.entitlement.status}/>}</div>
      {detail.entitlement?<Fields values={{Plan:detail.entitlement.plan_id,Start:adminDate(detail.entitlement.starts_at),Expiry:adminDate(detail.entitlement.expires_at),'Device limit':detail.entitlement.device_limit,Revision:detail.entitlement.revision}}/>:<p className={styles.empty}>No account entitlement recorded.</p>}
    </section>
    <section className={styles.panel} id="admin-devices"><div className={styles.sectionHead}><h2>Devices</h2><span className={styles.muted}>{detail.activations.length} recorded</span></div>
      {!detail.activations.length&&<p className={styles.empty}>No device activations recorded.</p>}
      {detail.activations.map(a=><article className={styles.device} key={a.activation_request_id}>
        <div className={styles.sectionHead}><h3>{a.platform||'Device'} <span className={styles.identifier}>{a.installation_id.slice(0,12)}...</span></h3><AdminStatus value={a.status}/></div>
        <Fields values={{Version:a.app_version,Activated:adminDate(a.authorized_at),...(a.revoked_at?{Revoked:adminDate(a.revoked_at)}:{}),'Revocation reason':a.revocation_reason_code}}/>
        <details className={styles.metadata}><summary>Device identifiers &amp; diagnostics</summary><Fields values={{'Activation ID':a.activation_request_id,'Installation ID':a.installation_id,'Device hash':a.device_public_key_hash,'Flag reason':a.flag_reason}}/></details>
        {a.status==='REVOKED'&&<p className={styles.muted}>Device authorization is revoked. A signed envelope does not authorize this device.</p>}
        {a.status==='AUTHORIZED'&&<div className={styles.actions}><button className={styles.danger} disabled={busy} onClick={()=>{setConfirm(a.activation_request_id);setReason('ADMINISTRATIVE');}}>Revoke Device</button></div>}
        {confirm===a.activation_request_id&&<div className={styles.confirmation} role="group" aria-label="Confirm device revocation"><h3>Revoke this device?</h3><p>Revocation is terminal for this activation. The account entitlement and its original expiry remain unchanged.</p>
          <label>Reason <select disabled={busy} value={reason} onChange={e=>setReason(e.target.value)}>{reasons.map(r=><option key={r}>{r}</option>)}</select></label>
          <div className={styles.actions}><button className={styles.danger} disabled={busy} onClick={()=>{setConfirm(null);onAction({schema_version:1,action:'revoke',activation_id:a.activation_request_id,reason_code:reason});}}>Confirm revocation</button><button disabled={busy} onClick={()=>setConfirm(null)}>Cancel</button></div>
        </div>}
      </article>)}
    </section>
    <section className={styles.panel} id="admin-licences"><h2>Licences</h2>
      {!detail.activations.length&&<p className={styles.empty}>No devices available for licence issuance.</p>}
      {detail.activations.map(a=><article className={styles.device} key={a.activation_request_id}>
        <div className={styles.sectionHead}><h3>{a.platform||'Device'} <span className={styles.identifier}>{a.installation_id.slice(0,12)}...</span></h3><AdminStatus value={a.licence_status}/></div>
        <Fields values={{'Licence ID':a.licence_id,Issued:adminDate(a.licence_issued_at),Expiry:adminDate(a.licence_expires_at),'Issuer / kid':a.kid,Publication:a.publication_status}}/>
        {canIssue(detail,a)&&<div className={styles.actions}><button className={styles.primary} disabled={busy} onClick={()=>onAction({schema_version:1,action:'issue',activation_id:a.activation_request_id})}>{a.licence_id?'Confirm / retry licence issuance':'Issue Licence'}</button></div>}
      </article>)}
    </section>
  </section>;
}
