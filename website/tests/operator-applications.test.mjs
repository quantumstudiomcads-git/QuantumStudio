import {describe, expect, it} from 'vitest';
import {onRequestGet} from '../functions/api/operator/applications.js';

const token = 'local-test-operator-token';
const expectedFields = [
  'application_id', 'full_name', 'email', 'institution', 'country', 'academic_role',
  'research_area', 'intended_evaluation', 'operating_system', 'privacy_consent',
  'privacy_version', 'terms_consent', 'terms_version', 'communications_consent',
  'status', 'submitted_at', 'updated_at', 'reviewed_at', 'review_note', 'licence_id',
  'licence_issued_at', 'licence_expires_at', 'revoked_at',
];
const rows = [
  {
    application_id: '22222222-2222-4222-8222-222222222222',
    full_name: 'Bea Example',
    email: 'bea@example.test',
    institution: 'Example Institute',
    country: 'Exampleland',
    academic_role: 'Researcher',
    research_area: 'Materials',
    intended_evaluation: 'Local evaluation',
    operating_system: 'Windows',
    privacy_consent: 1,
    privacy_version: 'draft-0.1',
    terms_consent: 1,
    terms_version: 'draft-0.1',
    communications_consent: 0,
    status: 'APPLIED',
    submitted_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    reviewed_at: null,
    review_note: null,
    licence_id: null,
    licence_issued_at: null,
    licence_expires_at: null,
    revoked_at: null,
    normalized_email: 'normalized-email-secret',
    email_lookup_hash: 'internal-hash-secret',
    session_id: 'website-session-secret',
    auth_challenge: 'website-challenge-secret',
    google_subject: 'google-identity-secret',
    internal_secret: 'website-secret',
  },
  {
    application_id: '11111111-1111-4111-8111-111111111111',
    full_name: 'Ada Example',
    email: 'ada@example.test',
    institution: 'Example Institute',
    country: 'Exampleland',
    academic_role: 'Researcher',
    research_area: 'Electronic structure',
    intended_evaluation: 'Local evaluation',
    operating_system: 'Windows',
    privacy_consent: 1,
    privacy_version: 'draft-0.1',
    terms_consent: 1,
    terms_version: 'draft-0.1',
    communications_consent: 0,
    status: 'APPLIED',
    submitted_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    reviewed_at: null,
    review_note: null,
    licence_id: null,
    licence_issued_at: null,
    licence_expires_at: null,
    revoked_at: null,
    normalized_email: 'normalized-email-secret',
    email_lookup_hash: 'internal-hash-secret',
    session_id: 'website-session-secret',
    auth_challenge: 'website-challenge-secret',
    google_subject: 'google-identity-secret',
    internal_secret: 'website-secret',
  },
];

function makeEnv(applicationRows = rows) {
  const queries = [];
  const env = {
    BETA_ENVIRONMENT: 'local',
    OPERATOR_SYNC_TOKEN: token,
    BETA_DB: {
      prepare(sql) {
        return {
          bind(...values) {
            return {
              async all() {
                queries.push({sql, values});
                const filtered = values.length
                  ? applicationRows.filter((row) => row.status === values[0])
                  : applicationRows;
                return {results: [...filtered].sort((left, right) =>
                  left.submitted_at.localeCompare(right.submitted_at)
                  || left.application_id.localeCompare(right.application_id))};
              },
            };
          },
        };
      },
    },
  };
  return {env, queries};
}

function getRequest({authorization, status} = {}) {
  const url = new URL('http://localhost:8788/api/operator/applications');
  if (status !== undefined) url.searchParams.set('status', status);
  const headers = authorization === undefined ? {} : {Authorization: authorization};
  return new Request(url, {headers});
}

describe('operator beta applications export', () => {
  it('rejects a missing Authorization header', async () => {
    const {env} = makeEnv();
    const response = await onRequestGet({request: getRequest(), env});
    expect(response.status).toBe(401);
    expect(response.headers.get('cache-control')).toBe('no-store');
  });

  it('rejects malformed Authorization headers', async () => {
    const {env} = makeEnv();
    for (const authorization of ['Token wrong', 'Bearer', 'Bearer one two']) {
      const response = await onRequestGet({request: getRequest({authorization}), env});
      expect(response.status).toBe(401);
    }
  });

  it('rejects an incorrect bearer token', async () => {
    const {env} = makeEnv();
    const response = await onRequestGet({
      request: getRequest({authorization: 'Bearer incorrect-local-test-token'}),
      env,
    });
    expect(response.status).toBe(403);
    expect(response.headers.get('cache-control')).toBe('no-store');
  });

  it('returns the version 1 importer envelope with exactly its supported fields', async () => {
    const {env} = makeEnv();
    const response = await onRequestGet({
      request: getRequest({authorization: `Bearer ${token}`}),
      env,
    });
    expect(response.status).toBe(200);
    expect(response.headers.get('cache-control')).toBe('no-store');
    const body = await response.json();
    expect(body.schema_version).toBe(1);
    expect(body.applications).toHaveLength(2);
    expect(Object.keys(body.applications[0]).sort()).toEqual([...expectedFields].sort());
    expect(body.applications[0]).toMatchObject({
      application_id: '11111111-1111-4111-8111-111111111111',
      full_name: 'Ada Example',
      email: 'ada@example.test',
      status: 'APPLIED',
    });
  });

  it('normalizes only schema-optional nullable fields for the strict importer', async () => {
    const realisticOptionalFields = {
      ...rows[0],
      academic_role: null,
      intended_evaluation: null,
    };
    const {env} = makeEnv([realisticOptionalFields]);
    const response = await onRequestGet({
      request: getRequest({authorization: `Bearer ${token}`}),
      env,
    });
    expect(response.status).toBe(200);
    const body = await response.json();
    expect(body.schema_version).toBe(1);
    expect(body.applications[0].academic_role).toBe('');
    expect(body.applications[0].intended_evaluation).toBe('');

    const requiredFieldNull = {
      ...realisticOptionalFields,
      full_name: null,
    };
    const {env: requiredFieldEnv} = makeEnv([requiredFieldNull]);
    const requiredResponse = await onRequestGet({
      request: getRequest({authorization: `Bearer ${token}`}),
      env: requiredFieldEnv,
    });
    const requiredBody = await requiredResponse.json();
    expect(requiredResponse.status).toBe(200);
    expect(requiredBody.applications[0].full_name).toBeNull();
  });

  it('does not expose website-only auth, identity, hash, or secret fields', async () => {
    const {env} = makeEnv();
    const response = await onRequestGet({
      request: getRequest({authorization: `Bearer ${token}`}),
      env,
    });
    const body = await response.text();
    for (const secret of [
      'normalized-email-secret',
      'internal-hash-secret',
      'website-session-secret',
      'website-challenge-secret',
      'google-identity-secret',
      'website-secret',
      'session_id',
      'auth_challenge',
      'google_subject',
      'internal_secret',
    ]) {
      expect(body).not.toContain(secret);
    }
  });

  it('uses stable submitted-time and application-id ordering', async () => {
    const {env, queries} = makeEnv();
    const response = await onRequestGet({
      request: getRequest({authorization: `Bearer ${token}`}),
      env,
    });
    const body = await response.json();
    expect(body.applications.map((row) => row.application_id)).toEqual([
      '11111111-1111-4111-8111-111111111111',
      '22222222-2222-4222-8222-222222222222',
    ]);
    expect(queries[0].sql).toContain('ORDER BY submitted_at ASC, application_id ASC');
  });

  it('bounds the export by application count and serialized bytes', async () => {
    const tooManyRows = Array.from({length: 1001}, () => rows[0]);
    const {env: countLimitedEnv} = makeEnv(tooManyRows);
    const countLimited = await onRequestGet({
      request: getRequest({authorization: `Bearer ${token}`}),
      env: countLimitedEnv,
    });
    expect(countLimited.status).toBe(413);
    expect(countLimited.headers.get('cache-control')).toBe('no-store');

    const largeRow = {...rows[0], intended_evaluation: 'x'.repeat(2 * 1024 * 1024)};
    const {env: byteLimitedEnv} = makeEnv([largeRow]);
    const byteLimited = await onRequestGet({
      request: getRequest({authorization: `Bearer ${token}`}),
      env: byteLimitedEnv,
    });
    expect(byteLimited.status).toBe(413);
  });

  it('rejects invalid and empty status filters', async () => {
    const {env} = makeEnv();
    for (const status of ['NOT_A_STATUS', '']) {
      const response = await onRequestGet({
        request: getRequest({authorization: `Bearer ${token}`, status}),
        env,
      });
      expect(response.status).toBe(400);
    }
  });
});
