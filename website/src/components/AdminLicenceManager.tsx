import React,{useEffect,useState} from 'react';
import Layout from '@theme/Layout';
import Head from '@docusaurus/Head';
import {createAdminClient,adminActionNotice,type AdminDetail,type AdminList,type AdminAction} from '../lib/admin-client';
import {AdminApplicationDetail} from './AdminApplicationDetail';
import styles from './AdminLicenceManager.module.css';

const api=createAdminClient();
const shown=(value:unknown)=>value===null||value===undefined||value===''?'Not recorded':String(value);
export default function AdminLicenceManager() {
  const [list,setList]=useState<AdminList|null>(null),[offset,setOffset]=useState(0),[detail,setDetail]=useState<AdminDetail|null>(null);
  const [busy,setBusy]=useState(true),[notice,setNotice]=useState('Loading administrator access...');
  useEffect(()=>{let live=true;api.list().then(data=>{if(live){setList(data);setNotice('Select an application to inspect authoritative records.');}})
    .catch(error=>{if(live)setNotice(error.message);}).finally(()=>{if(live)setBusy(false);});return()=>{live=false;};},[]);
  async function refresh(nextOffset=offset) {
    setBusy(true);setNotice('Refreshing...');
    try {const data=await api.list(nextOffset);setList(data);setOffset(nextOffset);
      if(detail&&nextOffset===offset)setDetail(await api.detail(detail.application.application_id));else setDetail(null);
      setNotice('Authoritative records refreshed.');}catch(error){setNotice((error as Error).message);setDetail(null);}finally{setBusy(false);}
  }
  async function select(id:string) {
    setBusy(true);setDetail(null);setNotice('Loading application...');
    try {setDetail(await api.detail(id));setNotice('Application loaded.');}catch(error){setNotice((error as Error).message);}finally{setBusy(false);}
  }
  async function action(body:AdminAction) {
    if(!detail||busy)return;setBusy(true);setNotice('Applying operator action...');
    try {const data=await api.action(detail.application.application_id,body);setDetail(data);
      setList(current=>current?{...current,applications:current.applications.map(a=>a.application_id===data.application.application_id?data.application:a)}:current);
      setNotice(adminActionNotice(data.result));}catch(error){setNotice((error as Error).message);setDetail(null);}finally{setBusy(false);}
  }
  return <Layout title="Admin / Licence Manager" description="Quantum Studio operator console"><Head><meta name="robots" content="noindex,nofollow"/></Head>
    <main className={styles.console}><h1>Admin / Licence Manager</h1><p>Applications, account entitlements, device activations and immutable licences.</p>
      <div className={styles.actions}><a href="/login?returnTo=%2Fadmin">Sign in</a><button disabled={busy} onClick={()=>refresh()}>Refresh</button></div>
      <p className={styles.notice} role="status" aria-live="polite">{notice}</p>
      <div className={styles.columns}><section className={styles.panel} aria-label="Applications"><h2>Applications</h2>
        {list&&<><div className={styles.scroll}><table className={styles.table}><thead><tr><th>Applicant</th><th>Institution</th><th>Status / created</th><th>Inspect</th></tr></thead>
          <tbody>{list.applications.map(a=><tr key={a.application_id}><td>{a.full_name}<br/>{a.email}<br/><small>Application: {a.application_id}<br/>User: {shown(a.user_id)}</small></td>
            <td>{a.institution}</td><td>{a.status}<br/>{a.submitted_at}</td><td><button disabled={busy} onClick={()=>select(a.application_id)}>Inspect {a.full_name}</button></td></tr>)}</tbody></table></div>
          {!list.applications.length&&<p>No applications.</p>}<div className={styles.actions}><button disabled={busy||offset===0} onClick={()=>refresh(Math.max(0,offset-100))}>Previous</button>
          <button disabled={busy||list.next_offset===null} onClick={()=>refresh(list.next_offset??offset)}>Next</button></div></>}
      </section>{detail?<AdminApplicationDetail key={detail.application.application_id} detail={detail} busy={busy} onAction={action}/>:<section className={styles.panel}><h2>Application detail</h2><p>Select an application. Administrator access is required.</p></section>}</div>
    </main></Layout>;
}
