import {describe, expect, it} from 'vitest';
import {
  handleApplicationPost, validateApplication, verifyTurnstile,
} from '../functions/_lib/beta-registration.js';
import {assertTransition} from '../functions/_lib/workflow.js';

const env = Object.freeze({
  BETA_ENVIRONMENT: 'local', BETA_ALLOWED_ORIGIN: 'http://localhost:8788',
  BETA_PRIVACY_VERSION: 'draft-0.1', BETA_TERMS_VERSION: 'draft-0.1',
  BETA_IDENTITY_PEPPER: 'synthetic-test-pepper', BETA_TURNSTILE_TEST_MODE: 'true',
});
const payload = () => ({
  fullName: 'Ada Example', email: 'ADA@EXAMPLE.TEST ', institution: 'Example Institute',
  country: 'Exampleland', researchArea: 'Electronic structure', operatingSystem: 'Windows',
  academicRole: '', evaluationDescription: '', privacyAccepted: true, termsAccepted: true,
  communicationsAccepted: false, turnstileToken: 'test-pass',
});
class Statement { constructor(sql) { this.sql = sql; this.values = []; } bind(...values) { this.values = values; return this; } }
class FakeD1 {
  constructor({duplicate = false} = {}) { this.duplicate = duplicate; this.statements = []; }
  prepare(sql) { const statement = new Statement(sql); this.statements.push(statement); return statement; }
  async batch(statements) { if (this.duplicate) throw new Error('UNIQUE constraint failed'); this.batchStatements = statements; return []; }
}
function request(body = payload(), headers = {}) { return new Request('http://worker.test/api/beta/applications', {method: 'POST', headers: {Origin: env.BETA_ALLOWED_ORIGIN, 'Content-Type': 'application/json', ...headers}, body: typeof body === 'string' ? body : JSON.stringify(body)}); }

describe('private beta registration endpoint', () => {
  it('creates only APPLIED and an audit event, without returning PII', async () => {
    const db = new FakeD1(); const response = await handleApplicationPost(request(), {...env, BETA_DB: db}); const body = await response.json();
    expect(response.status).toBe(202); expect(body).toMatchObject({accepted: true}); expect(body).not.toHaveProperty('email'); expect(body).not.toHaveProperty('fullName');
    expect(db.batchStatements).toHaveLength(2); expect(db.batchStatements[0].sql).toContain("'APPLIED'"); expect(db.batchStatements[0].sql).not.toContain('LICENSE_ISSUED'); expect(db.batchStatements[1].sql).toContain('APPLICATION_SUBMITTED');
    expect(db.batchStatements[0].values).toContain('ada@example.test');
  });

  it.each([
    ['missing required field', {...payload(), fullName: ''}], ['malformed email', {...payload(), email: 'not-an-email'}],
    ['excessive field', {...payload(), institution: 'x'.repeat(161)}], ['unknown field', {...payload(), unexpected: true}],
    ['invalid operating system', {...payload(), operatingSystem: 'macOS'}], ['missing privacy', {...payload(), privacyAccepted: false}],
    ['missing terms', {...payload(), termsAccepted: false}], ['client licence field', {...payload(), licenceId: 'forbidden'}],
  ])('rejects %s', async (_name, body) => {
    const response = await handleApplicationPost(request(body), {...env, BETA_DB: new FakeD1()}); expect(response.status).toBe(400);
  });

  it('normalizes text and treats script-like input as data', () => {
    const result = validateApplication({...payload(), fullName: '  <script>alert(1)</script>  ', researchArea: '  material   modelling '});
    expect(result.ok).toBe(true); expect(result.value.fullName).toBe('<script>alert(1)</script>'); expect(result.value.researchArea).toBe('material modelling'); expect(result.value.communicationsAccepted).toBe(false);
  });

  it('rejects wrong media type, origin, missing production origin, and oversized requests', async () => {
    expect((await handleApplicationPost(request(payload(), {'Content-Type': 'text/plain'}), {...env, BETA_DB: new FakeD1()})).status).toBe(415);
    expect((await handleApplicationPost(request(payload(), {Origin: 'https://attacker.example'}), {...env, BETA_DB: new FakeD1()})).status).toBe(403);
    expect((await handleApplicationPost(request(), {...env, BETA_ALLOWED_ORIGIN: '', BETA_ENVIRONMENT: 'production', BETA_DB: new FakeD1()})).status).toBe(503);
    expect((await handleApplicationPost(request('x'.repeat(16_385)), {...env, BETA_DB: new FakeD1()})).status).toBe(413);
  });

  it('handles duplicates neutrally and supplies secure no-store headers', async () => {
    const response = await handleApplicationPost(request(), {...env, BETA_DB: new FakeD1({duplicate: true})}); const body = await response.json();
    expect(response.status).toBe(202); expect(body.applicationId).toBeNull(); expect(response.headers.get('cache-control')).toBe('no-store'); expect(response.headers.get('x-content-type-options')).toBe('nosniff');
  });
});

describe('Turnstile and workflow controls', () => {
  it.each([['', false], ['invalid', false], ['test-expired', false], ['test-duplicate', false], ['test-hostname-mismatch', false], ['test-action-mismatch', false], ['test-pass', true]])('validates local test token %s', async (token, ok) => {
    expect((await verifyTurnstile(token, env, new Request('http://worker.test'))).ok).toBe(ok);
  });
  it('fails closed when a production secret is missing', async () => {
    expect((await verifyTurnstile('token', {...env, BETA_ENVIRONMENT: 'production', BETA_TURNSTILE_TEST_MODE: 'false'}, new Request('http://worker.test'))).ok).toBe(false);
  });
  it.each([
    ['APPLIED', 'UNDER_REVIEW'], ['UNDER_REVIEW', 'APPROVED'], ['UNDER_REVIEW', 'REJECTED'],
    ['APPROVED', 'LICENSE_ISSUED'], ['LICENSE_ISSUED', 'EXPIRED'], ['EXPIRED', 'REVOKED'],
  ])('accepts valid transition %s -> %s', (from, to) => expect(() => assertTransition(from, to)).not.toThrow());
  it.each([['APPLIED', 'APPROVED'], ['REJECTED', 'APPROVED'], ['REVOKED', 'LICENSE_ISSUED']])('rejects invalid transition %s -> %s', (from, to) => expect(() => assertTransition(from, to)).toThrow());
});
