// Shared by Pages Functions and the public site build. Never returns secret values.
export function deploymentEnvironment(env = {}) {
  const mode = env.BETA_ENVIRONMENT === 'test' ? 'local' : env.BETA_ENVIRONMENT;
  return ['local', 'staging', 'production'].includes(mode) ? mode : null;
}
export const isLocalDeployment = (env) => deploymentEnvironment(env) === 'local';
export const secureCookies = (env) => !isLocalDeployment(env);
const enabled = (value) => value === true || value === 'true' || value === '1';
const validFlag = (value) => [undefined, null, '', false, true, 'false', 'true', '0', '1'].includes(value);
export function placeholder(value) {
  return typeof value !== 'string' || !value.trim()
    || /(?:replace-with|replace-before|placeholder|0000000000)/i.test(value)
    || /^(?:local-test|local-dev|test-pass)/i.test(value);
}
export function validOrigin(value, mode) {
  try {
    const url = new URL(value), host = url.hostname.toLowerCase().replace(/\.$/, '');
    if (typeof value !== 'string' || value.trim() !== value || url.username || url.password
        || url.search || url.hash || url.pathname !== '/' || !['https:', 'http:'].includes(url.protocol)) return false;
    const local = ['localhost', '127.0.0.1', '[::1]'].includes(host);
    if (mode !== 'local' && (url.protocol !== 'https:' || local || !host.includes('.')
        || /^[\d.]+$/.test(host) || host.includes(':') || host.endsWith('.localdomain')
        || /(?:^|\.)(?:localhost|local|example|invalid|test)$/.test(host)
        || /(?:^|\.)example\.(?:com|org|net)$/.test(host) || placeholder(host))) return false;
    return url.protocol !== 'http:' || local;
  } catch {return false;}
}

/**
 * @returns {{ok: boolean, environment: string|null, production: boolean, origin?: string, reason?: string}}
 */
export function validateDeployment(env = {}, {scope = 'runtime'} = {}) {
  const environment = deploymentEnvironment(env), production = environment === 'production';
  const fail = (reason) => ({ok: false, environment, production, reason});
  if (!environment) return fail('invalid-environment');
  for (const name of ['BETA_TURNSTILE_TEST_MODE', 'AUTH_EMAIL_TEST_MODE', 'CLOUDFLARE_LOCAL',
    'QS_TEST_LICENSING', 'QS_DESKTOP_AUTH_ALLOW_LOCAL_HTTP']) {
    if (!validFlag(env[name])) return fail('invalid-test-flag');
    if (environment !== 'local' && enabled(env[name])) return fail('test-setting-not-allowed');
  }
  if (environment !== 'local' && env.QS_TEST_LICENCE_TRUST_FILE) return fail('test-trust-not-allowed');
  if (environment === 'local') return {ok: true, environment, production, origin: env.BETA_ALLOWED_ORIGIN};
  if (!validOrigin(env.BETA_ALLOWED_ORIGIN, environment)) return fail('invalid-deployment-origin');
  if (scope === 'build') {
    if (placeholder(env.TURNSTILE_SITE_KEY)) return fail('missing-turnstile-site-key');
  } else {
    if (!env.AUTH_OTP_PEPPER) return fail('missing-auth-otp-pepper');
    for (const name of ['AUTH_OTP_PEPPER', 'BETA_IDENTITY_PEPPER', 'TURNSTILE_SECRET_KEY',
      'OPERATOR_SYNC_TOKEN', 'OPERATOR_STATUS_SYNC_TOKEN', 'OPERATOR_LICENCE_SYNC_TOKEN',
      'OPERATOR_LICENCE_PUBLISH_TOKEN', 'OPERATOR_ACTIVATION_REVOKE_TOKEN',
      'BETA_PRIVACY_VERSION', 'BETA_TERMS_VERSION']) {
      if (placeholder(env[name])) return fail('missing-runtime-configuration');
    }
    if (!env.BETA_DB) return fail('missing-database-binding');
  }
  return {ok: true, environment, production, origin: env.BETA_ALLOWED_ORIGIN.replace(/\/$/, '')};
}

export function websiteBuildConfiguration(env = {}) {
  const result = validateDeployment(env, {scope: 'build'});
  if (!result.ok) throw new Error('Website deployment configuration unavailable: ' + result.reason);
  const origin = result.environment === 'local' ? (env.BETA_ALLOWED_ORIGIN || 'http://127.0.0.1:8788') : result.origin;
  if (!validOrigin(origin, result.environment)) throw new Error('Website deployment origin is invalid.');
  return {environment: result.environment, url: origin.replace(/\/$/, ''), baseUrl: '/',
    turnstileSiteKey: env.TURNSTILE_SITE_KEY || '', turnstileTestMode: enabled(env.BETA_TURNSTILE_TEST_MODE)};
}
