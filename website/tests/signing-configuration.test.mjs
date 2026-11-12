import {afterEach,it,expect,vi} from 'vitest';
import {issueLicenceViaService} from '../functions/_lib/signing-service.js';
const secret='SENSITIVE_CALLER_SECRET_NEVER_LOG';
const publicKey=Buffer.alloc(32,57).toString('base64url');
const caller={schema_version:1,environment:'staging',caller:'pages-staging',secret:Buffer.alloc(32,53).toString('base64url')};
const trust={schema_version:1,environment:'staging',domain:'licence',algorithm:'Ed25519',keys:{'lic-fixture':publicKey}};
const callerChange=change=>env=>{env.QS_SIGNING_SERVICE_CALLER=JSON.stringify({...caller,...change});};
const trustChange=change=>env=>{env.QS_LICENCE_TRUST=JSON.stringify({...trust,...change});};
function environment() {
  return {BETA_ENVIRONMENT:'staging',BETA_ALLOWED_ORIGIN:'https://staging.unit-fixture.org',BETA_DB:{prepare:vi.fn()},
    AUTH_OTP_PEPPER:'synthetic-otp',BETA_IDENTITY_PEPPER:'synthetic-identity',TURNSTILE_SECRET_KEY:'synthetic-turnstile',
    OPERATOR_SYNC_TOKEN:'synthetic-read',OPERATOR_STATUS_SYNC_TOKEN:'synthetic-status',OPERATOR_LICENCE_SYNC_TOKEN:'synthetic-metadata',
    OPERATOR_LICENCE_PUBLISH_TOKEN:'synthetic-publish',OPERATOR_ACTIVATION_REVOKE_TOKEN:'synthetic-revoke',BETA_PRIVACY_VERSION:'1',BETA_TERMS_VERSION:'1',
    QS_SIGNING_SERVICE_CALLER:JSON.stringify(caller),QS_LICENCE_TRUST:JSON.stringify(trust),SIGNING_SERVICE:{fetch:vi.fn()}};
}
afterEach(()=>vi.restoreAllMocks());
const cases=[
  ['deployment_validation_failed',env=>{delete env.AUTH_OTP_PEPPER;}],
  ['invalid_environment',env=>{env.BETA_ENVIRONMENT=secret;}],
  ['signing_service_binding_missing',env=>{env.SIGNING_SERVICE={fetch:secret};}],
  ['caller_json_invalid',env=>{env.QS_SIGNING_SERVICE_CALLER=secret;}],
  ['caller_schema_invalid',callerChange({schema_version:2})],
  ['caller_schema_invalid',env=>{env.QS_SIGNING_SERVICE_CALLER='null';}],
  ['caller_schema_invalid',callerChange({unexpected:secret})],
  ['caller_environment_mismatch',callerChange({environment:'production'})],
  ['caller_name_invalid',callerChange({caller:secret+' invalid'})],
  ['caller_secret_invalid',callerChange({secret})],
  ['trust_json_invalid',env=>{env.QS_LICENCE_TRUST=secret;}],
  ['trust_schema_invalid',trustChange({schema_version:2})],
  ['trust_schema_invalid',env=>{env.QS_LICENCE_TRUST='[]';}],
  ['trust_environment_mismatch',trustChange({environment:'production'})],
  ['trust_domain_invalid',trustChange({domain:secret})],
  ['trust_algorithm_invalid',trustChange({algorithm:secret})],
  ...[null,[],{},secret,{'bad-kid':publicKey},{'lic-fixture':secret},Object.fromEntries(Array.from({length:33},(_,i)=>['lic-'+i,publicKey]))].map(keys=>['trust_keys_invalid',trustChange({keys})]),
];
it.each(cases)('rejects %s configuration without temporary logging (#%#)',async(reason,change)=>{
  const logs=['log','info','warn','error','debug'].map(name=>vi.spyOn(console,name).mockImplementation(()=>{}));
  const env=environment();const binding=env.SIGNING_SERVICE.fetch;change(env);
  const response=await issueLicenceViaService(env,'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa');
  expect(response.status).toBe(503);
  const text=await response.text();expect(text).toBe('{"error":{"code":"signing_not_configured"}}');
  for(const log of logs)expect(log).not.toHaveBeenCalled();
  const serialized=JSON.stringify(logs.flatMap(log=>log.mock.calls))+text;
  for(const value of [secret,caller.secret,publicKey,JSON.stringify(caller),JSON.stringify(trust),'Authorization','QS-HMAC-SHA256'])expect(serialized).not.toContain(value);
  for(const log of logs.filter(log=>log!==console.error))expect(log).not.toHaveBeenCalled();
  expect(binding).not.toHaveBeenCalled();expect(env.BETA_DB.prepare).not.toHaveBeenCalled();
});
it('local TEST issuance remains with its worker and logs no configuration failure',async()=>{
  const log=vi.spyOn(console,'error').mockImplementation(()=>{});
  const response=await issueLicenceViaService({BETA_ENVIRONMENT:'local'},'ignored');
  expect(response.status).toBe(409);expect(log).not.toHaveBeenCalled();
});
