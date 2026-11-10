import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {expect,it} from 'vitest';
import {AdminApplicationDetail,AdminStatus,adminDate} from '../src/components/AdminApplicationDetail';
const application={application_id:'application-fixture',user_id:'user-fixture',full_name:'Researcher <unsafe>',email:'researcher@example.test',institution:'Institute',status:'UNDER_REVIEW',submitted_at:'2026-11-10T12:00:00Z'};
const activation={activation_request_id:'activation-fixture',installation_id:'installation-fixture-long',platform:'Windows',app_version:'0.2',status:'AUTHORIZED',authorized_at:'2026-11-10T12:00:00Z',revoked_at:null,flag_reason:null,device_public_key_hash:'hash',licence_id:null,licence_status:null};
const detail={schema_version:1,application,user:null,entitlement:{status:'CURRENT',plan_id:'pro',starts_at:'2026-11-10',expires_at:'2027-02-08',device_limit:1,revision:1},activations:[activation]};
const render=(data=detail,busy=false)=>renderToStaticMarkup(React.createElement(AdminApplicationDetail,{detail:data,busy}));
it('groups applicant, entitlement, devices and licences into navigable sections',()=>{
  const html=render();
  for(const section of ['admin-applicant','admin-entitlements','admin-devices','admin-licences'])expect(html).toContain('id="'+section+'"');
  expect(html).toContain('Researcher &lt;unsafe&gt;');
  expect(html).toContain('Copy application ID');expect(html).toContain('Copy user ID');
  expect(html).toMatch(/<details[^>]*>[\s\S]*application-fixture[\s\S]*<\/details>/);
  expect(html).toContain('Approve');expect(html).toContain('Reject');expect(html).toContain('Revoke Device');
  expect(html).not.toContain('Begin review');expect(html).not.toContain('schema_version');
});
it.each(['APPLIED','APPROVED','REJECTED'])('preserves valid review controls for %s',status=>{
  const html=render({...detail,application:{...application,status}});
  expect(html.includes('>Begin review<')).toBe(status==='APPLIED');
  expect(html).not.toContain('>Approve<');expect(html).not.toContain('>Reject<');
});
it('disables all operator buttons while a request is active',()=>{
  const buttons=render(detail,true).match(/<button[^>]*>/g);
  expect(buttons.length).toBeGreaterThan(0);
  for(const button of buttons)expect(button).toContain('disabled');
});
it('renders empty entitlement and device states without raw JSON',()=>{
  const html=render({...detail,entitlement:null,activations:[]});
  expect(html).toContain('No account entitlement recorded');expect(html).toContain('No device activations recorded');expect(html).toContain('No devices available');
});
it('shows licence issuance only for eligible records',()=>{
  const approved={...detail,application:{...application,status:'APPROVED'}};
  expect(render(approved)).toContain('Issue Licence');
  expect(render({...approved,activations:[{...activation,status:'REVOKED'}]})).not.toContain('Issue Licence');
});
it.each(['APPLIED','APPROVED','REJECTED','ACTIVE','REVOKED','EXPIRED'])('renders %s as a status badge',value=>{
  expect(renderToStaticMarkup(React.createElement(AdminStatus,{value}))).toContain('data-status="'+value+'"');
});
it('formats dates consistently in UTC and handles missing dates',()=>{
  expect(adminDate('2026-11-10T23:59:00Z')).toBe('10 Nov 2026');expect(adminDate(null)).toBe('Not recorded');expect(adminDate('bad')).toBe('Not recorded');
});
