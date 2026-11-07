import {readFileSync} from 'node:fs';
import {describe, expect, it, vi} from 'vitest';
import {deploymentEnvironment, validateDeployment, websiteBuildConfiguration} from '../functions/_lib/deployment.js';
import {verifyTurnstile} from '../functions/_lib/beta-registration.js';
import {googleRuntimeValidation} from '../functions/_lib/google-auth.js';
import {setSessionCookieHeader, clearSessionCookieHeader} from '../functions/_lib/auth.js';
import {sendOtpEmail} from '../functions/_lib/email-delivery.js';
import {onRequest} from '../functions/_middleware.js';
import {onRequestPost as metadata} from '../functions/api/operator/activations/[activationId]/licence.js';

// Synthetic unit values only; no service contact, credentials or key provisioning.
function deployed(mode = 'production') {
  const origin = `https://${mode}.unit-fixture.org`;
  return {BETA_ENVIRONMENT: mode, BETA_ALLOWED_ORIGIN: origin, BETA_DB: {},
    AUTH_OTP_PEPPER: 'synthetic-unit-otp', BETA_IDENTITY_PEPPER: 'synthetic-unit-identity',
    TURNSTILE_SECRET_KEY: 'synthetic-unit-captcha-secret', TURNSTILE_SITE_KEY: 'synthetic-unit-public-widget',
    OPERATOR_SYNC_TOKEN: 'synthetic-unit-read', OPERATOR_STATUS_SYNC_TOKEN: 'synthetic-unit-status',
    OPERATOR_LICENCE_SYNC_TOKEN: 'synthetic-unit-metadata', OPERATOR_LICENCE_PUBLISH_TOKEN: 'synthetic-unit-publish',
    OPERATOR_ACTIVATION_REVOKE_TOKEN: 'synthetic-unit-revoke', BETA_PRIVACY_VERSION: 'unit-1', BETA_TERMS_VERSION: 'unit-1',
    GOOGLE_CLIENT_ID: 'synthetic-unit-client', GOOGLE_CLIENT_SECRET: 'synthetic-unit-oauth',
    GOOGLE_REDIRECT_URI: `${origin}/api/auth/google/callback`};
}

describe('deployment environment boundary', () => {
  it.each(['local', 'test'])('retains the explicit %s TEST workflow', async (mode) => {
    const env = {BETA_ENVIRONMENT: mode, BETA_TURNSTILE_TEST_MODE: 'true', AUTH_EMAIL_TEST_MODE: 'true'};
    expect(deploymentEnvironment(env)).toBe('local');
    expect(validateDeployment(env).ok).toBe(true);
    expect(websiteBuildConfiguration(env)).toMatchObject({url: 'http://127.0.0.1:8788', turnstileTestMode: true});
    expect((await verifyTurnstile('test-pass', env, new Request('http://localhost:8788'))).ok).toBe(true);
  });
  it.each([undefined, '', 'development', 'prod', 'PRODUCTION'])('fails closed on unspecified/invalid mode %s', (mode) => {
    expect(validateDeployment({BETA_ENVIRONMENT: mode}).ok).toBe(false);
    expect(() => websiteBuildConfiguration({BETA_ENVIRONMENT: mode})).toThrow();
  });
  for (const mode of ['staging', 'production']) {
    it(`${mode} accepts explicit production-style runtime and public build configuration`, () => {
      const env = deployed(mode);
      expect(validateDeployment(env)).toMatchObject({ok: true, environment: mode});
      expect(googleRuntimeValidation(env).ok).toBe(true);
      const publicConfig = websiteBuildConfiguration(env);
      expect(publicConfig.url).toBe(env.BETA_ALLOWED_ORIGIN);
      expect(publicConfig.baseUrl).toBe('/');
      expect(publicConfig.turnstileTestMode).toBe(false);
      for (const secret of ['AUTH_OTP_PEPPER', 'GOOGLE_CLIENT_SECRET', 'OPERATOR_SYNC_TOKEN', 'TURNSTILE_SECRET_KEY']) {
        expect(JSON.stringify(publicConfig)).not.toContain(env[secret]);
      }
    });
    it.each(['QS_TEST_LICENSING', 'QS_DESKTOP_AUTH_ALLOW_LOCAL_HTTP', 'BETA_TURNSTILE_TEST_MODE',
      'AUTH_EMAIL_TEST_MODE', 'CLOUDFLARE_LOCAL'])(`${mode} rejects enabled %s at runtime and build`, (name) => {
      for (const value of ['true', '1', true]) {
        const env = {...deployed(mode), [name]: value};
        expect(validateDeployment(env)).toMatchObject({ok: false, reason: 'test-setting-not-allowed'});
        expect(() => websiteBuildConfiguration(env)).toThrow();
      }
    });
    it.each(['http://localhost:8788', 'https://localhost', 'https://127.0.0.1', 'https://[::1]',
      'https://127.1', 'https://service.local', 'https://site.example', 'https://example.com',
      'https://replace-before-deployment.org', 'http://site.unit-fixture.org',
      'https://site.unit-fixture.org/path', 'https://user:secret@site.unit-fixture.org'])(`${mode} rejects origin %s`, (url) => {
      expect(validateDeployment({...deployed(mode), BETA_ALLOWED_ORIGIN: url}).ok).toBe(false);
    });
    it.each(['AUTH_OTP_PEPPER', 'BETA_IDENTITY_PEPPER', 'TURNSTILE_SECRET_KEY', 'OPERATOR_SYNC_TOKEN',
      'OPERATOR_STATUS_SYNC_TOKEN', 'OPERATOR_LICENCE_SYNC_TOKEN', 'OPERATOR_LICENCE_PUBLISH_TOKEN',
      'OPERATOR_ACTIVATION_REVOKE_TOKEN', 'BETA_PRIVACY_VERSION', 'BETA_TERMS_VERSION',
      'BETA_ALLOWED_ORIGIN', 'BETA_DB'])(`${mode} does not inherit local default for %s`, (name) => {
      const env = deployed(mode); delete env[name];
      expect(validateDeployment(env).ok).toBe(false);
    });
    it(`${mode} requires its own public build configuration`, () => {
      expect(() => websiteBuildConfiguration({BETA_ENVIRONMENT: mode})).toThrow();
      expect(() => websiteBuildConfiguration({...deployed(mode), TURNSTILE_SITE_KEY: ''})).toThrow();
      expect(validateDeployment({...deployed(mode), QS_TEST_LICENCE_TRUST_FILE: 'local.json'}).ok).toBe(false);
    });
    it(`${mode} uses secure cookies and refuses stub email without leaking OTP`, async () => {
      const env = deployed(mode), log = vi.spyOn(console, 'log').mockImplementation(() => {});
      try {
        expect(setSessionCookieHeader({sessionId: 'unit', rawToken: 'unit', maxAgeSeconds: 60, env})).toContain('; Secure');
        expect(clearSessionCookieHeader(env)).toContain('; Secure');
        const result = await sendOtpEmail({email: 'unit@example.test', otp: '123456', purpose: 'LOGIN', expiryMinutes: 5, env});
        expect(result.ok).toBe(false); expect(result).not.toHaveProperty('devOtp'); expect(log).not.toHaveBeenCalled();
      } finally { log.mockRestore(); }
    });
    it(`${mode} cannot enable existing TEST metadata/delivery adapters`, async () => {
      const response = await metadata({request: new Request('https://site.unit-fixture.org/api/operator/activations/unit/licence', {method: 'POST'}), env: deployed(mode)});
      expect(response.status).toBe(403);
    });
  }
  it.each(['1x00000000000000000000AA', '2x00000000000000000000AB', '3x00000000000000000000FF'])(
    'refuses dummy Turnstile credentials %s even without a test-mode flag', (key) => {
      expect(() => websiteBuildConfiguration({...deployed(), TURNSTILE_SITE_KEY: key})).toThrow();
      expect(validateDeployment({...deployed(), TURNSTILE_SECRET_KEY: key}).ok).toBe(false);
    });
  it.each(['http://localhost:8788/api/auth/google/callback', 'https://other.unit-fixture.org/api/auth/google/callback',
    'https://production.unit-fixture.org/wrong', 'https://user:secret@production.unit-fixture.org/api/auth/google/callback'])(
    'rejects invalid deployed OAuth callback %s', (uri) => {
      expect(googleRuntimeValidation({...deployed(), GOOGLE_REDIRECT_URI: uri}).ok).toBe(false);
    });
  it.each(['staging', 'production'])('rejects HTTP requests in %s before routing', async (mode) => {
    const next = vi.fn();
    const response = await onRequest({request: new Request(`http://${mode}.unit-fixture.org/api/auth/session`), env: deployed(mode), next});
    expect(response.status).toBe(403); expect(next).not.toHaveBeenCalled();
    expect(await response.json()).toEqual({error: {code: 'https_required'}});
  });
  it('blocks requests before routing when configuration is invalid, with a redacted failure', async () => {
    const next = vi.fn();
    const response = await onRequest({request: new Request('https://site.unit-fixture.org/api/auth/session'),
      env: {...deployed(), QS_TEST_LICENSING: '1'}, next});
    expect(response.status).toBe(503); expect(next).not.toHaveBeenCalled();
    expect(await response.json()).toEqual({error: {code: 'configuration_unavailable'}});
  });
  it('passes valid deployed API requests to the existing route', async () => {
    const next = vi.fn(async () => new Response('existing route'));
    const response = await onRequest({request: new Request('https://production.unit-fixture.org/api/auth/session'), env: deployed(), next});
    expect(await response.text()).toBe('existing route'); expect(next).toHaveBeenCalledOnce();
  });
});


describe('dashboard-managed Pages deployment configuration', () => {
  const localWrangler = readFileSync(new URL('../wrangler.toml', import.meta.url), 'utf8')
    .split(/\r?\n/).filter((line) => !line.trim().startsWith('#')).join('\n');

  it('keeps Wrangler local-only so Pages does not override dashboard configuration', () => {
    expect(localWrangler).not.toMatch(/^\s*pages_build_output_dir\s*=/m);
    expect(localWrangler).not.toMatch(/^\s*\[(?:vars|env\.[^\]]+\.vars)\]/m);
    expect(localWrangler).not.toMatch(/^\s*(?:BETA_ENVIRONMENT|BETA_ALLOWED_ORIGIN|BETA_PRIVACY_VERSION|BETA_TERMS_VERSION|BETA_TURNSTILE_TEST_MODE|AUTH_EMAIL_TEST_MODE)\s*=/m);
    expect(localWrangler).not.toContain('replace-before-deployment');
  });

  it('retains the local D1 identity and the explicit local build-directory command', () => {
    expect(localWrangler).toMatch(/\[\[d1_databases\]\]/);
    expect(localWrangler).toContain('binding = "BETA_DB"');
    expect(localWrangler).toContain('database_name = "quantum-studio-beta"');
    expect(localWrangler).toContain('migrations_dir = "migrations"');
    const scripts = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8')).scripts;
    expect(scripts['pages:dev']).toContain('wrangler pages dev build');
    expect(scripts['d1:migrate:local']).toContain('--local --config wrangler.toml');
  });

  it.each(['staging', 'production'])('builds %s from externally supplied process variables', (mode) => {
    const supplied = {BETA_ENVIRONMENT: mode, BETA_ALLOWED_ORIGIN: `https://${mode}.unit-fixture.org`,
      TURNSTILE_SITE_KEY: 'synthetic-public-widget', BETA_TURNSTILE_TEST_MODE: 'false',
      AUTH_EMAIL_TEST_MODE: 'false', CLOUDFLARE_LOCAL: 'false', QS_TEST_LICENSING: '0',
      QS_DESKTOP_AUTH_ALLOW_LOCAL_HTTP: '0', QS_TEST_LICENCE_TRUST_FILE: ''};
    try {
      for (const [name, value] of Object.entries(supplied)) vi.stubEnv(name, value);
      expect(websiteBuildConfiguration(process.env)).toEqual({environment: mode,
        url: supplied.BETA_ALLOWED_ORIGIN, baseUrl: '/',
        turnstileSiteKey: supplied.TURNSTILE_SITE_KEY, turnstileTestMode: false});
    } finally { vi.unstubAllEnvs(); }
  });

  it.each(['staging', 'production'])('%s still refuses the previous tracked placeholder origin', (mode) => {
    expect(() => websiteBuildConfiguration({...deployed(mode),
      BETA_ALLOWED_ORIGIN: 'https://replace-before-deployment.example'})).toThrow('invalid-deployment-origin');
  });

  it.each(['staging', 'production'])('%s still refuses missing external configuration', (mode) => {
    expect(() => websiteBuildConfiguration({BETA_ENVIRONMENT: mode})).toThrow('invalid-deployment-origin');
    expect(() => websiteBuildConfiguration({...deployed(mode), BETA_ALLOWED_ORIGIN: ''})).toThrow('invalid-deployment-origin');
    expect(() => websiteBuildConfiguration({...deployed(mode), TURNSTILE_SITE_KEY: ''})).toThrow('missing-turnstile-site-key');
  });
});
