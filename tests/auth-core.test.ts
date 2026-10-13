import {describe, expect, it, vi} from 'vitest';

vi.mock('../functions/_lib/beta-registration.js', async () => {
  const actual = await vi.importActual<typeof import('../functions/_lib/beta-registration.js')>('../functions/_lib/beta-registration.js');
  return {
    ...actual,
    verifyTurnstile: vi.fn(async () => ({ok: true})),
  };
});

import {authRuntimeValidation, buildAuthChallengePayload, createSessionForUser, enforceIssueLimits, hashOtpVerifier, issueChallengeForUser, verifyOtpChallenge} from '../functions/_lib/auth.js';
import {onRequestPost as loginHandler} from '../functions/api/auth/login.js';

function makePreparedDb(initialRows: Record<string, any> = {}) {
  const statements: Array<{sql: string; args: unknown[]}> = [];
  const selectFirst = vi.fn(async (sql: string, args: unknown[]) => {
    const key = JSON.stringify({sql, args});
    return initialRows[key] ?? null;
  });
  const prepare = vi.fn((sql: string) => ({
    bind: (...args: unknown[]) => ({
      async all() {
        statements.push({sql, args});
        return {results: []};
      },
      async first() {
        statements.push({sql, args});
        const key = JSON.stringify({sql, args});
        return initialRows[key] ?? null;
      },
      async run() {
        statements.push({sql, args});
        return {success: true};
      },
    }),
  }));

  return {prepare, statements};
}

describe('auth core security and throttling', () => {
  it('derives a keyed OTP verifier and rejects wrong values', async () => {
    const challengeId = 'signup-challenge-1';
    const otp = '123456';
    const verifier = await hashOtpVerifier('auth-pepper', challengeId, otp);
    expect(verifier).toMatch(/^[0-9a-f]{64}$/);
    expect(await hashOtpVerifier('auth-pepper', challengeId, '654321')).not.toBe(verifier);
    expect(await hashOtpVerifier('different-pepper', challengeId, otp)).not.toBe(verifier);
  });

  it('requires a matching purpose for OTP verification', async () => {
    const env = {
      BETA_ENVIRONMENT: 'development',
      AUTH_OTP_PEPPER: 'pepper-1',
      AUTH_EMAIL_TEST_MODE: 'true',
      BETA_DB: {
        prepare(sql: string) {
          return {
            bind(...args: unknown[]) {
              if (sql.includes('FROM auth_challenges')) {
                const purpose = args[1];
                return {
                  async first() {
                    if (purpose !== 'LOGIN') {
                      return null;
                    }
                    return {
                      challenge_id: 'login-challenge',
                      user_id: 'user-1',
                      normalized_email: 'ada@example.com',
                      purpose: 'LOGIN',
                      otp_hash: await hashOtpVerifier('pepper-1', 'login-challenge', '123456'),
                      expires_at: new Date(Date.now() + 60_000).toISOString(),
                      used_at: null,
                      attempt_count: 0,
                    };
                  },
                  all: async () => ({results: []}),
                };
              }
              return {first: async () => null, all: async () => ({results: []}), run: async () => ({})};
            },
          };
        },
      },
    } as any;

    const loginVerified = await verifyOtpChallenge(env, 'ada@example.com', 'LOGIN', '123456');
    expect(loginVerified.ok).toBe(true);

    const wrongPurpose = await verifyOtpChallenge(env, 'ada@example.com', 'SIGNUP', '123456');
    expect(wrongPurpose.ok).toBe(false);
    expect(wrongPurpose.code).toBe('invalid_otp');
  });

  it('enforces cooldown and hourly limits for OTP issuance', async () => {
    const now = Date.now();
    const env = {
      BETA_ENVIRONMENT: 'development',
      AUTH_OTP_PEPPER: 'pepper-2',
      AUTH_EMAIL_TEST_MODE: 'true',
      BETA_DB: {
        prepare(sql: string) {
          return {
            bind(...args: unknown[]) {
              if (sql.includes('SELECT created_at FROM auth_challenges')) {
                const fromDb = args[2] ? new Date(args[2] as string).getTime() : 0;
                return {all: async () => ({results: [
                  {created_at: new Date(now - 10_000).toISOString()},
                  {created_at: new Date(now - 20_000).toISOString()},
                  {created_at: new Date(now - 30_000).toISOString()},
                ]})};
              }
              return {first: async () => null, all: async () => ({results: []}), run: async () => ({})};
            },
          };
        },
      },
    } as any;

    const cooldownResult = await enforceIssueLimits(env, 'cooldown@example.com', 'LOGIN');
    expect(cooldownResult.ok).toBe(false);
    expect(cooldownResult.status).toBe(429);

    const hourlyEnv = {
      ...env,
      BETA_DB: {
        prepare(sql: string) {
          return {
            bind(...args: unknown[]) {
              if (sql.includes('SELECT created_at FROM auth_challenges')) {
                return {all: async () => ({results: Array.from({length: 5}, (_, index) => ({created_at: new Date(Date.now() - index * 60_000).toISOString()}))})};
              }
              return {first: async () => null, all: async () => ({results: []}), run: async () => ({})};
            },
          };
        },
      },
    } as any;

    const hourlyResult = await enforceIssueLimits(hourlyEnv, 'rate@example.com', 'LOGIN');
    expect(hourlyResult.ok).toBe(false);
    expect(hourlyResult.status).toBe(429);
  });

  it('locks a challenge after too many verification attempts', async () => {
    const env = {
      BETA_ENVIRONMENT: 'development',
      AUTH_OTP_PEPPER: 'pepper-3',
      AUTH_EMAIL_TEST_MODE: 'true',
      BETA_DB: {
        prepare(sql: string) {
          return {
            bind(...args: unknown[]) {
              if (sql.includes('FROM auth_challenges')) {
                const row = {
                  challenge_id: 'lockout-challenge',
                  user_id: 'user-9',
                  normalized_email: 'lock@example.com',
                  purpose: 'LOGIN',
                  otp_hash: 'not-used',
                  expires_at: new Date(Date.now() + 60_000).toISOString(),
                  used_at: null,
                  attempt_count: 5,
                };
                return {first: async () => row, all: async () => ({results: []})};
              }
              return {first: async () => null, all: async () => ({results: []}), run: async () => ({})};
            },
          };
        },
      },
    } as any;

    const result = await verifyOtpChallenge(env, 'lock@example.com', 'LOGIN', '123456');
    expect(result.ok).toBe(false);
    expect(result.status).toBe(429);
  });

  it('fails closed in production when the OTP pepper is missing', () => {
    const result = authRuntimeValidation({
      BETA_ENVIRONMENT: 'production',
      BETA_ALLOWED_ORIGIN: 'https://example.com',
      TURNSTILE_SECRET_KEY: 'secret',
      AUTH_EMAIL_TEST_MODE: 'false',
      BETA_TURNSTILE_TEST_MODE: 'false',
      AUTH_OTP_PEPPER: '',
    });
    expect(result.ok).toBe(false);
    expect(result.reason).toBe('missing-auth-otp-pepper');
  });

  it('never persists raw OTPs or raw session tokens', async () => {
    const challengeStatements: Array<{sql: string; args: unknown[]}> = [];
    const sessionStatements: Array<{sql: string; args: unknown[]}> = [];
    const env = {
      BETA_ENVIRONMENT: 'development',
      AUTH_OTP_PEPPER: 'pepper-4',
      AUTH_EMAIL_TEST_MODE: 'true',
      BETA_DB: {
        prepare(sql: string) {
          return {
            bind(...args: unknown[]) {
              if (sql.includes('INSERT INTO auth_challenges')) {
                challengeStatements.push({sql, args});
              }
              if (sql.includes('INSERT INTO sessions')) {
                sessionStatements.push({sql, args});
              }
              return {all: async () => ({results: []}), first: async () => null, run: async () => ({})};
            },
          };
        },
      },
    } as any;

    const challengeResult = await issueChallengeForUser(env, 'user-raw', 'raw@example.com', 'LOGIN');
    expect(challengeResult.ok).toBe(true);
    const challengeOtp = 'otp' in challengeResult ? challengeResult.otp : undefined;
    expect(challengeStatements[0]?.args[4]).not.toBe(challengeOtp);

    const session = await createSessionForUser(env, 'user-raw');
    expect(sessionStatements[0]?.args[2]).not.toBe(session.rawToken);
    expect(sessionStatements[0]?.args[2]).toMatch(/^[a-f0-9]{64}$/);
  });

  it('returns the same generic success shape for unknown and known login attempts', async () => {
    const turnstile = vi.mocked((await import('../functions/_lib/beta-registration.js')).verifyTurnstile);
    turnstile.mockResolvedValue({ok: true});

    const unknownEnv = {
      BETA_ENVIRONMENT: 'development',
      AUTH_OTP_PEPPER: 'pepper-5',
      AUTH_EMAIL_TEST_MODE: 'false',
      BETA_DB: {
        prepare(sql: string) {
          return {
            bind(...args: unknown[]) {
              if (sql.includes('FROM users WHERE normalized_email')) {
                return {first: async () => null, all: async () => ({results: []}), run: async () => ({})};
              }
              if (sql.includes('SELECT created_at FROM auth_challenges')) {
                return {all: async () => ({results: []})};
              }
              if (sql.includes('INSERT INTO auth_challenges')) {
                return {run: async () => ({})};
              }
              return {first: async () => null, all: async () => ({results: []}), run: async () => ({})};
            },
          };
        },
      },
    } as any;

    const unknownRequest = new Request('https://example.com/api/auth/login', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({email: 'ghost@example.com', turnstileToken: 'test-token'}),
    });
    const unknownResponse = await loginHandler({request: unknownRequest, env: unknownEnv});
    const unknownBody = await unknownResponse.json();
    expect(unknownBody).toMatchObject({ok: true, message: 'If an eligible account exists for this email, a verification code has been sent.', devOtp: null});

    const knownEnv = {
      ...unknownEnv,
      BETA_DB: {
        prepare(sql: string) {
          return {
            bind(...args: unknown[]) {
              if (sql.includes('FROM users WHERE normalized_email')) {
                return {first: async () => ({user_id: 'known-user', full_name: 'Ada', institution: 'Institute', email: 'known@example.com', normalized_email: 'known@example.com', email_verified_at: '2024-01-01T00:00:00.000Z', status: 'VERIFIED'})};
              }
              if (sql.includes('SELECT created_at FROM auth_challenges')) {
                return {all: async () => ({results: []})};
              }
              if (sql.includes('INSERT INTO auth_challenges')) {
                return {run: async () => ({})};
              }
              return {first: async () => null, all: async () => ({results: []}), run: async () => ({})};
            },
          };
        },
      },
    } as any;

    const knownRequest = new Request('https://example.com/api/auth/login', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({email: 'known@example.com', turnstileToken: 'test-token'}),
    });
    const knownResponse = await loginHandler({request: knownRequest, env: knownEnv});
    const knownBody = await knownResponse.json();
    expect(knownBody).toMatchObject({ok: true, message: 'If an eligible account exists for this email, a verification code has been sent.'});
    expect(knownBody).toHaveProperty('devOtp');
  });

  it('rejects invalid email and purpose payloads consistently', () => {
    expect(buildAuthChallengePayload({email: 'not-an-email', otp: '12345', purpose: 'INVALID'})).toMatchObject({ok: false, errors: {email: 'Invalid email address.', otp: 'Verification code must be a 6-digit number.', purpose: 'Unsupported challenge purpose.'}});
    expect(buildAuthChallengePayload({email: 'user@example.com', otp: '123456', purpose: 'login'})).toMatchObject({ok: true, value: {purpose: 'LOGIN'}});
  });
});
