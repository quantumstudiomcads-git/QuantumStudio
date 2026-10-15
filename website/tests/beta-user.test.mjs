import {describe, expect, it} from 'vitest';
import {onRequestPost as submitApplication} from '../functions/api/beta/applications.js';
import {onRequestGet as getMyApplication} from '../functions/api/beta/me.js';
import {AUTH_SESSION_COOKIE, sha256Hex} from '../functions/_lib/auth.js';

const baseEnv = Object.freeze({
  BETA_ENVIRONMENT: 'local',
  BETA_ALLOWED_ORIGIN: 'http://localhost:8788',
  BETA_PRIVACY_VERSION: 'draft-0.1',
  BETA_TERMS_VERSION: 'draft-0.1',
  BETA_IDENTITY_PEPPER: 'synthetic-user-test-pepper',
  BETA_TURNSTILE_TEST_MODE: 'true',
});

const applicationPayload = () => ({
  fullName: 'Ada Example',
  email: 'ada@example.test',
  institution: 'Example Institute',
  country: 'Exampleland',
  researchArea: 'Electronic structure',
  operatingSystem: 'Linux',
  academicRole: '',
  evaluationDescription: '',
  privacyAccepted: true,
  termsAccepted: true,
  communicationsAccepted: false,
  turnstileToken: 'test-pass',
});

class FakeD1 {
  constructor({applications = []} = {}) {
    this.applications = applications;
    this.sessions = new Map();
    this.applicationQueries = [];
    this.batches = [];
  }

  prepare(sql) {
    const statement = {
      sql,
      values: [],
      bind: (...values) => {
        statement.values = values;
        return statement;
      },
      first: async () => {
        if (sql.includes('FROM sessions WHERE session_id = ?')) {
          return this.sessions.get(statement.values[0]) ?? null;
        }
        if (sql.includes('FROM beta_applications WHERE user_id = ?')) {
          const [userId] = statement.values;
          this.applicationQueries.push(userId);
          return this.applications.find((application) => application.user_id === userId) ?? null;
        }
        throw new Error(`Unexpected query: ${sql}`);
      },
      run: async () => ({success: true}),
    };
    return statement;
  }

  async batch(statements) {
    this.batches.push(statements);
    const insert = statements[0];
    const userId = insert.values.at(-1);
    if (this.applications.some((application) => application.user_id === userId)) {
      throw new Error('UNIQUE constraint failed: beta_applications.user_id');
    }
    const applicationId = insert.values[0];
    const timestamp = insert.values.at(-2);
    this.applications.push({
      application_id: applicationId,
      user_id: userId,
      status: 'APPLIED',
      submitted_at: timestamp,
      updated_at: timestamp,
      full_name: 'operator-only name',
      review_note: 'operator-only note',
      licence_id: 'operator-only licence',
    });
    return [];
  }
}

async function authenticatedRequest(db, userId, path, options = {}) {
  const sessionId = `session-${userId}`;
  const rawToken = `token-${userId}`;
  db.sessions.set(sessionId, {
    session_id: sessionId,
    user_id: userId,
    token_hash: await sha256Hex(rawToken),
    expires_at: new Date(Date.now() + 60_000).toISOString(),
    revoked_at: null,
  });
  const headers = new Headers(options.headers);
  headers.set('Cookie', `${AUTH_SESSION_COOKIE}=${encodeURIComponent(`${sessionId}.${rawToken}`)}`);
  const request = new Request(`http://localhost:8788${path}`, {...options, headers});
  return request;
}

describe('current-user beta application API', () => {
  it('returns a clean no-application state to an authenticated user', async () => {
    const db = new FakeD1();
    const request = await authenticatedRequest(db, 'user-a', '/api/beta/me');
    const response = await getMyApplication({request, env: {...baseEnv, BETA_DB: db}});
    expect(response.status).toBe(200);
    expect(response.headers.get('cache-control')).toBe('no-store');
    expect(await response.json()).toEqual({application: null});
    expect(db.applicationQueries).toEqual(['user-a']);
  });

  it('requires authentication for status lookup and application submission', async () => {
    const db = new FakeD1();
    const getResponse = await getMyApplication({
      request: new Request('http://localhost:8788/api/beta/me'),
      env: {...baseEnv, BETA_DB: db},
    });
    expect(getResponse.status).toBe(401);

    const postResponse = await submitApplication({
      request: new Request('http://localhost:8788/api/beta/applications', {
        method: 'POST',
        headers: {Origin: baseEnv.BETA_ALLOWED_ORIGIN, 'Content-Type': 'application/json'},
        body: JSON.stringify(applicationPayload()),
      }),
      env: {...baseEnv, BETA_DB: db},
    });
    expect(postResponse.status).toBe(401);
    expect(db.batches).toHaveLength(0);
  });

  it('stores the authenticated user ID when that user submits', async () => {
    const db = new FakeD1();
    const request = await authenticatedRequest(db, 'user-a', '/api/beta/applications', {
      method: 'POST',
      headers: {Origin: baseEnv.BETA_ALLOWED_ORIGIN, 'Content-Type': 'application/json'},
      body: JSON.stringify(applicationPayload()),
    });
    const response = await submitApplication({request, env: {...baseEnv, BETA_DB: db}});
    const payload = await response.json();
    expect(response.status).toBe(202);
    expect(payload.accepted).toBe(true);
    expect(db.applications[0].user_id).toBe('user-a');
    expect(db.batches[0][0].sql).toContain('user_id');
  });

  it('prevents a second current application for the same authenticated user', async () => {
    const db = new FakeD1({applications: [{
      application_id: 'app-existing',
      user_id: 'user-a',
      status: 'APPLIED',
      submitted_at: '2026-10-15T00:00:00.000Z',
      updated_at: '2026-10-15T00:00:00.000Z',
    }]});
    const request = await authenticatedRequest(db, 'user-a', '/api/beta/applications', {
      method: 'POST',
      headers: {Origin: baseEnv.BETA_ALLOWED_ORIGIN, 'Content-Type': 'application/json'},
      body: JSON.stringify(applicationPayload()),
    });
    const response = await submitApplication({request, env: {...baseEnv, BETA_DB: db}});
    expect(response.status).toBe(409);
    expect(await response.json()).toMatchObject({error: {code: 'application_exists'}});
    expect(db.batches).toHaveLength(0);
  });

  it('returns only the authenticated user application and safe fields', async () => {
    const db = new FakeD1({applications: [
      {
        application_id: 'application-user-a',
        user_id: 'user-a',
        status: 'UNDER_REVIEW',
        submitted_at: '2026-10-14T12:00:00.000Z',
        updated_at: '2026-10-15T12:00:00.000Z',
        full_name: 'private name',
        review_note: 'private operator note',
        licence_id: 'private licence',
      },
      {
        application_id: 'legacy-unlinked-application',
        user_id: null,
        email: 'user-b@example.test',
        status: 'APPROVED',
        submitted_at: '2026-10-13T12:00:00.000Z',
        updated_at: '2026-10-14T12:00:00.000Z',
      },
    ]});
    const userBRequest = await authenticatedRequest(db, 'user-b', '/api/beta/me');
    const userBResponse = await getMyApplication({request: userBRequest, env: {...baseEnv, BETA_DB: db}});
    expect(await userBResponse.json()).toEqual({application: null});

    const userARequest = await authenticatedRequest(db, 'user-a', '/api/beta/me');
    const userAResponse = await getMyApplication({request: userARequest, env: {...baseEnv, BETA_DB: db}});
    expect(await userAResponse.json()).toEqual({
      application: {
        application_id: 'application-user-a',
        status: 'UNDER_REVIEW',
        submitted_at: '2026-10-14T12:00:00.000Z',
        updated_at: '2026-10-15T12:00:00.000Z',
      },
    });
    expect(db.applicationQueries).toEqual(['user-b', 'user-a']);
  });
});
