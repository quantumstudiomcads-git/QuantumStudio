import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {fileURLToPath} from 'node:url';
import {mkdtempSync, writeFileSync, readFileSync, readdirSync, unlinkSync, rmdirSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {it, expect} from 'vitest';

it('keeps server email credentials and provider code out of an actual static build', async () => {
  const root = fileURLToPath(new URL('..', import.meta.url));
  const canary = 're_SYNTHETIC_BUILD_SECRET_CANARY_NOT_A_REAL_KEY_829174';
  const temporary = mkdtempSync(join(tmpdir(), 'qs-email-build-'));
  const guard = join(temporary, 'deny-network.cjs');
  // Even an accidental server import cannot make a real Resend request during this build.
  writeFileSync(guard, "globalThis.fetch = () => Promise.reject(new Error('Network is disabled in the email build test')); ");
  try {
    await promisify(execFile)(process.execPath, ['--require', guard, 'node_modules/@docusaurus/core/bin/docusaurus.mjs', 'build'], {
      cwd: root, timeout: 180000, maxBuffer: 2*1024*1024,
      env: {...process.env, BETA_ENVIRONMENT:'staging', BETA_ALLOWED_ORIGIN:'https://staging.unit-fixture.org',
        TURNSTILE_SITE_KEY:'synthetic-public-widget', BETA_TURNSTILE_TEST_MODE:'false', AUTH_EMAIL_TEST_MODE:'false',
        CLOUDFLARE_LOCAL:'false', QS_TEST_LICENSING:'0', QS_DESKTOP_AUTH_ALLOW_LOCAL_HTTP:'0', QS_TEST_LICENCE_TRUST_FILE:'',
        RESEND_API_KEY:canary, AUTH_EMAIL_PROVIDER:'resend', AUTH_EMAIL_FROM:'auth@mailer.unit-fixture.org'},
    });
    let inspected = 0;
    function inspect(directory) {
      for (const item of readdirSync(directory, {withFileTypes:true})) {
        const path = join(directory,item.name);
        if (item.isDirectory()) inspect(path);
        else {
          const content = readFileSync(path);
          for (const forbidden of [canary, 'RESEND_API_KEY', 'api.resend.com/emails']) {
            expect(content.includes(Buffer.from(forbidden)), 'Server email material must not enter static output').toBe(false);
          }
          inspected++;
        }
      }
    }
    inspect(join(root,'build'));
    expect(inspected).toBeGreaterThan(0);
  } finally { unlinkSync(guard); rmdirSync(temporary); }
}, 190000);
