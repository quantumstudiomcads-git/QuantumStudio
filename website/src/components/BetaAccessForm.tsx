import Link from '@docusaurus/Link';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import React, {useEffect, useRef, useState} from 'react';
import {
  BetaApplication, BetaFieldName, BetaSubmissionError, betaFieldLimits,
  initialBetaApplication, normalizeBetaApplication, submitBetaApplication,
  validateBetaApplication,
} from './betaAccess';

type TurnstileApi = {
  render: (container: HTMLElement, options: Record<string, unknown>) => string;
  reset: (widgetId?: string) => void;
};

declare global { interface Window { turnstile?: TurnstileApi; } }

const requiredFields = new Set<BetaFieldName>(['fullName', 'email', 'institution', 'country', 'researchArea', 'operatingSystem']);

export default function BetaAccessForm(): React.ReactNode {
  const {siteConfig} = useDocusaurusContext();
  const publicSettings = (siteConfig.customFields ?? {}) as {turnstileSiteKey?: string; turnstileTestMode?: boolean};
  const siteKey = publicSettings.turnstileSiteKey?.trim() ?? '';
  const testMode = publicSettings.turnstileTestMode === true;
  const turnstileContainer = useRef<HTMLDivElement>(null);
  const widgetId = useRef<string | undefined>(undefined);
  const submissionLock = useRef(false);
  const [application, setApplication] = useState<BetaApplication>(initialBetaApplication);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [turnstileToken, setTurnstileToken] = useState('');
  const [verificationMessage, setVerificationMessage] = useState('');
  const [notice, setNotice] = useState<{kind: 'success' | 'error'; text: string} | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const resetVerification = () => {
    setTurnstileToken('');
    if (!testMode && window.turnstile && widgetId.current) window.turnstile.reset(widgetId.current);
  };

  useEffect(() => {
    if (testMode || !siteKey || !turnstileContainer.current) return;
    const renderWidget = () => {
      if (!window.turnstile || !turnstileContainer.current || widgetId.current) return;
      widgetId.current = window.turnstile.render(turnstileContainer.current, {
        sitekey: siteKey,
        action: 'beta_registration',
        callback: (token: string) => { setTurnstileToken(token); setVerificationMessage(''); },
        'expired-callback': () => { setTurnstileToken(''); setVerificationMessage('Verification expired. Please complete it again.'); },
        'error-callback': () => { setTurnstileToken(''); setVerificationMessage('Verification could not load. Please try again later.'); },
      });
    };
    if (window.turnstile) { renderWidget(); return; }
    const script = document.createElement('script');
    script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
    script.async = true;
    script.defer = true;
    script.addEventListener('load', renderWidget, {once: true});
    script.addEventListener('error', () => setVerificationMessage('Verification could not load. Please try again later.'), {once: true});
    document.head.appendChild(script);
  }, [siteKey, testMode]);

  const setField = (field: keyof BetaApplication, value: string | boolean) => {
    setApplication((current) => ({...current, [field]: value}));
    setErrors((current) => ({...current, [field]: ''}));
  };

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (submitting || submissionLock.current) return;
    setNotice(null);
    const normalized = normalizeBetaApplication(application);
    const nextErrors = validateBetaApplication(normalized);
    if (!turnstileToken) nextErrors.turnstileToken = 'Complete the verification before submitting.';
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) return;
    submissionLock.current = true;
    setSubmitting(true);
    try {
      const result = await submitBetaApplication(normalized, turnstileToken);
      const identifier = result.applicationId ? ` Application ID: ${result.applicationId}.` : '';
      setNotice({kind: 'success', text: `${result.message}${identifier}`});
      setApplication(initialBetaApplication);
      resetVerification();
    } catch (error) {
      const message = error instanceof BetaSubmissionError ? error.message : 'A network error prevented submission. Check your connection and try again.';
      setNotice({kind: 'error', text: message});
      resetVerification();
    } finally { submissionLock.current = false; setSubmitting(false); }
  };

  const textField = (field: BetaFieldName, label: string, multiline = false) => {
    const required = requiredFields.has(field);
    const error = errors[field];
    const id = `beta-${field}`;
    return <label className={multiline ? 'qs-form__full' : ''} htmlFor={id}>{label}{required ? ' *' : ''}
      {multiline
        ? <textarea id={id} value={application[field]} maxLength={betaFieldLimits[field]} onChange={(event) => setField(field, event.target.value)} aria-invalid={Boolean(error)} aria-describedby={error ? `${id}-error` : undefined} />
        : <input id={id} type={field === 'email' ? 'email' : 'text'} value={application[field]} maxLength={betaFieldLimits[field]} onChange={(event) => setField(field, event.target.value)} aria-invalid={Boolean(error)} aria-describedby={error ? `${id}-error` : undefined} />}
      {error && <span className="qs-error" id={`${id}-error`}>{error}</span>}
    </label>;
  };

  const unavailable = !testMode && !siteKey;
  return <form className="qs-form" onSubmit={submit} noValidate>
    {textField('fullName', 'Full name')}{textField('email', 'Email address')}{textField('institution', 'Institution or organization')}{textField('country', 'Country')}
    {textField('researchArea', 'Research area or intended use', true)}
    <label htmlFor="beta-operating-system">Operating system *<select id="beta-operating-system" value={application.operatingSystem} onChange={(event) => setField('operatingSystem', event.target.value)} aria-invalid={Boolean(errors.operatingSystem)} aria-describedby={errors.operatingSystem ? 'beta-operating-system-error' : undefined}><option value="">Select an operating system</option><option value="Windows">Windows</option><option value="Linux">Linux</option><option value="Both">Windows and Linux</option><option value="Other">Other</option></select>{errors.operatingSystem && <span className="qs-error" id="beta-operating-system-error">{errors.operatingSystem}</span>}</label>
    {textField('academicRole', 'Academic role (optional)')}{textField('evaluationDescription', 'Short evaluation description (optional)', true)}
    <label className="qs-check qs-form__full"><input type="checkbox" checked={application.privacyAccepted} onChange={(event) => setField('privacyAccepted', event.target.checked)} aria-invalid={Boolean(errors.privacyAccepted)} /> <span>I have read and accept the <Link to="/privacy">Privacy Notice</Link>. *</span>{errors.privacyAccepted && <span className="qs-error">{errors.privacyAccepted}</span>}</label>
    <label className="qs-check qs-form__full"><input type="checkbox" checked={application.termsAccepted} onChange={(event) => setField('termsAccepted', event.target.checked)} aria-invalid={Boolean(errors.termsAccepted)} /> <span>I have read and accept the <Link to="/beta-terms">Beta Terms</Link>. *</span>{errors.termsAccepted && <span className="qs-error">{errors.termsAccepted}</span>}</label>
    <label className="qs-check qs-form__full"><input type="checkbox" checked={application.communicationsAccepted} onChange={(event) => setField('communicationsAccepted', event.target.checked)} /> <span>I consent to optional beta and update communications. This is not required for review.</span></label>
    <div className="qs-form__full"><strong>Abuse protection *</strong>
      {testMode ? <label htmlFor="beta-turnstile-test">Local test verification token<input id="beta-turnstile-test" type="text" value={turnstileToken} onChange={(event) => setTurnstileToken(event.target.value)} aria-invalid={Boolean(errors.turnstileToken)} aria-describedby="beta-turnstile-help" /><span id="beta-turnstile-help">Local development only: enter <code>test-pass</code>. This adapter is disabled in production.</span></label> : <div ref={turnstileContainer} className="qs-turnstile" aria-live="polite" />}
      {unavailable && <div className="qs-unavailable" role="status">Registration is not configured in this preview. A public Turnstile site key is required before applications can be submitted.</div>}
      {verificationMessage && <span className="qs-error" role="alert">{verificationMessage}</span>}
      {errors.turnstileToken && <span className="qs-error" role="alert">{errors.turnstileToken}</span>}
    </div>
    <p className="qs-form__full qs-form__hint">Approval is manual. A successful application does not issue a licence; any approved beta licence is temporary.</p>
    {notice && <div className={`qs-form__full qs-notice qs-notice--${notice.kind}`} role={notice.kind === 'error' ? 'alert' : 'status'}>{notice.text}</div>}
    <div className="qs-form__full"><button className="qs-button qs-button--primary" type="submit" disabled={submitting || unavailable}>{submitting ? 'Submitting application…' : 'Submit beta application'}</button></div>
  </form>;
}
