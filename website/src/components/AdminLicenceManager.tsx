import React,{useEffect,useState} from 'react';
import Layout from '@theme/Layout';
import Head from '@docusaurus/Head';
import {createAdminClient,adminActionNotice,type AdminDetail,type AdminList,type AdminAction} from '../lib/admin-client';
import {AdminApplicationDetail,AdminStatus,adminDate} from './AdminApplicationDetail';
import styles from './AdminLicenceManager.module.css';

const api=createAdminClient();
export default function AdminLicenceManager() {
  const [list,setList]=useState<AdminList|null>(null),[offset,setOffset]=useState(0),[detail,setDetail]=useState<AdminDetail|null>(null);
  const [query,setQuery]=useState('');
  const [noticeKind,setNoticeKind]=useState<'info'|'success'|'error'>('info');
  const [busy,setBusy]=useState(true),[notice,setNotice]=useState('Loading administrator access...');
  useEffect(()=>{let live=true;api.list().then(data=>{if(live){setList(data);setNotice('Select an application to inspect authoritative records.');}})
    .catch(error=>{if(live){setNotice(error.message);setNoticeKind('error');}}).finally(()=>{if(live)setBusy(false);});return()=>{live=false;};},[]);
  async function refresh(nextOffset=offset) {
    setBusy(true);setNoticeKind('info');setNotice('Refreshing...');
    try {const data=await api.list(nextOffset);setList(data);setOffset(nextOffset);
      if(detail&&nextOffset===offset)setDetail(await api.detail(detail.application.application_id));else setDetail(null);
      setNotice('Authoritative records refreshed.');setNoticeKind('success');}catch(error){setNoticeKind('error');setNotice((error as Error).message);setDetail(null);}finally{setBusy(false);}
  }
  async function select(id:string) {
    setBusy(true);setNoticeKind('info');setDetail(null);setNotice('Loading application...');
    try {setDetail(await api.detail(id));setNotice('Application loaded.');}catch(error){setNoticeKind('error');setNotice((error as Error).message);}finally{setBusy(false);}
  }
  async function action(body:AdminAction) {
    if(!detail||busy)return;setBusy(true);setNoticeKind('info');setNotice('Applying operator action...');
    try {const data=await api.action(detail.application.application_id,body);setDetail(data);
      setList(current=>current?{...current,applications:current.applications.map(a=>a.application_id===data.application.application_id?data.application:a)}:current);
      setNotice(adminActionNotice(data.result));setNoticeKind('success');}catch(error){setNoticeKind('error');setNotice((error as Error).message);setDetail(null);}finally{setBusy(false);}
  }
  return <Layout title="Admin / Licence Manager" description="Quantum Studio operator console"><Head><meta name="robots" content="noindex,nofollow"/></Head>
    <main className={styles.console}>
      <header className={styles.topbar}><div><p className={styles.eyebrow}>Quantum Studio / Operator console</p><h1>Admin / Licence Manager</h1></div>
        <div className={styles.actions}><a href="/login?returnTo=%2Fadmin">Admin sign in</a><button disabled={busy} onClick={()=>refresh()}>{busy?'Working...':'Refresh'}</button></div>
      </header>
      <nav className={styles.navigation} aria-label="Licence Manager sections"><a href="#admin-applications">Applications</a><a href="#admin-entitlements">Entitlements</a><a href="#admin-devices">Devices</a><a href="#admin-licences">Licences</a></nav>
      <p className={styles.notice} data-kind={noticeKind} role={noticeKind==='error'?'alert':'status'} aria-live="polite">{busy&&<span className={styles.loading} aria-hidden="true"/>}{notice}</p>
      <div className={styles.columns} aria-busy={busy}><section className={styles.panel} id="admin-applications" aria-label="Applications">
        <div className={styles.sectionHead}><h2>Applications</h2><span className={styles.muted}>{list?`${list.applications.length} on this page`:'Loading'}</span></div>
        <label className={styles.search}>Find on this page<input type="search" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Name, email or institution"/></label>
        {list&&<><div className={styles.applicationList}>{list.applications.filter(a=>[a.full_name,a.email,a.institution].some(value=>value.toLowerCase().includes(query.toLowerCase()))).map(a=><article key={a.application_id} className={styles.application} data-selected={detail?.application.application_id===a.application_id}>
          <div className={styles.sectionHead}><h3>{a.full_name}</h3><AdminStatus value={a.status}/></div>
          <p className={styles.email}>{a.email}</p><p className={styles.muted}>{a.institution}</p>
          <div className={styles.listFooter}><time dateTime={a.submitted_at}>Submitted {adminDate(a.submitted_at)}</time><button disabled={busy} aria-pressed={detail?.application.application_id===a.application_id} aria-label={`Inspect ${a.full_name}`} onClick={()=>select(a.application_id)}>Inspect</button></div>
        </article>)}</div>
          {!list.applications.length&&<p className={styles.empty}>No applications have been submitted.</p>}
          {!!list.applications.length&&!list.applications.some(a=>[a.full_name,a.email,a.institution].some(value=>value.toLowerCase().includes(query.toLowerCase())))&&<p className={styles.empty}>No matching applications on this page.</p>}
          <div className={styles.pagination}><button disabled={busy||offset===0} onClick={()=>refresh(Math.max(0,offset-100))}>Previous</button><span>Page {Math.floor(offset/100)+1}</span><button disabled={busy||list.next_offset===null} onClick={()=>refresh(list.next_offset??offset)}>Next</button></div>
        </>}
        {!list&&<p className={styles.empty}>{busy?'Loading applications...':'Applications unavailable. Sign in or refresh to try again.'}</p>}
      </section>{detail?<AdminApplicationDetail key={detail.application.application_id} detail={detail} busy={busy} onAction={action}/>:<section className={`${styles.panel} ${styles.placeholder}`}><p className={styles.eyebrow}>Application workspace</p><h2>{busy?'Loading records...':'Select an application'}</h2><p>Inspect an applicant to review their details, entitlement, devices and licences.</p><p className={styles.muted}>Actions become available when the selected record is eligible.</p></section>}</div>
    </main></Layout>;
}
