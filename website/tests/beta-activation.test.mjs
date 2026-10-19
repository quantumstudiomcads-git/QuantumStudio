import {describe, expect, it} from 'vitest';
import {onRequestGet, onRequestPost} from '../functions/api/beta/activation.js';
import {onRequestGet as getOperatorActivations} from '../functions/api/operator/activations.js';
import {AUTH_SESSION_COOKIE, sha256Hex} from '../functions/_lib/auth.js';

const baseEnv = Object.freeze({
  BETA_ENVIRONMENT: 'local',
  BETA_ALLOWED_ORIGIN: 'http://localhost:8788',
  BETA_PRIVACY_VERSION: 'draft-0.1',
  BETA_TERMS_VERSION: 'draft-0.1',
  BETA_IDENTITY_PEPPER: 'synthetic-activation-test-pepper',
});

const requestPayload = (installationId = `dev_${'a'.repeat(32)}`) => ({
  installation_id: installationId,
  platform: 'linux',
  architecture: 'x86_64',
  app_version: '0.1.0',
});

const makeApplication = (userId = 'user-a', status = 'APPROVED') => ({
  application_id: '12345678-1234-4123-8123-123456789abc',
  user_id: userId,
  status,
  licence_expires_at: '2099-01-01T00:00:00.000Z',
});

class FakeD1 {
  constructor({applications = [], activations = []} = {}) {
    this.applications = applications;
    this.activations = activations;
    this.sessions = new Map();
    this.insertRuns = 0;
    this.operatorQueries = 0;
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
          return this.applications.find((row) => row.user_id === statement.values[0]) ?? null;
        }
        if (sql.includes('FROM beta_activations') && sql.includes('installation_id = ?')) {
          const [userId, installationId] = statement.values;
          return this.activations.find(
            (row) => row.user_id === userId && row.installation_id === installationId,
          ) ?? null;
        }
        throw new Error(`Unexpected first query: ${sql}`);
      },
      all: async () => {
        if (sql.includes('FROM beta_activations') && sql.includes('WHERE user_id = ?')) {
          const [userId] = statement.values;
          return {
            results: this.activations
              .filter((row) => row.user_id === userId)
              .sort((left, right) => left.created_at.localeCompare(right.created_at)
                || left.activation_request_id.localeCompare(right.activation_request_id)),
          };
        }
        if (sql.includes('FROM beta_activations') && sql.includes('ORDER BY created_at ASC')) {
          this.operatorQueries += 1;
          return {
            results: [...this.activations]
              .sort((left, right) => left.created_at.localeCompare(right.created_at)
                || left.activation_request_id.localeCompare(right.activation_request_id)),
          };
        }
        throw new Error(`Unexpected all query: ${sql}`);
      },
      run: async () => {
        if (sql.includes('UPDATE sessions SET last_seen_at')) {
          return {success: true};
        }
        if (!sql.includes('INSERT INTO beta_activations')) {
          throw new Error(`Unexpected run query: ${sql}`);
        }
        this.insertRuns += 1;
        const values = statement.values;
        expect(values).toHaveLength(19);
        const activationId = values[0];
        const installationId = values[1];
        const platform = values[2];
        const architecture = values[3];
        const appVersion = values[4];
        const maxDevices = values[15];
        const createdAt = values[11];
        const updatedAt = values[12];
        const authorizedAt = values[16];
        const digest = values[17];
        const userId = values[18];
        const app = this.applications.find((row) => row.user_id === userId);
        const now = values[5];
        const eligible = app?.status === 'APPROVED'
          || (app?.status === 'LICENSE_ISSUED' && app.licence_expires_at > now);
        const existing = this.activations.find(
          (row) => row.user_id === userId && row.installation_id === installationId,
        );
        const activeCount = this.activations.filter(
          (row) => row.user_id === userId
            && row.status === 'AUTHORIZED'
            && row.installation_id !== installationId,
        ).length;
        const status = eligible && activeCount < maxDevices ? 'AUTHORIZED' : 'FLAGGED';
        const flagReason = eligible
          ? activeCount >= maxDevices ? 'DEVICE_LIMIT' : null
          : 'APPLICATION_NOT_ELIGIBLE';
        if (existing) {
          if (existing.device_public_key_hash && digest && existing.device_public_key_hash !== digest) return {success: true};
          existing.device_public_key_hash ??= digest;
          if (existing.status !== 'REVOKED') {
            Object.assign(existing, {
              platform,
              architecture,
              app_version: appVersion,
              status,
              flag_reason: flagReason,
              updated_at: updatedAt,
              authorized_at: status === 'AUTHORIZED'
                ? existing.authorized_at ?? authorizedAt
                : null,
            });
          } else {
            existing.flag_reason = 'INSTALLATION_REVOKED';
            existing.updated_at = updatedAt;
          }
          return {success: true};
        }
        this.activations.push({
          activation_request_id: activationId,
          user_id: userId,
          application_id: app.application_id,
          installation_id: installationId,
          device_public_key_hash: digest,
          platform,
          architecture,
          app_version: appVersion,
          status,
          flag_reason: flagReason,
          created_at: createdAt,
          updated_at: updatedAt,
          authorized_at: status === 'AUTHORIZED' ? authorizedAt : null,
          revoked_at: null,
        });
        return {success: true};
      },
    };
    return statement;
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
  return new Request(`http://localhost:8788${path}`, {...options, headers});
}

async function register(db, userId, payload) {
  const request = await authenticatedRequest(db, userId, '/api/beta/activation', {
    method: 'POST',
    headers: {
      Origin: baseEnv.BETA_ALLOWED_ORIGIN,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });
  return onRequestPost({request, env: {...baseEnv, BETA_DB: db}});
}

describe('authenticated beta activation API', () => {
  it('rejects unauthenticated users and does not write', async () => {
    const db = new FakeD1({applications: [makeApplication()]});
    const getResponse = await onRequestGet({
      request: new Request('http://localhost:8788/api/beta/activation'),
      env: {...baseEnv, BETA_DB: db},
    });
    const response = await onRequestPost({
      request: new Request('http://localhost:8788/api/beta/activation', {
        method: 'POST',
        headers: {Origin: baseEnv.BETA_ALLOWED_ORIGIN, 'Content-Type': 'application/json'},
        body: JSON.stringify(requestPayload()),
      }),
      env: {...baseEnv, BETA_DB: db},
    });
    expect(getResponse.status).toBe(401);
    expect(response.status).toBe(401);
    expect(db.insertRuns).toBe(0);
  });

  it('requires a linked approved application and automatically authorizes a valid installation', async () => {
    const db = new FakeD1({applications: [makeApplication()]});
    const response = await register(db, 'user-a', requestPayload());
    expect(response.status).toBe(200);
    expect((await response.json()).activation.status).toBe('AUTHORIZED');
    expect(db.activations).toHaveLength(1);
    expect(db.activations[0].user_id).toBe('user-a');
  });

  it('returns a controlled denial when the signed-in user has no linked application', async () => {
    const db = new FakeD1();
    const response = await register(db, 'user-a', requestPayload());
    expect(response.status).toBe(403);
    expect(await response.json()).toMatchObject({
      error: {code: 'application_required'},
    });
    expect(db.insertRuns).toBe(0);
  });

  it('flags an installation when the application is not eligible', async () => {
    const db = new FakeD1({applications: [makeApplication('user-a', 'UNDER_REVIEW')]});
    const response = await register(db, 'user-a', requestPayload());
    expect(response.status).toBe(200);
    expect((await response.json()).activation.status).toBe('FLAGGED');
    expect(db.activations[0].flag_reason).toBe('APPLICATION_NOT_ELIGIBLE');
  });

  it('keeps repeated registration idempotent and preserves revoked installations', async () => {
    const db = new FakeD1({applications: [makeApplication()]});
    const first = await register(db, 'user-a', requestPayload());
    const firstPayload = await first.json();
    await register(db, 'user-a', requestPayload());
    expect(db.activations).toHaveLength(1);
    expect(db.activations[0].activation_request_id).toBe(firstPayload.activation.activation_request_id);

    db.activations[0].status = 'REVOKED';
    await register(db, 'user-a', requestPayload());
    expect(db.activations).toHaveLength(1);
    expect(db.activations[0].status).toBe('REVOKED');
    expect(db.activations[0].flag_reason).toBe('INSTALLATION_REVOKED');
  });

  it('flags only installations exceeding the configured active-device limit', async () => {
    const db = new FakeD1({applications: [makeApplication()]});
    const maxDevices = 2;
    const first = await register(db, 'user-a', requestPayload(`dev_${'1'.repeat(32)}`));
    const second = await register(db, 'user-a', requestPayload(`dev_${'2'.repeat(32)}`));
    const third = await register(db, 'user-a', requestPayload(`dev_${'3'.repeat(32)}`));
    expect((await first.json()).activation.status).toBe('AUTHORIZED');
    expect((await second.json()).activation.status).toBe('AUTHORIZED');
    expect((await third.json()).activation.status).toBe('FLAGGED');
    expect(db.activations.filter((row) => row.status === 'AUTHORIZED')).toHaveLength(maxDevices);
  });

  it('fails closed for an invalid configured device limit', async () => {
    const db = new FakeD1({applications: [makeApplication()]});
    const request = await authenticatedRequest(db, 'user-a', '/api/beta/activation', {
      method: 'POST',
      headers: {
        Origin: baseEnv.BETA_ALLOWED_ORIGIN,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(requestPayload()),
    });
    const response = await onRequestPost({
      request,
      env: {...baseEnv, BETA_DB: db, BETA_MAX_ACTIVE_DEVICES: '0'},
    });
    expect(response.status).toBe(503);
    expect(db.insertRuns).toBe(0);
  });

  it('records the existing desktop full public hash, permits legacy requests, and prevents rebinding', async () => {
    const db = new FakeD1({applications: [makeApplication()]});
    expect((await register(db, 'user-a', requestPayload())).status).toBe(200);
    const digest = 'a'.repeat(64);
    expect((await register(db, 'user-a', {...requestPayload(), device_public_key_hash: digest})).status).toBe(200);
    expect(db.activations[0].device_public_key_hash).toBe(digest);
    expect((await register(db, 'user-a', {...requestPayload(), device_public_key_hash: 'b'.repeat(64)})).status).toBe(400);
    expect((await register(db, 'user-a', {...requestPayload(), device_public_key_hash: 'a'.repeat(32) + 'b'.repeat(32)})).status).toBe(409);
    expect(db.activations[0].device_public_key_hash).toBe(digest);
  });

  it('rejects unsupported activation facts and unknown client authority fields', async () => {
    const db = new FakeD1({applications: [makeApplication()]});
    expect((await register(db, 'user-a', {...requestPayload(), user_id: 'user-b'})).status).toBe(400);
    expect((await register(db, 'user-a', {...requestPayload(), installation_id: 'not-a-device'})).status).toBe(400);
    expect(db.insertRuns).toBe(0);
  });

  it('rejects an oversized or malformed request body before writing', async () => {
    const db = new FakeD1({applications: [makeApplication()]});
    const oversized = await authenticatedRequest(db, 'user-a', '/api/beta/activation', {
      method: 'POST',
      headers: {
        Origin: baseEnv.BETA_ALLOWED_ORIGIN,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(requestPayload()) + ' '.repeat(5000),
    });
    expect((await onRequestPost({request: oversized, env: {...baseEnv, BETA_DB: db}})).status).toBe(413);

    const malformed = await authenticatedRequest(db, 'user-a', '/api/beta/activation', {
      method: 'POST',
      headers: {
        Origin: baseEnv.BETA_ALLOWED_ORIGIN,
        'Content-Type': 'application/json',
      },
      body: '{invalid',
    });
    expect((await onRequestPost({request: malformed, env: {...baseEnv, BETA_DB: db}})).status).toBe(400);
    expect(db.insertRuns).toBe(0);
  });

  it('returns only the signed-in user activations and safe fields', async () => {
    const db = new FakeD1({
      applications: [makeApplication('user-a'), makeApplication('user-b')],
      activations: [
        {
          activation_request_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
          user_id: 'user-a',
          application_id: '12345678-1234-4123-8123-123456789abc',
          installation_id: `dev_${'a'.repeat(32)}`,
          platform: 'linux',
          architecture: 'x86_64',
          app_version: '0.1.0',
          status: 'AUTHORIZED',
          flag_reason: null,
          created_at: '2026-10-01T00:00:00.000Z',
          updated_at: '2026-10-01T00:00:00.000Z',
          authorized_at: '2026-10-01T00:00:00.000Z',
          revoked_at: null,
        },
        {
          activation_request_id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
          user_id: 'user-b',
          application_id: '12345678-1234-4123-8123-123456789abc',
          installation_id: `dev_${'b'.repeat(32)}`,
          platform: 'windows',
          architecture: 'x86_64',
          app_version: '0.1.0',
          status: 'FLAGGED',
          flag_reason: 'DEVICE_LIMIT',
          created_at: '2026-10-02T00:00:00.000Z',
          updated_at: '2026-10-02T00:00:00.000Z',
          authorized_at: null,
          revoked_at: null,
        },
      ],
    });
    const request = await authenticatedRequest(db, 'user-a', '/api/beta/activation');
    const response = await onRequestGet({request, env: {...baseEnv, BETA_DB: db}});
    expect(response.status).toBe(200);
    const payload = await response.json();
    expect(payload.activations).toHaveLength(1);
    expect(payload.activations[0]).not.toHaveProperty('user_id');
    expect(payload.activations[0]).not.toHaveProperty('application_id');
    expect(payload.activations[0]).not.toHaveProperty('flag_reason');
    expect(response.headers.get('cache-control')).toBe('no-store');
  });
});

describe('read-only operator beta activation export', () => {
  const token = 'synthetic-read-only-token';
  const applicationId = '12345678-1234-4123-8123-123456789abc';
  const activation = (activationId, createdAt, userId) => ({
    activation_request_id: activationId,
    user_id: userId,
    application_id: applicationId,
    installation_id: `dev_${activationId.slice(0, 32).replaceAll('-', 'a')}`,
    platform: 'linux',
    architecture: 'x86_64',
    app_version: '0.1.0',
    status: 'AUTHORIZED',
    flag_reason: null,
    created_at: createdAt,
    updated_at: createdAt,
    authorized_at: createdAt,
    revoked_at: null,
    email: 'must-not-be-exported@example.test',
  });

  it('requires the existing read-only bearer token and emits a bounded safe schema', async () => {
    const db = new FakeD1({activations: [
      activation('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', '2026-10-02T00:00:00.000Z', 'user-b'),
      activation('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', '2026-10-01T00:00:00.000Z', 'user-a'),
    ]});
    const unauthorized = await getOperatorActivations({
      request: new Request('http://localhost:8788/api/operator/activations'),
      env: {...baseEnv, BETA_DB: db, OPERATOR_SYNC_TOKEN: token},
    });
    expect(unauthorized.status).toBe(401);
    const response = await getOperatorActivations({
      request: new Request('http://localhost:8788/api/operator/activations', {
        headers: {Authorization: `Bearer ${token}`},
      }),
      env: {...baseEnv, BETA_DB: db, OPERATOR_SYNC_TOKEN: token},
    });
    expect(response.status).toBe(200);
    expect(response.headers.get('cache-control')).toBe('no-store');
    const payload = await response.json();
    expect(payload.schema_version).toBe(1);
    expect(payload.activations.map((row) => row.activation_request_id)).toEqual([
      'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
      'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
    ]);
    expect(payload.activations[0]).not.toHaveProperty('user_id');
    expect(payload.activations[0]).not.toHaveProperty('email');
  });

  it('rejects production HTTP and introduces no write handler', async () => {
    const response = await getOperatorActivations({
      request: new Request('http://website.example/api/operator/activations', {
        headers: {Authorization: `Bearer ${token}`},
      }),
      env: {...baseEnv, BETA_ENVIRONMENT: 'production', BETA_DB: new FakeD1(), OPERATOR_SYNC_TOKEN: token},
    });
    expect(response.status).toBe(403);
  });
});
