// Server-side adapter only. No SDK dependency, configurable endpoint, logging or retries.
import {placeholder, validOrigin, validateDeployment} from '../deployment.js';

const ENDPOINT = 'https://api.resend.com/emails';
export const EMAIL_REQUEST_TIMEOUT_MS = 10000;
const MAX_RESPONSE_BYTES = 4096;
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

/** @typedef {{ok: boolean, provider: string|null, kind?: string, reason?: string, devOtp?: string}} EmailDeliveryResult */

export class EmailConfigurationError extends Error {
  constructor() { super('Email provider configuration is unavailable.'); }
}

function validSender(value, environment) {
  if (typeof value !== 'string' || value.length > 384 || value.trim() !== value
      || /[\r\n\x00-\x1f\x7f]/.test(value) || placeholder(value)) return false;
  let address = value;
  if (value.includes('<') || value.includes('>')) {
    const match = /^([^<>"\\,;]{1,80}) <([^<>]+)>$/.exec(value);
    if (!match || match[1].trim() !== match[1]) return false;
    address = match[2];
  }
  if (address.length > 254) return false;
  const match = /^([A-Za-z0-9][A-Za-z0-9._+\-]{0,63})@([A-Za-z0-9.\-]+)$/.exec(address);
  if (!match || match[1].includes('..') || match[1].endsWith('.')) return false;
  const host = match[2];
  if (!host.split('.').every((label) => /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$/.test(label))) return false;
  return validOrigin('https://' + host, environment);
}

// Returns only safe validation codes, never configuration values or credentials.
export function validateResendConfiguration(env) {
  if (!['staging', 'production'].includes(env.BETA_ENVIRONMENT)) return {ok: false, reason: 'invalid-email-environment'};
  if (env.AUTH_EMAIL_PROVIDER !== 'resend') return {ok: false, reason: 'email-provider-not-configured'};
  if (typeof env.RESEND_API_KEY !== 'string' || !/^re_[A-Za-z0-9_\-]{16,255}$/.test(env.RESEND_API_KEY)
      || /^re_x+$/i.test(env.RESEND_API_KEY) || placeholder(env.RESEND_API_KEY)) {
    return {ok: false, reason: 'invalid-email-api-key'};
  }
  if (!validSender(env.AUTH_EMAIL_FROM, env.BETA_ENVIRONMENT)) return {ok: false, reason: 'invalid-email-sender'};
  return {ok: true};
}

function failed(kind, reason) { return {ok: false, provider: 'resend', kind, reason}; }

async function acknowledgement(response) {
  if (response.headers.get('content-type')?.split(';', 1)[0].trim().toLowerCase() !== 'application/json') return false;
  const length = response.headers.get('content-length');
  if (length && (!/^\d+$/.test(length) || Number(length) > MAX_RESPONSE_BYTES)) return false;
  if (!response.body) return false;
  const reader = response.body.getReader();
  const parts = [];
  let total = 0;
  try {
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > MAX_RESPONSE_BYTES) { await reader.cancel(); return false; }
      parts.push(value);
    }
  } finally { reader.releaseLock(); }
  const raw = new Uint8Array(total);
  let offset = 0;
  for (const part of parts) { raw.set(part, offset); offset += part.byteLength; }
  const data = JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(raw));
  return data !== null && typeof data === 'object' && !Array.isArray(data)
    && Object.keys(data).length === 1 && typeof data.id === 'string' && uuid.test(data.id);
}

export class ResendEmailProvider {
  #apiKey;
  #from;
  #fetch;
  constructor(env, fetchImpl = fetch) {
    if (!validateDeployment(env).ok || !validateResendConfiguration(env).ok) throw new EmailConfigurationError();
    this.#apiKey = env.RESEND_API_KEY;
    this.#from = env.AUTH_EMAIL_FROM;
    this.#fetch = fetchImpl;
  }

  /** @returns {Promise<EmailDeliveryResult>} */
  async send({email, otp, purpose, expiryMinutes}) {
    if (typeof email !== 'string' || email.length > 254 || !/^[^\s@<>,;]+@[^\s@<>,;]+\.[^\s@<>,;]+$/.test(email)
        || typeof otp !== 'string' || !/^\d{6}$/.test(otp) || !['SIGNUP', 'LOGIN'].includes(purpose)
        || !Number.isInteger(expiryMinutes) || expiryMinutes <= 0) {
      return failed('delivery', 'invalid-email-message');
    }
    const controller = new AbortController();
    let timer;
    const timeout = new Promise((resolve) => {
      timer = setTimeout(() => {
        controller.abort();
        resolve(failed('delivery', 'email-request-timeout'));
      }, EMAIL_REQUEST_TIMEOUT_MS);
    });
    const attempt = async () => {
      try {
        const response = await this.#fetch(ENDPOINT, {method: 'POST', redirect: 'error', signal: controller.signal,
          headers: {'Authorization': 'Bearer ' + this.#apiKey, 'Content-Type': 'application/json',
            'Accept': 'application/json', 'User-Agent': 'QuantumStudio-Auth/0.2'},
          body: JSON.stringify({from: this.#from, to: [email], subject: 'Quantum Studio verification code',
            text: `Your Quantum Studio verification code is: ${otp}\n\nThis code expires in ${expiryMinutes} minutes.\nIf you did not request this code, you can ignore this email.`}),
        });
        if (response.status === 401 || response.status === 403) return failed('configuration', 'email-provider-configuration-rejected');
        if (!response.ok) return failed('delivery', 'email-provider-rejected');
        try {
          if (!await acknowledgement(response)) return failed('delivery', 'invalid-email-provider-response');
        } catch { return failed('delivery', 'invalid-email-provider-response'); }
        return {ok: true, provider: 'resend'};
      } catch {
        return failed('delivery', controller.signal.aborted ? 'email-request-timeout' : 'email-transport-failed');
      }
    };
    try { return await Promise.race([attempt(), timeout]); }
    finally { clearTimeout(timer); controller.abort(); }
  }
}
