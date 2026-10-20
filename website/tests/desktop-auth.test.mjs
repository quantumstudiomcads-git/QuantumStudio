import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {mkdtempSync, readFileSync, readdirSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {onRequestPost as startRoute} from '../functions/api/desktop-auth/start.js';
import {onRequestPost as statusRoute} from '../functions/api/desktop-auth/status.js';
import {onRequestPost as cancelRoute} from '../functions/api/desktop-auth/cancel.js';
import {onRequestGet as detailsRoute, onRequestPost as confirmRoute} from '../functions/api/desktop-auth/confirm.js';
import {onRequest as middleware} from '../functions/_middleware.js';
import {AUTH_SESSION_COOKIE, sha256Hex, getValidatedSessionFromRequest} from '../functions/_lib/auth.js';

import {SQLiteD1} from './helpers/sqlite-d1.mjs';

// Process-per-query SQLite bridge is deliberately slower than local D1.
vi.setConfig({testTimeout: 30000});
const origin = 'http://localhost:8788';
const facts = (hex = 'a') => ({installation_id: `dev_${hex.repeat(32)}`, device_public_key_hash: hex.repeat(64),
  platform: 'windows', architecture: 'x86_64', app_version: '0.2.0'});
let root, db, env, cookie;
const post = (route, body, browser = false, overrides = {}) => route({env,
  request: new Request(`${origin}/api/desktop-auth/test`, {method: 'POST',
    headers: {'Content-Type': 'application/json', ...(browser ? {Cookie: cookie, Origin: origin} : {}), ...overrides}, body: JSON.stringify(body)})});
const start = (body = facts()) => post(startRoute, body);
const confirm = (challenge, headers = {}) => post(confirmRoute, {challenge_id: challenge.challenge_id}, true, headers);
const poll = (challenge, overrides = {}) => post(statusRoute, {challenge_id: challenge.challenge_id, device_code: challenge.device_code, ...overrides});

beforeEach(async () => {
  vi.useFakeTimers({toFake: ['Date']});
  vi.setSystemTime(new Date('2026-10-19T12:00:00Z'));
  root = mkdtempSync(join(tmpdir(), 'qs-m6-test-'));
  db = new SQLiteD1(join(root, 'local.sqlite3'));
  db.script(readdirSync('migrations').filter((p) => p.endsWith('.sql')).sort().map((p) => readFileSync(join('migrations', p), 'utf8')).join('\n'));
  db.script(`INSERT INTO users(user_id,full_name,institution,email,normalized_email,email_lookup_hash,status,created_at,updated_at)
    VALUES('user-a','Researcher','Institute','a@example.test','a@example.test','hash-a','VERIFIED','2026-10-19','2026-10-19');
    INSERT INTO beta_applications(application_id,full_name,email,normalized_email,email_lookup_hash,institution,country,research_area,
      operating_system,privacy_consent,privacy_version,terms_consent,terms_version,communications_consent,status,submitted_at,updated_at,user_id)
    VALUES('12345678-1234-4123-8123-123456789abc','Researcher','a@example.test','a@example.test','hash-a','Institute','Test','Materials',
      'Windows',1,'1',1,'1',0,'APPROVED','2026-10-19','2026-10-19','user-a');`);
  const hash = await sha256Hex('fixture-browser-secret');
  await db.prepare('INSERT INTO sessions VALUES(?,?,?,?,?,?,NULL)').bind('session-a', 'user-a', hash,
    '2026-10-19T12:00:00Z', '2026-10-20T12:00:00Z', '2026-10-19T12:00:00Z').run();
  cookie = `${AUTH_SESSION_COOKIE}=session-a.fixture-browser-secret`;
  env = {BETA_DB: db, BETA_ALLOWED_ORIGIN: origin, BETA_ENVIRONMENT: 'local', BETA_IDENTITY_PEPPER: 'synthetic-test-pepper'};
});
afterEach(() => { vi.useRealTimers(); if (root) rmSync(root, {recursive: true, force: true}); });

describe('desktop browser activation protocol with real SQLite', () => {
  it('creates unique random challenges and stores only hashed device secrets plus public facts', async () => {
    const one = await (await start()).json();
    const two = await (await start()).json();
    expect(one.challenge_id).toMatch(/^[0-9a-f]{64}$/);
    expect(one.device_code).toMatch(/^[0-9a-f]{64}$/);
    expect(one.challenge_id).not.toBe(two.challenge_id);
    expect(one.device_code).not.toBe(two.device_code);
    expect(one.verification_url).toBe(`${origin}/desktop-auth?challenge=${one.challenge_id}`);
    expect(one.verification_url).not.toContain(one.device_code);
    const row = await db.prepare('SELECT * FROM desktop_auth_challenges WHERE challenge_id = ?').bind(one.challenge_id).first();
    expect(row.device_code_hash).toBe(await sha256Hex(one.device_code));
    expect(JSON.stringify(row)).not.toContain(one.device_code);
    expect(JSON.parse(row.facts_json)).toEqual(facts());
    expect(one.expires_in).toBe(300);
  });

  it('uses normal browser login and refuses unauthenticated confirmation', async () => {
    const challenge = await (await start()).json();
    const request = new Request(challenge.verification_url);
    const redirect = await middleware({request, env, next: () => new Response('page')});
    expect(redirect.status).toBe(302);
    const destination = new URL(redirect.headers.get('Location'));
    expect(destination.pathname).toBe('/login');
    expect(destination.searchParams.get('returnTo')).toBe(`/desktop-auth?challenge=${challenge.challenge_id}`);
    expect((await post(confirmRoute, {challenge_id: challenge.challenge_id}, false, {Origin: origin})).status).toBe(401);
    expect((await detailsRoute({env, request: new Request(`${origin}/api/desktop-auth/confirm?challenge=${challenge.challenge_id}`)})).status).toBe(401);
  });

  it('confirms once and returns a single AUTHORIZED device result without desktop browser cookies', async () => {
    const challenge = await (await start()).json();
    const details = await detailsRoute({env, request: new Request(`${origin}/api/desktop-auth/confirm?challenge=${challenge.challenge_id}`, {headers: {Cookie: cookie}})});
    expect(await details.json()).toMatchObject({installation_id: facts().installation_id, state: 'pending'});
    expect(await (await poll(challenge)).json()).toEqual({state: 'pending'});
    expect((await confirm(challenge)).status).toBe(200);
    expect((await confirm(challenge)).status).toBe(409);
    vi.setSystemTime(Date.now() + 3000);
    const response = await poll(challenge);
    expect(response.headers.get('Cache-Control')).toBe('no-store');
    const result = await response.json();
    expect(result).toMatchObject({state: 'completed', activation: {installation_id: facts().installation_id, status: 'AUTHORIZED'}});
    expect(Object.keys(result.activation).sort()).toEqual(['activation_request_id', 'installation_id', 'status']);
    expect(await (await poll(challenge)).json()).toEqual({state: 'consumed'});
    expect((await db.prepare('SELECT * FROM beta_activations').all()).results).toHaveLength(1);
    expect((await getValidatedSessionFromRequest(new Request(origin, {headers: {Authorization: `Bearer ${challenge.device_code}`}}), env)).ok).toBe(false);
  });

  it('reuses the existing automatic device-limit policy and preserves M5 metadata', async () => {
    env.BETA_MAX_ACTIVE_DEVICES = '1';
    const first = await (await start()).json();
    await confirm(first);
    expect((await (await poll(first)).json()).activation.status).toBe('AUTHORIZED');
    await db.prepare("UPDATE beta_activations SET licence_id = 'existing-M5-metadata'").run();
    const second = await (await start(facts('b'))).json();
    await confirm(second);
    expect((await (await poll(second)).json()).activation.status).toBe('FLAGGED');
    const retry = await (await start()).json();
    await confirm(retry);
    expect((await (await poll(retry)).json()).activation.status).toBe('AUTHORIZED');
    const rows = (await db.prepare('SELECT * FROM beta_activations ORDER BY installation_id').all()).results;
    expect(rows).toHaveLength(2);
    expect(rows[0].licence_id).toBe('existing-M5-metadata');
    expect(rows[1].flag_reason).toBe('DEVICE_LIMIT');
  });

  it('rejects expired confirmation and reports expired polling', async () => {
    const challenge = await (await start()).json();
    vi.setSystemTime(Date.now() + 300000);
    expect((await confirm(challenge)).status).toBe(410);
    expect(await (await poll(challenge)).json()).toEqual({state: 'expired'});
    expect((await db.prepare('SELECT * FROM beta_activations').all()).results).toHaveLength(0);
  });

  it('rejects CSRF, secret substitution, private fields and device transaction substitution', async () => {
    const challenge = await (await start()).json();
    expect((await confirm(challenge, {Origin: 'https://evil.example'})).status).toBe(403);
    expect((await post(confirmRoute, {challenge_id: challenge.challenge_id}, false, {Cookie: cookie})).status).toBe(403);
    expect((await poll({...challenge, device_code: 'b'.repeat(64)})).status).toBe(400);
    expect((await poll(challenge, {installation_id: facts('b').installation_id})).status).toBe(400);
    expect((await start({...facts(), private_key: 'never-send'})).status).toBe(400);
    expect((await start({...facts(), device_public_key_hash: 'b'.repeat(64)})).status).toBe(400);
    expect((await post(confirmRoute, {challenge_id: challenge.challenge_id, user_id: 'other-user'}, true)).status).toBe(400);
    expect((await db.prepare('SELECT * FROM beta_activations').all()).results).toHaveLength(0);
  });

  it('rate-limits starts and pending polling', async () => {
    const challenge = await (await start()).json();
    expect(await (await poll(challenge)).json()).toEqual({state: 'pending'});
    expect((await poll(challenge)).status).toBe(429);
    for (let n = 0; n < 9; n++) expect((await start()).status).toBe(200);
    expect((await start()).status).toBe(429);
    vi.setSystemTime(Date.now() + 3000);
    expect((await poll(challenge)).status).toBe(200);
  });

  it('cancels safely and cleans abandoned challenges after retention', async () => {
    const challenge = await (await start()).json();
    expect((await post(cancelRoute, {challenge_id: challenge.challenge_id, device_code: challenge.device_code})).status).toBe(200);
    expect(await (await poll(challenge)).json()).toEqual({state: 'cancelled'});
    expect((await confirm(challenge)).status).toBe(409);
    vi.setSystemTime(Date.now() + 2 * 86400000);
    expect((await start()).status).toBe(200);
    expect((await poll(challenge)).status).toBe(400);
  });

  it('prevents concurrent confirmations and concurrent result consumption', async () => {
    const challenge = await (await start()).json();
    const confirmation = await Promise.all([confirm(challenge), confirm(challenge)]);
    expect(confirmation.map((r) => r.status).sort()).toEqual([200, 409]);
    const results = await Promise.all([poll(challenge), poll(challenge)]);
    const bodies = await Promise.all(results.map((r) => r.json()));
    expect(bodies.filter((r) => r.state === 'completed')).toHaveLength(1);
    expect((await db.prepare('SELECT * FROM beta_activations').all()).results).toHaveLength(1);
  });

  it('reports missing application without fabricating an activation', async () => {
    await db.prepare('DELETE FROM beta_applications').run();
    const challenge = await (await start()).json();
    expect((await confirm(challenge)).status).toBe(403);
    expect(await (await poll(challenge)).json()).toEqual({state: 'failed'});
  });
});
