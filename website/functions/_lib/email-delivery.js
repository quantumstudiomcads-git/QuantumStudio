import {validateDeployment, isLocalDeployment} from './deployment.js';
export async function sendOtpEmail({email, otp, purpose, expiryMinutes, env}) {
  if (!validateDeployment(env).ok) return {ok: false, provider: null, reason: 'Deployment configuration unavailable.'};
  const localDevMode = env.AUTH_EMAIL_TEST_MODE === 'true' && isLocalDeployment(env);

  if (localDevMode) {
    const payload = {to: email, otp, purpose, expiresInMinutes: expiryMinutes, provider: 'local-dev'};
    console.log('[auth local otp]', JSON.stringify(payload));
    return {ok: true, provider: 'local-dev', devOtp: otp};
  }

  if (!isLocalDeployment(env)) {
    return {ok: false, provider: null, reason: 'Production email provider not configured.'};
  }

  return {ok: true, provider: 'stub', devOtp: otp};
}
