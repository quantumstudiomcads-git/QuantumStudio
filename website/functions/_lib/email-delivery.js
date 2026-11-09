import {validateDeployment, isLocalDeployment} from './deployment.js';
import {EmailConfigurationError, ResendEmailProvider, validateResendConfiguration} from './email/resend.js';

/** @typedef {{ok: boolean, provider: string|null, kind?: string, reason?: string, devOtp?: string}} EmailDeliveryResult */

// Providers implement send({email, otp, purpose, expiryMinutes}) -> EmailDeliveryResult.
// Local modes intentionally never make an external email request.
export function createEmailProvider(env, fetchImpl = fetch) {
  if (!validateDeployment(env).ok) throw new EmailConfigurationError();
  if (isLocalDeployment(env)) {
    const name = env.AUTH_EMAIL_TEST_MODE === 'true' ? 'local-dev' : 'stub';
    return {send: async ({otp}) => ({ok: true, provider: name, devOtp: otp})};
  }
  return new ResendEmailProvider(env, fetchImpl);
}

/** @returns {Promise<EmailDeliveryResult>} */
export async function sendOtpEmail({email, otp, purpose, expiryMinutes, env}, fetchImpl = fetch) {
  if (!validateDeployment(env).ok) {
    return {ok: false, provider: null, kind: 'configuration', reason: 'deployment-configuration-unavailable'};
  }
  if (!isLocalDeployment(env)) {
    const config = validateResendConfiguration(env);
    if (!config.ok) return {ok: false, provider: null, kind: 'configuration', reason: config.reason};
  }
  try {
    const provider = createEmailProvider(env, fetchImpl);
    return await provider.send({email, otp, purpose, expiryMinutes});
  } catch {
    // No raw provider exceptions, email addresses, OTPs, or credentials leave this boundary.
    return {ok: false, provider: null, kind: 'delivery', reason: 'email-delivery-unavailable'};
  }
}
