export async function sendOtpEmail({email, otp, purpose, expiryMinutes, env}) {
  const localDevMode = env.AUTH_EMAIL_TEST_MODE === 'true' && env.BETA_ENVIRONMENT !== 'production';

  if (localDevMode) {
    const payload = {to: email, otp, purpose, expiresInMinutes: expiryMinutes, provider: 'local-dev'};
    console.log('[auth local otp]', JSON.stringify(payload));
    return {ok: true, provider: 'local-dev', devOtp: otp};
  }

  if (env.BETA_ENVIRONMENT === 'production') {
    return {ok: false, provider: null, reason: 'Production email provider not configured.'};
  }

  return {ok: true, provider: 'stub', devOtp: otp};
}
