// Authoritative deployed delivery/status facts. No signer, operator credential or service call.
import {sha256Hex} from './auth.js';

export const readPublicLicenceState = (db,id) => db.prepare(`SELECT a.*,
  app.status AS application_status, app.user_id AS application_user_id, u.status AS user_status,
  ent.entitlement_id, ent.user_id AS entitlement_user_id, ent.application_id AS entitlement_application_id,
  ent.plan_id AS entitlement_plan, ent.starts_at, ent.expires_at AS entitlement_expires_at,
  ent.device_limit, ent.revision AS entitlement_revision,
  p.licence_id AS published_licence_id, p.status AS publication_status,
  p.envelope_json, p.envelope_sha256
  FROM beta_activations a JOIN beta_applications app ON app.application_id=a.application_id
  JOIN users u ON u.user_id=a.user_id
  LEFT JOIN account_entitlements ent ON ent.application_id=a.application_id AND ent.user_id=a.user_id
  LEFT JOIN published_licences p ON p.activation_request_id=a.activation_request_id
  WHERE a.activation_request_id=?`).bind(id).first();

export async function currentPublicLicenceState(row,{allowExpired=false}={}) {
  if(!row)return false;
  const now=Math.floor(Date.now()/1000),starts=Date.parse(row.starts_at)/1000,expires=Date.parse(row.entitlement_expires_at)/1000;
  if(!['AUTHORIZED','REVOKED'].includes(row.status) || (row.status==='AUTHORIZED'&&row.revoked_at!=null) || row.flag_reason!=null || !row.authorized_at
      || row.user_status!=='VERIFIED' || row.application_user_id!==row.user_id
      || !(['APPROVED','LICENSE_ISSUED'].includes(row.application_status)
        || (allowExpired&&row.application_status==='EXPIRED'&&expires<=now))
      || !row.entitlement_id || row.entitlement_user_id!==row.user_id || row.entitlement_application_id!==row.application_id
      || row.entitlement_plan!=='beta' || !Number.isSafeInteger(row.device_limit) || row.device_limit<1
      || !Number.isSafeInteger(row.entitlement_revision)||row.entitlement_revision<1
      || !Number.isSafeInteger(starts)||!Number.isSafeInteger(expires)||expires-starts!==90*86400
      || starts>now || (!allowExpired&&expires<=now)
      || typeof row.device_public_key_hash!=='string'||!/^[0-9a-f]{64}$/.test(row.device_public_key_hash)
      || row.installation_id!=='dev_'+row.device_public_key_hash.slice(0,32))return false;
  if(row.licence_id==null)return row.published_licence_id==null&&[row.licence_status,row.licence_issued_at,row.licence_expires_at,row.licence_revoked_at].every(x=>x==null);
  if(row.licence_status!=='ISSUED'||row.licence_revoked_at!=null||Date.parse(row.licence_expires_at)/1000!==expires
      || !Number.isFinite(Date.parse(row.licence_issued_at)))return false;
  if(row.published_licence_id==null)return row.envelope_json==null; // Interrupted metadata/publication can remain pending.
  try {
    const e=JSON.parse(row.envelope_json);
    return row.publication_status==='PUBLISHED'&&row.published_licence_id===row.licence_id
      &&await sha256Hex(row.envelope_json)===row.envelope_sha256
      &&e.schema_version===1&&e.licence_id===row.licence_id&&e.device_id===row.installation_id&&e.device_public_key_hash===row.device_public_key_hash
      &&e.approved_application_ref===row.application_id&&e.account_id==='sub_'+row.application_id&&e.subject_id===e.account_id
      &&e.subject_type==='beta_applicant'&&e.product==='Quantum Studio'&&e.channel==='beta'&&e.plan_id==='pro'
      &&e.expires_at===expires&&e.offline_until===expires&&e.registered_device_limit===row.device_limit
      &&e.concurrent_session_limit===1&&e.offline_device_limit===1&&e.entitlement_version===1
      &&e.issued_at===Date.parse(row.licence_issued_at)/1000&&e.not_before>=starts&&e.not_before>=e.issued_at&&e.not_before<=now
      &&typeof e.kid==='string'&&/^lic-[a-z0-9][a-z0-9._-]{0,63}$/.test(e.kid);
  }catch{return false;}
}
