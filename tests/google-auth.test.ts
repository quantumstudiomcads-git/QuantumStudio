import {describe, expect, it, vi} from 'vitest';
import {onRequestGet as googleStartHandler} from '../functions/api/auth/google/start.js';
import {onRequestGet as googleCallbackHandler} from '../functions/api/auth/google/callback.js';
import {requireGoogleAccountForIdentity, safeGoogleReturnTo} from '../functions/_lib/google-auth.js';

describe('google auth flow', () => {
  it('creates a secure Google auth URL with PKCE and a safe returnTo', async () => {
    const env = {
      GOOGLE_CLIENT_ID: 'google-client-id',
      GOOGLE_CLIENT_SECRET: 'super-secret-value',
      GOOGLE_REDIRECT_URI: 'http://127.0.0.1:8788/api/auth/google/callback',
      BETA_DB: {
        prepare() {
          return {
            bind() {
              return {
                run: async () => ({success: true}),
                first: async () => null,
                all: async () => ({results: []}),
              };
            },
          };
        },
      },
    } as any;

    const response = await googleStartHandler({request: new Request('https://example.com/api/auth/google/start?returnTo=/beta-access'), env});
    expect(response.status).toBe(302);
    const location = new URL(response.headers.get('Location') ?? 'https://example.com');
    expect(location.origin).toBe('https://accounts.google.com');
    expect(location.searchParams.get('state')).toBeTruthy();
    expect(location.searchParams.get('code_challenge')).toBeTruthy();
    expect(location.searchParams.get('scope')).toBe('openid email profile');
    expect(location.searchParams.get('prompt')).toBe('select_account');
  });

  it('rejects unsafe returnTo values and keeps the returnTo same-site only', () => {
    expect(safeGoogleReturnTo('/beta-access')).toBe('/beta-access');
    expect(safeGoogleReturnTo('//evil.example')).toBe('/account');
    expect(safeGoogleReturnTo('https://evil.example')).toBe('/account');
    expect(safeGoogleReturnTo('/\\evil.example')).toBe('/account');
  });

  it('links an existing verified user to the Google subject without creating a duplicate user', async () => {
    const env = {
      BETA_DB: {
        prepare(sql: string) {
          return {
            bind(...args: unknown[]) {
              if (sql.includes('FROM auth_identities')) {
                return {first: async () => null, all: async () => ({results: []}), run: async () => ({success: true})};
              }
              if (sql.includes('FROM users')) {
                return {first: async () => ({user_id: 'existing-user', email_verified_at: new Date().toISOString(), normalized_email: 'ada@example.com'}), all: async () => ({results: []}), run: async () => ({success: true})};
              }
              return {first: async () => null, all: async () => ({results: []}), run: async () => ({success: true})};
            },
          };
        },
      },
    } as any;

    const result = await requireGoogleAccountForIdentity(env, 'google-sub-1', 'Ada@Example.com');
    expect(result.ok).toBe(true);
    expect(result.userId).toBe('existing-user');
    expect(result.linked).toBe(true);
  });

  it('returns an existing Google user with a Quantum Studio session without mutating redirect headers', async () => {
    const state = 'google-oauth-state';
    const stateRow = {
      state_hash: 'state-hash',
      return_to: '/beta-access',
      code_verifier: 'code-verifier',
      expires_at: new Date(Date.now() + 60_000).toISOString(),
      used_at: null,
    };
    const identity = {identity_id: 'google-identity', user_id: 'existing-user'};
    const sessionStatements: Array<{sql: string; args: unknown[]}> = [];
    const env = {
      GOOGLE_CLIENT_ID: 'google-client-id',
      GOOGLE_CLIENT_SECRET: 'super-secret-value',
      GOOGLE_REDIRECT_URI: 'https://example.com/api/auth/google/callback',
      BETA_DB: {
        prepare(sql: string) {
          return {
            bind(...args: unknown[]) {
              return {
                first: async () => {
                  if (sql.includes('FROM google_oauth_states')) {
                    return stateRow;
                  }
                  if (sql.includes('FROM auth_identities')) {
                    return sql.includes('SELECT identity_id, user_id') ? identity : {identity_id: identity.identity_id};
                  }
                  return null;
                },
                run: async () => {
                  if (sql.includes('INSERT INTO sessions')) {
                    sessionStatements.push({sql, args});
                  }
                  return {success: true};
                },
                all: async () => ({results: []}),
              };
            },
          };
        },
      },
    } as any;
    const payload = {
      iss: 'https://accounts.google.com',
      aud: env.GOOGLE_CLIENT_ID,
      exp: Math.floor(Date.now() / 1000) + 60,
      email_verified: true,
      sub: 'existing-google-subject',
      email: 'ada@example.com',
      name: 'Ada Lovelace',
    };
    const idToken = `header.${Buffer.from(JSON.stringify(payload)).toString('base64url')}.signature`;
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({id_token: idToken}), {status: 200}));
    const redirectMock = vi.spyOn(Response, 'redirect').mockImplementation(() => {
      throw new TypeError("Can't modify immutable headers.");
    });
    vi.stubGlobal('fetch', fetchMock);

    try {
      const response = await googleCallbackHandler({
        request: new Request(`https://example.com/api/auth/google/callback?state=${state}&code=google-code`),
        env,
      });

      expect(sessionStatements).toHaveLength(1);
      expect(sessionStatements[0]?.args[1]).toBe('existing-user');
      expect(response.status).toBe(302);
      expect(response.headers.get('Location')).toBe('https://example.com/beta-access');
      expect(response.headers.get('Set-Cookie')).toMatch(/^qs_session=/);
      expect(response.headers.get('Cache-Control')).toBe('no-store');
      expect(redirectMock).not.toHaveBeenCalled();
    } finally {
      redirectMock.mockRestore();
      vi.unstubAllGlobals();
    }
  });
});
