import {describe, expect, it} from 'vitest';
import {onRequestPost} from '../functions/api/operator/activations/[activationId]/licence.js';

const activationId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const installation = `dev_${'a'.repeat(32)}`;
const token = 'synthetic-dedicated-licence-token';
const metadata = {
  schema_version: 1, installation_id: installation,
  licence_id: 'lic_12345678-1234-4123-8123-123456789abc', status: 'ISSUED',
  issued_at: '2026-10-19T12:00:00.000Z', expires_at: '2027-01-17T12:00:00.000Z', revoked_at: null,
};

class FakeD1 {
  constructor(status = 'AUTHORIZED') {
    this.row = {installation_id: installation, status, licence_id: null};
    this.writes = 0;
  }
  prepare(sql) {
    const statement = {
      values: [],
      bind: (...values) => { statement.values = values; return statement; },
      first: async () => ({...this.row}),
      run: async () => {
        if (!sql.includes('UPDATE beta_activations')) throw new Error('unexpected query');
        const [id, status, issued, expires, revoked, activation, device] = statement.values;
        if (activation !== activationId || device !== this.row.installation_id
            || this.row.status !== 'AUTHORIZED' || this.row.licence_id) return {meta: {changes: 0}};
        Object.assign(this.row, {licence_id: id, licence_status: status,
          licence_issued_at: issued, licence_expires_at: expires, licence_revoked_at: revoked});
        this.writes += 1;
        return {meta: {changes: 1}};
      },
    };
    return statement;
  }
}

function post(db = new FakeD1(), body = metadata, bearer = token, env = {}, id = activationId) {
  const headers = {'Content-Type': 'application/json'};
  if (bearer !== null) headers.Authorization = `Bearer ${bearer}`;
  return onRequestPost({
    request: new Request(`http://localhost/api/operator/activations/${id}/licence`, {
      method: 'POST', headers, body: JSON.stringify(body),
    }),
    env: {BETA_ENVIRONMENT: 'local', BETA_DB: db, OPERATOR_LICENCE_SYNC_TOKEN: token, ...env},
    params: {activationId: id},
  });
}

describe('TEST licence metadata', () => {
  it('requires a dedicated write token, never the read or status tokens', async () => {
    for (const bearer of [null, 'synthetic-read-token', 'synthetic-status-token']) {
      expect((await post(new FakeD1(), metadata, bearer, {
        OPERATOR_SYNC_TOKEN: 'synthetic-read-token', OPERATOR_STATUS_SYNC_TOKEN: 'synthetic-status-token',
      })).status).toBe(bearer === null ? 401 : 403);
    }
    expect((await post(new FakeD1(), metadata, token, {OPERATOR_LICENCE_SYNC_TOKEN: ''})).status).toBe(503);
  });

  it('mirrors safe metadata and retries without another write', async () => {
    const db = new FakeD1();
    const response = await post(db);
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({schema_version: 1, result: 'updated'});
    expect(response.headers.get('cache-control')).toBe('no-store');
    expect(await (await post(db)).json()).toEqual({schema_version: 1, result: 'already_current'});
    expect(db.writes).toBe(1);
    expect((await post(db, {...metadata, licence_id: 'lic_22345678-1234-4123-8123-123456789abc'})).status).toBe(409);
    expect(JSON.stringify(db.row)).not.toMatch(/signature|private|secret|seed/);
  });

  it.each([
    {}, {...metadata, signature: 'never-send'}, {...metadata, private_key: 'never-send'},
    {...metadata, schema_version: true}, {...metadata, licence_id: 'invalid'},
    {...metadata, issued_at: 1792400000}, {...metadata, expires_at: metadata.issued_at},
    {...metadata, revoked_at: metadata.issued_at}, {...metadata, status: 'AUTHORIZED'},
    {...metadata, expires_at: 'bad'}, {...metadata, issued_at: '2026-10-19T12:00:00'},
  ])('rejects invalid or private metadata without exposing submitted fields', async (body) => {
    const db = new FakeD1();
    const response = await post(db, body);
    expect(response.status).toBe(400);
    expect(await response.json()).toEqual({error: {code: 'invalid_metadata'}});
    expect(db.writes).toBe(0);
  });

  it.each(['FLAGGED', 'REVOKED'])('does not license a %s activation', async (status) => {
    const db = new FakeD1(status);
    expect((await post(db)).status).toBe(409);
    expect(db.writes).toBe(0);
  });

  it('checks activation identity and bounded input', async () => {
    expect((await post(new FakeD1(), {...metadata, installation_id: `dev_${'b'.repeat(32)}`})).status).toBe(404);
    const badId = await post(new FakeD1(), metadata, token, {}, 'invalid');
    expect(badId.status).toBe(400);
    expect(await badId.json()).toEqual({error: {code: 'invalid_activation_id'}});
    expect((await post(new FakeD1(), {...metadata, oversized: 'x'.repeat(5000)})).status).toBe(400);
  });

  it('disables production and never signs or returns an envelope', async () => {
    expect((await post(new FakeD1(), metadata, token, {BETA_ENVIRONMENT: 'production'})).status).toBe(403);
    const response = await post();
    expect(Object.keys(await response.json()).sort()).toEqual(['result', 'schema_version']);
  });
});
