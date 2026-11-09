// Shared metadata persistence. Callers authenticate and validate before entry.
const json = (status, body) => new Response(JSON.stringify(body), {status, headers: {
  'Content-Type':'application/json; charset=utf-8', 'Cache-Control':'no-store', 'X-Content-Type-Options':'nosniff',
}});
const fail = (status, code) => json(status, {error:{code}});
export async function persistLicenceMetadata(env, activationId, body) {
  try {
    const row = await env.BETA_DB.prepare('SELECT installation_id, status, licence_id, licence_status, licence_issued_at, licence_expires_at, licence_revoked_at FROM beta_activations WHERE activation_request_id = ?').bind(activationId).first();
    if (!row || row.installation_id !== body.installation_id) return fail(404, 'activation_not_found');
    if (row.status !== 'AUTHORIZED') return fail(409, 'activation_not_authorized');
    if (row.licence_id) {
      if (row.licence_id !== body.licence_id || row.licence_status !== body.status
          || row.licence_issued_at !== body.issued_at || row.licence_expires_at !== body.expires_at
          || row.licence_revoked_at !== body.revoked_at) return fail(409, 'licence_metadata_conflict');
      return json(200, {schema_version: 1, result: 'already_current'});
    }
    const result = await env.BETA_DB.prepare(`UPDATE beta_activations SET licence_id = ?, licence_status = ?,
      licence_issued_at = ?, licence_expires_at = ?, licence_revoked_at = ?
      WHERE activation_request_id = ? AND installation_id = ? AND status = 'AUTHORIZED' AND licence_id IS NULL`).bind(
      body.licence_id, body.status, body.issued_at, body.expires_at, body.revoked_at, activationId, body.installation_id,
    ).run();
    if (result.meta?.changes !== 1) return fail(409, 'activation_changed');
    return json(200, {schema_version: 1, result: 'updated'});
  } catch { return fail(503, 'service_unavailable'); }
}
