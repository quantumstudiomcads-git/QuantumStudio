import {describe, expect, it} from 'vitest';
import {onRequestGet, onRequestPost} from '../functions/api/operator/applications/[applicationId]/status.js';

const applicationId = '11111111-1111-4111-8111-111111111111';
const statusToken = 'local-status-write-token';
const readToken = 'local-read-only-token';
const auth = (token = statusToken) => `Bearer ${token}`;

function makeEnv(initialStatus = 'APPLIED', {beforeBatch} = {}) {
  const state = {status: initialStatus};
  const auditEvents = [];
  const database = {
    prepare(sql) {
      return {
        sql,
        values: [],
        bind(...values) {
          this.values = values;
          return this;
        },
        async first() {
          if (this.sql.startsWith('SELECT status')) {
            return state.status === null ? null : {status: state.status};
          }
          throw new Error('Unexpected query');
        },
      };
    },
    async batch(statements) {
      beforeBatch?.(state);
      const update = statements[0];
      const [newStatus, timestamp, reviewed, reviewedAt, id, expectedStatus] = update.values;
      if (id !== applicationId || state.status !== expectedStatus) {
        return [{meta: {changes: 0}}, {meta: {changes: 0}}];
      }
      const oldStatus = state.status;
      state.status = newStatus;
      state.updatedAt = timestamp;
      if (reviewed) state.reviewedAt = reviewedAt;
      const audit = statements[1];
      const [eventId, auditApplicationId, eventTimestamp, auditOld, auditNew, metadata] = audit.values;
      auditEvents.push({
        event_id: eventId,
        application_id: auditApplicationId,
        event_type: 'OPERATOR_STATUS_SYNC',
        event_timestamp: eventTimestamp,
        actor_reference: 'operator-status-sync',
        old_status: auditOld,
        new_status: auditNew,
        metadata_json: metadata,
      });
      expect(auditOld).toBe(oldStatus);
      return [{meta: {changes: 1}}, {meta: {changes: 1}}];
    },
  };
  return {
    state,
    auditEvents,
    env: {
      BETA_ENVIRONMENT: 'local',
      OPERATOR_SYNC_TOKEN: readToken,
      OPERATOR_STATUS_SYNC_TOKEN: statusToken,
      BETA_DB: database,
    },
  };
}

function post(env, {id = applicationId, authorization, body} = {}) {
  const headers = {'Content-Type': 'application/json'};
  if (authorization !== undefined) headers.Authorization = authorization;
  return onRequestPost({
    request: new Request(`http://localhost:8788/api/operator/applications/${id}/status`, {
      method: 'POST',
      headers,
      body: body === undefined ? JSON.stringify({schema_version: 1, status: 'UNDER_REVIEW'}) : body,
    }),
    env,
    params: {applicationId: id},
  });
}

describe('operator application status mirror endpoint', () => {
  it('rejects missing and malformed Authorization headers', async () => {
    const {env} = makeEnv();
    expect((await post(env)).status).toBe(401);
    for (const value of ['Token invalid', 'Bearer', 'Bearer two tokens']) {
      expect((await post(env, {authorization: value})).status).toBe(401);
    }
  });

  it('requires the distinct status-write token', async () => {
    const {env} = makeEnv();
    expect((await post(env, {authorization: auth(readToken)})).status).toBe(403);
    expect((await post(env, {authorization: auth('wrong-write-token')})).status).toBe(403);
  });

  it('accepts the configured status token and returns no-store minimal data', async () => {
    const {env, state, auditEvents} = makeEnv();
    const response = await post(env, {authorization: auth()});
    const payload = await response.json();
    expect(response.status).toBe(200);
    expect(response.headers.get('cache-control')).toBe('no-store');
    expect(payload).toEqual({
      schema_version: 1,
      application_id: applicationId,
      status: 'UNDER_REVIEW',
      result: 'updated',
    });
    expect(Object.keys(payload).sort()).toEqual([
      'application_id', 'result', 'schema_version', 'status',
    ]);
    expect(state.status).toBe('UNDER_REVIEW');
    expect(state.reviewedAt).toBeTruthy();
    expect(auditEvents).toHaveLength(1);
  });

  it('rejects malformed identifiers, unknown applications, malformed JSON, and wrong schemas', async () => {
    const {env} = makeEnv();
    expect((await post(env, {id: 'not-a-uuid', authorization: auth()})).status).toBe(400);

    const missing = makeEnv();
    missing.state.status = null;
    expect((await post(missing.env, {authorization: auth()})).status).toBe(404);

    expect((await post(env, {authorization: auth(), body: '{'})).status).toBe(400);
    expect((await post(env, {
      authorization: auth(),
      body: JSON.stringify({schema_version: 2, status: 'UNDER_REVIEW'}),
    })).status).toBe(400);
    expect((await post(env, {
      authorization: auth(),
      body: JSON.stringify({schema_version: 1, status: 'APPROVED', review_note: 'extra'}),
    })).status).toBe(400);
  });

  it('rejects unsupported and non-review statuses', async () => {
    const {env} = makeEnv();
    for (const status of ['OTHER', 'LICENSE_ISSUED', null]) {
      const response = await post(env, {
        authorization: auth(),
        body: JSON.stringify({schema_version: 1, status}),
      });
      expect(response.status).toBe(400);
    }
  });

  it.each([
    ['APPLIED', 'UNDER_REVIEW'],
    ['UNDER_REVIEW', 'APPROVED'],
    ['UNDER_REVIEW', 'REJECTED'],
  ])('allows the operator transition %s -> %s', async (from, to) => {
    const {env, state, auditEvents} = makeEnv(from);
    const response = await post(env, {
      authorization: auth(),
      body: JSON.stringify({schema_version: 1, status: to}),
    });
    expect(response.status).toBe(200);
    expect((await response.json()).result).toBe('updated');
    expect(state.status).toBe(to);
    expect(auditEvents).toHaveLength(1);
    expect(auditEvents[0].old_status).toBe(from);
    expect(auditEvents[0].new_status).toBe(to);
  });

  it('rejects skipped, backward, and terminal transitions', async () => {
    for (const [from, to] of [
      ['APPLIED', 'APPROVED'],
      ['UNDER_REVIEW', 'APPLIED'],
      ['REJECTED', 'UNDER_REVIEW'],
      ['APPROVED', 'REJECTED'],
    ]) {
      const {env, state, auditEvents} = makeEnv(from);
      const response = await post(env, {
        authorization: auth(),
        body: JSON.stringify({schema_version: 1, status: to}),
      });
      expect(response.status).toBe(409);
      expect(state.status).toBe(from);
      expect(auditEvents).toHaveLength(0);
    }
  });

  it('treats a retry as already current without duplicating the audit transition', async () => {
    const {env, auditEvents} = makeEnv();
    const body = JSON.stringify({schema_version: 1, status: 'UNDER_REVIEW'});
    expect((await post(env, {authorization: auth(), body})).status).toBe(200);
    const retry = await post(env, {authorization: auth(), body});
    expect(retry.status).toBe(200);
    expect((await retry.json()).result).toBe('already_current');
    expect(auditEvents).toHaveLength(1);
  });

  it('returns conflict and does not overwrite an unexpected concurrent state', async () => {
    const {env, state, auditEvents} = makeEnv('APPLIED', {
      beforeBatch(current) {
        current.status = 'REJECTED';
      },
    });
    const response = await post(env, {authorization: auth()});
    expect(response.status).toBe(409);
    expect(state.status).toBe('REJECTED');
    expect(auditEvents).toHaveLength(0);
  });

  it('records only controlled audit metadata and never returns applicant data', async () => {
    const {env, auditEvents} = makeEnv();
    const response = await post(env, {authorization: auth()});
    const body = await response.text();
    expect(body).not.toContain('full_name');
    expect(body).not.toContain('email');
    expect(body).not.toContain(statusToken);
    expect(auditEvents[0]).toMatchObject({
      event_type: 'OPERATOR_STATUS_SYNC',
      actor_reference: 'operator-status-sync',
      old_status: 'APPLIED',
      new_status: 'UNDER_REVIEW',
      metadata_json: JSON.stringify({schema: 1, source: 'operator_status_sync'}),
    });
    expect(auditEvents[0].event_id).toBeTruthy();
    expect(auditEvents[0].event_timestamp).toBeTruthy();
  });

  it('rejects production plain HTTP', async () => {
    const {env} = makeEnv();
    env.BETA_ENVIRONMENT = 'production';
    const response = await onRequestPost({
      request: new Request(
        `http://localhost:8788/api/operator/applications/${applicationId}/status`,
        {
          method: 'POST',
          headers: {Authorization: auth(), 'Content-Type': 'application/json'},
          body: JSON.stringify({schema_version: 1, status: 'UNDER_REVIEW'}),
        },
      ),
      env,
      params: {applicationId},
    });
    expect(response.status).toBe(403);
  });
});


describe('authoritative status read and guarded reconciliation', () => {
  const read = (env, authorization = auth()) => onRequestGet({
    request: new Request(`http://localhost:8788/api/operator/applications/${applicationId}/status`,
      {headers: {Authorization: authorization}}), env, params: {applicationId},
  });
  const guarded = (env, expected, status) => onRequestPost({
    request: new Request(`http://localhost:8788/api/operator/applications/${applicationId}/status`, {
      method: 'POST', headers: {Authorization: auth(), 'Content-Type': 'application/json',
        'X-QuantumStudio-Expected-Status': expected}, body: JSON.stringify({schema_version: 1, status}),
    }), env, params: {applicationId},
  });
  it('reads only authoritative status with the dedicated status token', async () => {
    const {env, auditEvents} = makeEnv();
    expect((await read(env, auth(readToken))).status).toBe(403);
    expect((await read(env, 'Bearer invalid')).status).toBe(403);
    const response = await read(env);
    expect(response.headers.get('cache-control')).toBe('no-store');
    expect(await response.json()).toEqual({schema_version: 1, application_id: applicationId,
      status: 'APPLIED', result: 'already_current'});
    expect(auditEvents).toHaveLength(0);
  });
  it('reconciles each valid edge and retries without duplicate audit', async () => {
    const {env, auditEvents} = makeEnv();
    expect((await guarded(env, (await (await read(env)).json()).status, 'UNDER_REVIEW')).status).toBe(200);
    // A later invocation reads UNDER_REVIEW after a partial previous run.
    expect((await guarded(env, (await (await read(env)).json()).status, 'APPROVED')).status).toBe(200);
    expect((await (await guarded(env, 'APPROVED', 'APPROVED')).json()).result).toBe('already_current');
    expect(auditEvents.map((e) => [e.old_status, e.new_status])).toEqual([
      ['APPLIED', 'UNDER_REVIEW'], ['UNDER_REVIEW', 'APPROVED'],
    ]);
  });
  it('still rejects a skipped edge even with the expected-state guard', async () => {
    const {env, auditEvents} = makeEnv();
    expect((await guarded(env, 'APPLIED', 'APPROVED')).status).toBe(409);
    expect(auditEvents).toHaveLength(0);
  });
  it('rejects a stale snapshot even if a transition from the new state would be legal', async () => {
    const {env, state, auditEvents} = makeEnv('UNDER_REVIEW');
    expect((await guarded(env, 'APPLIED', 'APPROVED')).status).toBe(409);
    expect(state.status).toBe('UNDER_REVIEW');
    expect(auditEvents).toHaveLength(0);
  });
  it('rejects a concurrent writer reaching the same target instead of assuming ownership', async () => {
    const {env, auditEvents} = makeEnv('APPLIED', {beforeBatch(state) { state.status = 'UNDER_REVIEW'; }});
    expect((await guarded(env, 'APPLIED', 'UNDER_REVIEW')).status).toBe(409);
    expect(auditEvents).toHaveLength(0);
  });
});
