import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {sendOtpEmail, createEmailProvider} from '../functions/_lib/email-delivery.js';
import {EMAIL_REQUEST_TIMEOUT_MS, ResendEmailProvider, validateResendConfiguration} from '../functions/_lib/email/resend.js';
import {websiteBuildConfiguration} from '../functions/_lib/deployment.js';
import {issueChallengeForUser} from '../functions/_lib/auth.js';

vi.mock('../functions/_lib/beta-registration.js', async () => {
  const actual = await vi.importActual('../functions/_lib/beta-registration.js');
  return {...actual, verifyTurnstile: vi.fn(async () => ({ok: true}))};
});
import {onRequestPost as login} from '../functions/api/auth/login.js';

const KEY = 're_SYNTHETIC_UNIT_EMAIL_SECRET_NEVER_REAL_948201';
const OTP = '619283';
const ID = '49a3999c-0ce1-4ea6-ab68-afcd6dc2e794';
const message = {email: 'recipient@example.test', otp: OTP, purpose: 'LOGIN', expiryMinutes: 10};
function environment(mode = 'staging') {
  return {BETA_ENVIRONMENT: mode, BETA_ALLOWED_ORIGIN: `https://${mode}.unit-fixture.org`, BETA_DB: {},
    AUTH_OTP_PEPPER: 'unit-otp-pepper', BETA_IDENTITY_PEPPER: 'unit-identity-pepper', TURNSTILE_SECRET_KEY: 'unit-captcha-secret',
    TURNSTILE_SITE_KEY: 'unit-public-widget', BETA_PRIVACY_VERSION: 'unit-1', BETA_TERMS_VERSION: 'unit-1',
    OPERATOR_SYNC_TOKEN: 'unit-read', OPERATOR_STATUS_SYNC_TOKEN: 'unit-status', OPERATOR_LICENCE_SYNC_TOKEN: 'unit-metadata',
    OPERATOR_LICENCE_PUBLISH_TOKEN: 'unit-publish', OPERATOR_ACTIVATION_REVOKE_TOKEN: 'unit-revoke',
    AUTH_EMAIL_TEST_MODE: 'false', BETA_TURNSTILE_TEST_MODE: 'false', AUTH_EMAIL_PROVIDER: 'resend',
    RESEND_API_KEY: KEY, AUTH_EMAIL_FROM: 'Quantum Studio <auth@mailer.unit-fixture.org>'};
}
const accepted = () => new Response(JSON.stringify({id: ID}), {status: 200, headers: {'Content-Type': 'application/json'}});
const send = (env, fetchImpl) => sendOtpEmail({...message, env}, fetchImpl);

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () => {throw new Error('Unexpected network: tests must mock delivery');}));
});
afterEach(() => {vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals();});

describe('local and deployed email provider selection', () => {
  it.each(['local', 'test'])('preserves %s test-email UI delivery with no network or OTP logging', async (mode) => {
    const logs = ['log', 'info', 'warn', 'error', 'debug'].map((name) => vi.spyOn(console, name).mockImplementation(() => {}));
    const result = await send({...environment(mode), AUTH_EMAIL_TEST_MODE: 'true'});
    expect(result).toEqual({ok: true, provider: 'local-dev', devOtp: OTP});
    expect(fetch).not.toHaveBeenCalled();
    for (const log of logs) expect(log).not.toHaveBeenCalled();
  });
  it('preserves the existing explicit-local stub and never sends externally', async () => {
    expect(await send(environment('local'))).toEqual({ok: true, provider: 'stub', devOtp: OTP});
    expect(fetch).not.toHaveBeenCalled();
  });
  for (const mode of ['staging', 'production']) {
    it.each(['', undefined, 'stub', 'local-dev', 'RESEND', 'unknown'])(`${mode} rejects provider %s`, async (provider) => {
      expect(await send({...environment(mode), AUTH_EMAIL_PROVIDER: provider})).toMatchObject({ok: false, kind: 'configuration'});
      expect(fetch).not.toHaveBeenCalled();
    });
    it(`${mode} rejects local test mode even with valid Resend settings`, async () => {
      const env = {...environment(mode), AUTH_EMAIL_TEST_MODE: 'true'};
      expect(await send(env)).toMatchObject({ok: false, kind: 'configuration'});
      expect(() => createEmailProvider(env)).toThrow('configuration');
      expect(fetch).not.toHaveBeenCalled();
    });
    it(`${mode} accepts only the configured real provider and never returns devOtp`, async () => {
      vi.mocked(fetch).mockResolvedValueOnce(accepted());
      const result = await send(environment(mode));
      expect(result).toEqual({ok: true, provider: 'resend'});
      expect(result).not.toHaveProperty('devOtp');
    });
  }
  it.each([undefined, '', 'development'])('missing/invalid deployment mode %s never selects local email', async (mode) => {
    const result = await send({...environment(), BETA_ENVIRONMENT: mode, AUTH_EMAIL_TEST_MODE: 'true'});
    expect(result.ok).toBe(false); expect(fetch).not.toHaveBeenCalled();
  });
});

describe('Resend configuration validation', () => {
  it.each(['auth@mailer.unit-fixture.org', 'Quantum Studio <auth@mailer.unit-fixture.org>'])(
    'accepts configured sender %s without returning credentials', (from) => {
      const result = validateResendConfiguration({...environment(), AUTH_EMAIL_FROM: from});
      expect(result).toEqual({ok: true}); expect(JSON.stringify(result)).not.toContain(KEY);
    });
  it.each(['', undefined, 'not-a-key', 're_short', 're_xxxxxxxxxxxxxxxxxxxxx', KEY+' ', KEY+'\r\nInjected: secret'])(
    'rejects missing/malformed API credentials #%#', async (key) => {
      const result = await send({...environment(), RESEND_API_KEY: key});
      expect(result).toMatchObject({ok: false, kind: 'configuration', reason: 'invalid-email-api-key'});
      expect(result).not.toHaveProperty('devOtp'); expect(fetch).not.toHaveBeenCalled();
    });
  it.each(['', undefined, 'bad', 'auth@localhost', 'auth@127.0.0.1', 'auth@example.com',
    'auth@replace-before-deployment.example', ' auth@mailer.unit-fixture.org',
    'auth@mailer.unit-fixture.org,other@mailer.unit-fixture.org', 'auth..code@mailer.unit-fixture.org',
    'auth@-bad.unit-fixture.org', 'Quantum Studio <auth@mailer.unit-fixture.org>\r\nBcc: recipient@example.test',
    'Quantum Studio <auth@mailer.unit-fixture.org> trailing', 'Quantum Studio <auth@mailer.unit-fixture.org> <other@site.org>'])(
    'rejects malformed/placeholder sender #%#', async (from) => {
      const result = await send({...environment(), AUTH_EMAIL_FROM: from});
      expect(result).toMatchObject({ok: false, kind: 'configuration', reason: 'invalid-email-sender'});
      expect(fetch).not.toHaveBeenCalled();
    });
  it('also enforces deployment gates when the Resend adapter is constructed directly', () => {
    expect(() => new ResendEmailProvider({...environment(), AUTH_EMAIL_TEST_MODE:'true'})).toThrow('configuration');
    expect(fetch).not.toHaveBeenCalled();
  });
  it('does not expose a credential in a configuration exception', () => {
    expect(() => new ResendEmailProvider({...environment(), AUTH_EMAIL_FROM: 'invalid'})).toThrow('Email provider configuration is unavailable.');
  });
});

describe('bounded Resend HTTPS adapter', () => {
  it.each(['direct', 'factory', 'auth-boundary'])('%s default fetch preserves the global receiver', async (path) => {
    const receiverSensitiveFetch = vi.fn(function(request) {
      if (this !== globalThis) throw new TypeError('Illegal invocation');
      expect(request).toBeInstanceOf(Request);
      return Promise.resolve(accepted());
    });
    vi.stubGlobal('fetch', receiverSensitiveFetch);
    const log = vi.spyOn(console, 'error').mockImplementation(() => {});
    const env = environment();
    const result = path === 'direct' ? await new ResendEmailProvider(env).send(message)
      : path === 'factory' ? await createEmailProvider(env).send(message)
      : await send(env);
    expect(result).toEqual({ok:true, provider:'resend'});
    expect(receiverSensitiveFetch).toHaveBeenCalledOnce();
    expect(receiverSensitiveFetch.mock.contexts[0]).toBe(globalThis);
    expect(log).not.toHaveBeenCalled();
  });
  it('preserves an explicitly injected fetch implementation', async () => {
    const injected = vi.fn(async () => accepted());
    expect(await send(environment(), injected)).toEqual({ok:true, provider:'resend'});
    expect(injected).toHaveBeenCalledExactlyOnceWith(expect.any(Request));
    expect(fetch).not.toHaveBeenCalled();
  });

  it.each(['LOGIN', 'SIGNUP'])('sends the unchanged %s OTP with configurable sender and expiry', async (purpose) => {
    vi.mocked(fetch).mockResolvedValueOnce(accepted());
    const env = environment();
    expect((await sendOtpEmail({...message, purpose, env})).ok).toBe(true);
    expect(fetch).toHaveBeenCalledOnce();
    const [options] = vi.mocked(fetch).mock.calls[0];
    expect(options).toBeInstanceOf(Request);
    expect(options.url).toBe('https://api.resend.com/emails');
    expect(options).toMatchObject({method: 'POST', redirect: 'manual'});
    expect(Object.fromEntries(options.headers)).toMatchObject({authorization: 'Bearer '+KEY, 'content-type': 'application/json', 'user-agent': 'QuantumStudio-Auth/0.2'});
    expect(await options.clone().json()).toEqual({from: env.AUTH_EMAIL_FROM, to: [message.email],
      subject: 'Quantum Studio verification code',
      text: `Your Quantum Studio verification code is: ${OTP}\n\nThis code expires in 10 minutes.\nIf you did not request this code, you can ignore this email.`});
    expect(options.signal).toBeInstanceOf(AbortSignal);
  });
  it.each([300, 301, 302, 303, 304, 305, 306, 307, 308, 399])('rejects HTTP %s without following redirects or reading sensitive headers/bodies', async (status) => {
    const logs = ['log', 'info', 'warn', 'error', 'debug'].map(name => vi.spyOn(console, name).mockImplementation(() => {}));
    const location = `https://redirect.unit-fixture.org/${KEY}/${OTP}/${message.email}`;
    const response = new Response(status === 304 ? null : `${KEY} ${OTP} ${message.email}`, {status, headers:{Location:location}});
    const headers = vi.spyOn(response.headers, 'get');
    const readText = vi.spyOn(response, 'text');
    const readJson = vi.spyOn(response, 'json');
    vi.mocked(fetch).mockResolvedValueOnce(response);
    expect(await send(environment())).toEqual({ok:false, provider:'resend', kind:'delivery', reason:'email-provider-redirect-rejected'});
    expect(fetch).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({redirect:'manual'}));
    expect(headers).not.toHaveBeenCalled();
    expect(readText).not.toHaveBeenCalled();
    expect(readJson).not.toHaveBeenCalled();
    expect(response.bodyUsed).toBe(false);
    for (const log of logs) expect(log).not.toHaveBeenCalled();
  });
  it.each([400, 401, 403, 422, 429, 500, 503])('handles HTTP %s without reading or leaking sensitive failure bodies', async (status) => {
    const response = new Response(JSON.stringify({message: `${KEY} ${OTP} ${message.email}`}), {status});
    const read = vi.spyOn(response, 'json'); const text = vi.spyOn(response, 'text');
    vi.mocked(fetch).mockResolvedValueOnce(response);
    const result = await send(environment());
    expect(result).toMatchObject({ok: false, kind: [401, 403].includes(status) ? 'configuration' : 'delivery'});
    expect(result).not.toHaveProperty('devOtp'); expect(read).not.toHaveBeenCalled(); expect(text).not.toHaveBeenCalled();
    expect(JSON.stringify(result)).not.toContain(KEY); expect(JSON.stringify(result)).not.toContain(OTP);
    expect(fetch).toHaveBeenCalledOnce(); // No automatic retries or duplicate OTP messages.
  });
  it.each(['{}', 'null', '[]', 'not-json', JSON.stringify({id: 'not-a-provider-id'}),
    JSON.stringify({error: {message: KEY+' '+OTP}}), JSON.stringify({id: ID, error: {message: KEY}})])(
    'rejects malformed/API-error success acknowledgement #%#', async (body) => {
      vi.mocked(fetch).mockResolvedValueOnce(new Response(body, {headers: {'Content-Type':'application/json'}}));
      expect(await send(environment())).toMatchObject({ok:false, kind:'delivery', reason:'invalid-email-provider-response'});
    });
  it('rejects oversized or non-JSON acknowledgements', async () => {
    for (const response of [new Response('x'.repeat(5000), {headers:{'Content-Type':'application/json'}}),
      new Response(JSON.stringify({id:ID}), {headers:{'Content-Type':'text/html'}})]) {
      vi.mocked(fetch).mockResolvedValueOnce(response);
      expect(await send(environment())).toMatchObject({ok:false,reason:'invalid-email-provider-response'});
    }
  });
  it.each(['staging', 'production'])('%s logs only safe transport metadata, excluding exception details', async (mode) => {
    const logs = ['log', 'info', 'warn', 'error', 'debug'].map((name) => vi.spyOn(console, name).mockImplementation(() => {}));
    const error = new TypeError(`${KEY} ${OTP} ${message.email}`);
    error.stack = `Authorization: Bearer ${KEY}`;
    error.code = message.email;
    vi.mocked(fetch).mockRejectedValueOnce(error);
    const result = await send(environment(mode));
    expect(result).toEqual({ok:false,provider:'resend',kind:'delivery',reason:'email-transport-failed'});
    expect(console.error).toHaveBeenCalledExactlyOnceWith('qs-resend-transport-exception', {
      name: 'TypeError', stage: 'fetch', aborted: false, environment: mode,
    });
    const serialized = JSON.stringify(logs.flatMap(log => log.mock.calls));
    for (const forbidden of [KEY, OTP, message.email, 'Authorization', 'stack', 'code']) expect(serialized).not.toContain(forbidden);
    for (const log of logs.filter(log => log !== console.error)) expect(log).not.toHaveBeenCalled();
  });
  it.each(['custom-name', 'primitive'])('does not log sensitive %s exception values', async (kind) => {
    const log = vi.spyOn(console, 'error').mockImplementation(() => {});
    const secret = `${KEY} ${OTP} ${message.email}`;
    const error = new Error(secret);
    error.name = secret;
    vi.mocked(fetch).mockRejectedValueOnce(kind === 'primitive' ? secret : error);
    expect(await send(environment())).toMatchObject({ok:false, reason:'email-transport-failed'});
    expect(log).toHaveBeenCalledExactlyOnceWith('qs-resend-transport-exception', {
      name: kind === 'primitive' ? 'string' : 'Error', stage: 'fetch', aborted: false, environment: 'staging',
    });
    for (const forbidden of [KEY, OTP, message.email]) expect(JSON.stringify(log.mock.calls)).not.toContain(forbidden);
  });
  it('distinguishes request construction failure without fetching or leaking exception details', async () => {
    const logs = ['log', 'info', 'warn', 'error', 'debug'].map(name => vi.spyOn(console, name).mockImplementation(() => {}));
    const secret = `${KEY} ${OTP} ${message.email} Authorization Location`;
    vi.stubGlobal('Request', class {constructor() {throw new TypeError(secret);}});
    expect(await send(environment())).toEqual({ok:false, provider:'resend', kind:'delivery', reason:'email-transport-failed'});
    expect(fetch).not.toHaveBeenCalled();
    expect(console.error).toHaveBeenCalledExactlyOnceWith('qs-resend-request-construction-failure', {
      name:'TypeError', stage:'request-construction', environment:'staging',
    });
    const serialized = JSON.stringify(logs.flatMap(log => log.mock.calls));
    for (const forbidden of [KEY, OTP, message.email, 'Authorization', 'Location', 'stack']) expect(serialized).not.toContain(forbidden);
    for (const log of logs.filter(log => log !== console.error)) expect(log).not.toHaveBeenCalled();
  });
  it('logs aborted transport metadata while preserving the timeout result', async () => {
    vi.useFakeTimers();
    const log = vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.mocked(fetch).mockImplementation(({signal}) => new Promise((resolve, reject) => {
      signal.addEventListener('abort', () => reject(Object.assign(new Error(KEY+' '+OTP), {name:'AbortError'})));
    }));
    const pending = send(environment());
    await vi.advanceTimersByTimeAsync(EMAIL_REQUEST_TIMEOUT_MS);
    expect(await pending).toMatchObject({ok:false, reason:'email-request-timeout'});
    expect(log).toHaveBeenCalledExactlyOnceWith('qs-resend-transport-exception', {
      name:'AbortError', stage:'fetch', aborted:true, environment:'staging',
    });
  });
  it('bounds a hung request even when the fetch mock ignores AbortSignal', async () => {
    vi.useFakeTimers();
    vi.mocked(fetch).mockImplementation(() => new Promise(() => {}));
    const pending = send(environment());
    await vi.advanceTimersByTimeAsync(EMAIL_REQUEST_TIMEOUT_MS);
    expect(await pending).toEqual({ok:false,provider:'resend',kind:'delivery',reason:'email-request-timeout'});
    expect(vi.mocked(fetch).mock.calls[0][0].signal.aborted).toBe(true);
  });
  it('also bounds response-body reading', async () => {
    vi.useFakeTimers();
    vi.mocked(fetch).mockResolvedValue(new Response(new ReadableStream({start() {}}), {headers:{'Content-Type':'application/json'}}));
    const pending = send(environment());
    await vi.advanceTimersByTimeAsync(EMAIL_REQUEST_TIMEOUT_MS);
    expect(await pending).toMatchObject({ok:false,reason:'email-request-timeout'});
  });
});

function loginEnvironment() {
  const env = environment();
  env.BETA_DB = {prepare(sql) {return {bind() {return {
    first: async () => sql.includes('FROM users') ? {user_id:'unit-user',email_verified_at:'2026-11-09T00:00:00Z'} : null,
    all: async () => ({results:[]}), run: async () => ({success:true}),
  };}};}};
  return env;
}
function loginRequest(env) {
  return new Request(env.BETA_ALLOWED_ORIGIN+'/api/auth/login', {method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({email:message.email,turnstileToken:'unit-captcha'})});
}

describe('existing auth route delivery boundary', () => {
  it('returns generic success with no OTP or API credential after provider acceptance', async () => {
    const env = loginEnvironment();
    vi.mocked(fetch).mockResolvedValueOnce(accepted());
    const response = await login({request:loginRequest(env),env});
    expect(response.status).toBe(200);
    const body = await response.json();
    expect(body.devOtp).toBeNull(); expect(body.ok).toBe(true);
    const outbound = await vi.mocked(fetch).mock.calls[0][0].clone().json();
    const sentOtp = outbound.text.match(/\b\d{6}\b/)[0];
    expect(JSON.stringify(body)).not.toContain(sentOtp); expect(JSON.stringify(body)).not.toContain(KEY);
  });
  it('maps configuration and provider failures to the same existing safe external message', async () => {
    const log = vi.spyOn(console, 'error').mockImplementation(() => {});
    for (const configured of [false, true]) {
      const env = loginEnvironment();
      if (!configured) delete env.RESEND_API_KEY;
      else vi.mocked(fetch).mockResolvedValueOnce(new Response(KEY+' '+OTP, {status:403}));
      const response = await login({request:loginRequest(env),env});
      expect(response.status).toBe(503);
      expect(await response.json()).toEqual({ok:false,message:'Verification delivery is temporarily unavailable.'});
      expect(log).toHaveBeenLastCalledWith('qs-email-delivery-failure', {
        provider: configured ? 'resend' : null, kind: 'configuration',
        reason: configured ? 'email-provider-configuration-rejected' : 'invalid-email-api-key',
        environment: 'staging', purpose: 'LOGIN',
      });
    }
  });
  it('keeps the browser response generic for transport exceptions without logging sensitive details', async () => {
    const log = vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.spyOn(Math, 'random').mockReturnValue(0.5);
    const env = loginEnvironment();
    vi.mocked(fetch).mockRejectedValueOnce(new TypeError(`${KEY} ${message.email} 550000`));
    const response = await login({request:loginRequest(env),env});
    expect(response.status).toBe(503);
    expect(await response.json()).toEqual({ok:false,message:'Verification delivery is temporarily unavailable.'});
    expect(log).toHaveBeenNthCalledWith(1, 'qs-resend-transport-exception', {
      name:'TypeError', stage:'fetch', aborted:false, environment:'staging',
    });
    expect(log).toHaveBeenCalledTimes(2);
    for (const forbidden of [KEY, message.email, '550000', env.AUTH_EMAIL_FROM]) expect(JSON.stringify(log.mock.calls)).not.toContain(forbidden);
  });
  it.each([301, 302, 307, 308])('keeps HTTP %s redirect details out of browser responses and logs', async (status) => {
    const logs = ['log', 'info', 'warn', 'error', 'debug'].map(name => vi.spyOn(console, name).mockImplementation(() => {}));
    vi.spyOn(Math, 'random').mockReturnValue(0.5);
    const env = loginEnvironment();
    const location = `https://redirect.unit-fixture.org/${KEY}/${message.email}/550000`;
    vi.mocked(fetch).mockResolvedValueOnce(new Response(`${KEY} ${message.email} 550000`, {status, headers:{Location:location}}));
    const response = await login({request:loginRequest(env),env});
    expect(response.status).toBe(503);
    const body = await response.json();
    expect(body).toEqual({ok:false,message:'Verification delivery is temporarily unavailable.'});
    expect(fetch).toHaveBeenCalledOnce();
    expect(console.error).toHaveBeenCalledExactlyOnceWith('qs-email-delivery-failure', {
      provider:'resend', kind:'delivery', reason:'email-provider-redirect-rejected', environment:'staging', purpose:'LOGIN',
    });
    const serialized = JSON.stringify([body, ...logs.flatMap(log => log.mock.calls)]);
    for (const forbidden of [KEY, message.email, '550000', location, 'Location', env.AUTH_EMAIL_FROM]) expect(serialized).not.toContain(forbidden);
    for (const log of logs.filter(log => log !== console.error)) expect(log).not.toHaveBeenCalled();
  });
  it('never exports provider credentials in the public build configuration', () => {
    const result = websiteBuildConfiguration(environment());
    expect(JSON.stringify(result)).not.toContain(KEY);
    expect(result).not.toHaveProperty('RESEND_API_KEY'); expect(result).not.toHaveProperty('AUTH_EMAIL_FROM');
  });
});

describe('safe auth email failure observability', () => {
  for (const mode of ['staging', 'production']) {
    it.each(['SIGNUP','LOGIN'])(`${mode} logs only safe failure fields for %s`, async (purpose) => {
      const logs = ['log','info','warn','error','debug'].map(name => vi.spyOn(console,name).mockImplementation(() => {}));
      vi.spyOn(Math,'random').mockReturnValue(0.5);
      const env=loginEnvironment();env.BETA_ENVIRONMENT=mode;
      const privateBody=`${KEY} ${message.email} 550000 Authorization: Bearer private-header`;
      vi.mocked(fetch).mockResolvedValueOnce(new Response(privateBody,{status:403}));
      const result=await issueChallengeForUser(env,'unit-user',message.email,purpose);
      expect(result).toEqual({ok:false,status:503,code:'email_delivery_unavailable',message:'Verification delivery is temporarily unavailable.'});
      const outbound=await vi.mocked(fetch).mock.calls[0][0].clone().json();
      const actualOtp=outbound.text.match(/\b\d{6}\b/)[0];
      expect(actualOtp).toBe('550000');
      expect(console.error).toHaveBeenCalledExactlyOnceWith('qs-email-delivery-failure',{
        provider:'resend',kind:'configuration',reason:'email-provider-configuration-rejected',environment:mode,purpose,
      });
      const serialized=JSON.stringify(logs.flatMap(log=>log.mock.calls));
      for(const forbidden of [KEY,message.email,actualOtp,env.AUTH_EMAIL_FROM,privateBody,'Authorization','private-header',env.AUTH_OTP_PEPPER]) {
        expect(serialized).not.toContain(forbidden);
      }
      for(const log of logs.filter(log=>log!==console.error))expect(log).not.toHaveBeenCalled();
    });
  }
  it.each(['configuration','http','malformed','network'])('logs the adapter safe reason for %s failure', async (kind) => {
    const log=vi.spyOn(console,'error').mockImplementation(()=>{});
    const env=loginEnvironment();let expected;
    if(kind==='configuration') {delete env.RESEND_API_KEY;expected={provider:null,kind:'configuration',reason:'invalid-email-api-key'};}
    if(kind==='http') {vi.mocked(fetch).mockResolvedValueOnce(new Response(KEY+' '+message.email,{status:500}));expected={provider:'resend',kind:'delivery',reason:'email-provider-rejected'};}
    if(kind==='malformed') {vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({error:KEY+' '+message.email}),{headers:{'Content-Type':'application/json'}}));expected={provider:'resend',kind:'delivery',reason:'invalid-email-provider-response'};}
    if(kind==='network') {vi.mocked(fetch).mockRejectedValueOnce(new Error(KEY+' '+message.email));expected={provider:'resend',kind:'delivery',reason:'email-transport-failed'};}
    await issueChallengeForUser(env,'unit-user',message.email,'SIGNUP');
    expect(log).toHaveBeenCalledTimes(kind==='network'?2:1);
    expect(log).toHaveBeenLastCalledWith('qs-email-delivery-failure',{...expected,environment:'staging',purpose:'SIGNUP'});
    expect(JSON.stringify(log.mock.calls)).not.toContain(KEY);expect(JSON.stringify(log.mock.calls)).not.toContain(message.email);
  });
  it('does not log provider acceptance',async()=>{
    const log=vi.spyOn(console,'error').mockImplementation(()=>{});
    vi.mocked(fetch).mockResolvedValueOnce(accepted());
    expect((await issueChallengeForUser(loginEnvironment(),'unit-user',message.email,'SIGNUP')).ok).toBe(true);
    expect(log).not.toHaveBeenCalled();
  });
});
