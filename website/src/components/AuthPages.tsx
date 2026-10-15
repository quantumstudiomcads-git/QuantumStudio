import Link from '@docusaurus/Link';
import Layout from '@theme/Layout';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import useBaseUrl from '@docusaurus/useBaseUrl';
import React, {useEffect, useRef, useState} from 'react';
import {authPageHref, getAuthSession, googleAuthHref, logout, resolvePostAuthDestination, resolveSafeReturnTo, type AuthUser} from '../lib/auth-client';
import {BetaAccountStatus} from './BetaApplicationStatus';

type Notice = {kind: 'success' | 'error'; text: string};

type TurnstileApi = {
  render: (container: HTMLElement, options: Record<string, unknown>) => string;
  reset: (widgetId?: string) => void;
};

declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}

function useTurnstileWidget(onToken: (token: string) => void, action: string) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const widgetId = useRef<string | undefined>(undefined);
  const {siteConfig} = useDocusaurusContext();
  const publicSettings = (siteConfig.customFields ?? {}) as {turnstileSiteKey?: string; turnstileTestMode?: boolean};
  const siteKey = publicSettings.turnstileSiteKey?.trim() ?? '';
  const testMode = publicSettings.turnstileTestMode === true;

  useEffect(() => {
    if (testMode || !siteKey || !containerRef.current) {
      return;
    }

    const renderWidget = () => {
      if (!window.turnstile || !containerRef.current || widgetId.current) {
        return;
      }
      widgetId.current = window.turnstile.render(containerRef.current, {
        sitekey: siteKey,
        action,
        callback: (token: string) => onToken(token),
        'expired-callback': () => onToken(''),
        'error-callback': () => onToken(''),
      });
    };

    if (window.turnstile) {
      renderWidget();
      return;
    }

    const script = document.createElement('script');
    script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
    script.async = true;
    script.defer = true;
    script.addEventListener('load', renderWidget, {once: true});
    document.head.appendChild(script);

    return () => {
      if (widgetId.current && window.turnstile) {
        window.turnstile.reset(widgetId.current);
      }
    };
  }, [action, onToken, siteKey, testMode]);

  return {containerRef, siteKey, testMode};
}

function AuthCard({children, title, subtitle}: {children: React.ReactNode; title: string; subtitle: string}) {
  return <Layout title={title} description={subtitle}><main className="qs-page"><section className="qs-intro"><div className="container qs-intro__layout"><span className="qs-kicker">Secure research access</span><h1>{title}</h1><p>{subtitle}</p></div></section><section className="qs-section"><div className="container"><div className="qs-auth-card">{children}</div></div></section></main></Layout>;
}

function TurnstileField({action, onToken, token, setToken}: {action: string; onToken: (v: string) => void; token: string; setToken: (value: string) => void}) {
  const {containerRef, testMode} = useTurnstileWidget(onToken, action);
  if (testMode) {
    return <label className="qs-form__full"><span>Verification</span><input type="text" value={token} onChange={(event) => setToken(event.target.value)} placeholder="Enter local Turnstile test token" /></label>;
  }

  return <div className="qs-form__full"><span>Verification</span><div ref={containerRef} className="qs-turnstile-wrap" /></div>;
}

function readCurrentReturnTo(): string | null {
  return typeof window === 'undefined' ? null : new URLSearchParams(window.location.search).get('returnTo');
}

function useReturnToFromLocation(): string | null {
  const [returnTo, setReturnTo] = useState<string | null>(null);

  useEffect(() => {
    setReturnTo(readCurrentReturnTo());
  }, []);

  return returnTo;
}

function GoogleAuthLink({returnTo}: {returnTo: string | null}) {
  const googleStartPath = useBaseUrl('/api/auth/google/start');
  const googleHref = googleAuthHref(googleStartPath, returnTo);
  return <a className="qs-button qs-button--secondary" href={googleHref}>G  Continue with Google</a>;
}

export function LoginPage(): React.ReactNode {
  const returnTo = useReturnToFromLocation();
  const baseUrl = useBaseUrl('/');
  const [email, setEmail] = useState('');
  const [otp, setOtp] = useState('');
  const [turnstileToken, setTurnstileToken] = useState('');
  const [step, setStep] = useState<'email' | 'otp'>('email');
  const [notice, setNotice] = useState<Notice | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [resending, setResending] = useState(false);

  const onEmailSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!email.trim()) {
      setNotice({kind: 'error', text: 'Enter your email address.'});
      return;
    }
    setSubmitting(true);
    setNotice(null);

    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {'Content-Type': 'application/json; charset=utf-8'},
        body: JSON.stringify({email, turnstileToken}),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.message || 'Unable to send verification code.');
      }
      setStep('otp');
      setNotice({kind: 'success', text: data.message || 'If an eligible account exists for this email, a verification code has been sent.'});
      if (data.devOtp) {
        setNotice({kind: 'success', text: `Local test mode: OTP ${data.devOtp}`});
      }
    } catch (error) {
      setNotice({kind: 'error', text: error instanceof Error ? error.message : 'Unable to request a code.'});
    } finally {
      setSubmitting(false);
    }
  };

  const onOtpSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!otp.trim()) {
      setNotice({kind: 'error', text: 'Enter the 6-digit verification code.'});
      return;
    }

    setSubmitting(true);
    setNotice(null);
    try {
      const response = await fetch('/api/auth/verify-otp', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {'Content-Type': 'application/json; charset=utf-8'},
        body: JSON.stringify({email, otp, purpose: 'LOGIN'}),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.message || 'The code is invalid or expired.');
      }
      const currentReturnTo = resolveSafeReturnTo(readCurrentReturnTo(), '');
      const retainedReturnTo = resolveSafeReturnTo(returnTo, '');
      const destination = resolvePostAuthDestination(data.redirectTo, currentReturnTo || retainedReturnTo, baseUrl);
      window.location.assign(destination);
    } catch (error) {
      setNotice({kind: 'error', text: error instanceof Error ? error.message : 'Authentication failed.'});
    } finally {
      setSubmitting(false);
    }
  };

  const onResend = async () => {
    setResending(true);
    setNotice(null);
    try {
      const response = await fetch('/api/auth/resend-otp', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {'Content-Type': 'application/json; charset=utf-8'},
        body: JSON.stringify({email, purpose: 'LOGIN', turnstileToken}),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.message || 'Unable to resend a code.');
      }
      setNotice({kind: 'success', text: data.devOtp ? `Local test mode: OTP ${data.devOtp}` : (data.message || 'A new code has been sent.')});
    } catch (error) {
      setNotice({kind: 'error', text: error instanceof Error ? error.message : 'Unable to resend a code.'});
    } finally {
      setResending(false);
    }
  };

  return <AuthCard title="Sign in" subtitle="Use your institutional email to receive a one-time verification code."><div className="qs-auth-form-wrap">{notice && <div className={`qs-alert qs-alert--${notice.kind}`}>{notice.text}</div>}<div className="qs-form"><GoogleAuthLink returnTo={returnTo} /></div><div className="qs-auth-meta"><span>OR</span></div>{step === 'email' ? <form className="qs-form" onSubmit={onEmailSubmit}> <label className="qs-form__full"><span>Email address</span><input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@institution.edu" required /></label> <TurnstileField action="auth_otp" onToken={setTurnstileToken} token={turnstileToken} setToken={setTurnstileToken} /> <button className="qs-button qs-button--primary" type="submit" disabled={submitting}>{submitting ? 'Sending…' : 'Send code'}</button> <div className="qs-auth-meta"><span>New to Quantum Studio?</span> <Link to={authPageHref('/signup', returnTo)}>Create account</Link></div></form> : <form className="qs-form" onSubmit={onOtpSubmit}> <label className="qs-form__full"><span>Verification code</span><input type="text" value={otp} onChange={(event) => setOtp(event.target.value.replace(/\D/g, '').slice(0, 6))} inputMode="numeric" maxLength={6} placeholder="123456" required /></label> <button className="qs-button qs-button--primary" type="submit" disabled={submitting}>{submitting ? 'Verifying…' : 'Continue'}</button><div className="qs-auth-actions"><button type="button" className="qs-button qs-button--secondary" onClick={onResend} disabled={resending}>{resending ? 'Sending…' : 'Resend code'}</button><button type="button" className="qs-button qs-button--link" onClick={() => {setStep('email'); setOtp(''); setNotice(null);}}>Change email</button></div></form>}</div></AuthCard>;
}

export function SignupPage(): React.ReactNode {
  const returnTo = useReturnToFromLocation();
  const baseUrl = useBaseUrl('/');
  const provider = typeof window === 'undefined' ? null : new URLSearchParams(window.location.search).get('provider');
  const [fullName, setFullName] = useState('');
  const [institution, setInstitution] = useState('');
  const [email, setEmail] = useState('');
  const [otp, setOtp] = useState('');
  const [turnstileToken, setTurnstileToken] = useState('');
  const [step, setStep] = useState<'signup' | 'otp'>('signup');
  const [notice, setNotice] = useState<Notice | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [resending, setResending] = useState(false);
  const [googleState, setGoogleState] = useState('');
  const [googleProfile, setGoogleProfile] = useState({name: '', email: ''});
  const [googleLoading, setGoogleLoading] = useState(false);
  const isGoogleFlow = provider === 'google' && !!googleState;

  useEffect(() => {
    if (provider !== 'google') {
      return;
    }

    const state = typeof window === 'undefined' ? null : new URLSearchParams(window.location.search).get('state');
    if (!state) {
      setNotice({kind: 'error', text: 'Google signup is unavailable.'});
      return;
    }

    setGoogleState(state);
    setGoogleLoading(true);
    fetch(`/api/auth/google/pending?state=${encodeURIComponent(state)}`, {credentials: 'same-origin'})
      .then(async (response) => {
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.message || 'Google signup is unavailable.');
        }
        setGoogleProfile({name: data.name || '', email: data.email || ''});
      })
      .catch((error) => {
        setNotice({kind: 'error', text: error instanceof Error ? error.message : 'Google signup is unavailable.'});
      })
      .finally(() => {
        setGoogleLoading(false);
      });
  }, [provider]);

  const onGoogleComplete = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!institution.trim()) {
      setNotice({kind: 'error', text: 'Enter your institution or organization.'});
      return;
    }

    setSubmitting(true);
    setNotice(null);
    try {
      const response = await fetch('/api/auth/google/complete', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {'Content-Type': 'application/json; charset=utf-8'},
        body: JSON.stringify({state: googleState, institution}),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.message || 'Unable to complete Google sign-up.');
      }
      window.location.assign(resolveSafeReturnTo(data.redirectTo || returnTo || '/'));
    } catch (error) {
      setNotice({kind: 'error', text: error instanceof Error ? error.message : 'Unable to complete Google sign-up.'});
    } finally {
      setSubmitting(false);
    }
  };

  const onSignupSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!fullName.trim() || !institution.trim() || !email.trim()) {
      setNotice({kind: 'error', text: 'Please complete the sign-up form.'});
      return;
    }

    setSubmitting(true);
    setNotice(null);
    try {
      const response = await fetch('/api/auth/signup', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {'Content-Type': 'application/json; charset=utf-8'},
        body: JSON.stringify({fullName, institution, email, turnstileToken}),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.message || 'Unable to create your account.');
      }
      setStep('otp');
      setNotice({kind: 'success', text: data.message || 'If an eligible account exists for this email, a verification code has been sent.'});
      if (data.devOtp) {
        setNotice({kind: 'success', text: `Local test mode: OTP ${data.devOtp}`});
      }
    } catch (error) {
      setNotice({kind: 'error', text: error instanceof Error ? error.message : 'Unable to create your account.'});
    } finally {
      setSubmitting(false);
    }
  };

  const onOtpSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!otp.trim()) {
      setNotice({kind: 'error', text: 'Enter the 6-digit verification code.'});
      return;
    }

    setSubmitting(true);
    setNotice(null);
    try {
      const response = await fetch('/api/auth/verify-otp', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {'Content-Type': 'application/json; charset=utf-8'},
        body: JSON.stringify({email, otp, purpose: 'SIGNUP'}),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.message || 'The code is invalid or expired.');
      }
      const currentReturnTo = resolveSafeReturnTo(readCurrentReturnTo(), '');
      const retainedReturnTo = resolveSafeReturnTo(returnTo, '');
      window.location.assign(resolvePostAuthDestination(data.redirectTo, currentReturnTo || retainedReturnTo, baseUrl));
    } catch (error) {
      setNotice({kind: 'error', text: error instanceof Error ? error.message : 'Authentication failed.'});
    } finally {
      setSubmitting(false);
    }
  };

  const onResend = async () => {
    setResending(true);
    setNotice(null);
    try {
      const response = await fetch('/api/auth/resend-otp', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {'Content-Type': 'application/json; charset=utf-8'},
        body: JSON.stringify({email, purpose: 'SIGNUP', turnstileToken}),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.message || 'Unable to resend a code.');
      }
      setNotice({kind: 'success', text: data.devOtp ? `Local test mode: OTP ${data.devOtp}` : (data.message || 'A new code has been sent.')});
    } catch (error) {
      setNotice({kind: 'error', text: error instanceof Error ? error.message : 'Unable to resend a code.'});
    } finally {
      setResending(false);
    }
  };

  if (isGoogleFlow) {
    return <AuthCard title="Create account" subtitle="Complete your Google account setup."><div className="qs-auth-form-wrap">{notice && <div className={`qs-alert qs-alert--${notice.kind}`}>{notice.text}</div>} {googleLoading ? <p>Preparing your Google profile…</p> : <form className="qs-form" onSubmit={onGoogleComplete}><label className="qs-form__full"><span>Verified Google email</span><input type="text" value={googleProfile.email} readOnly /></label><label className="qs-form__full"><span>Name</span><input type="text" value={googleProfile.name} readOnly /></label><label className="qs-form__full"><span>Institution or organization</span><input type="text" value={institution} onChange={(event) => setInstitution(event.target.value)} placeholder="Your institution or organization" required /></label><button className="qs-button qs-button--primary" type="submit" disabled={submitting}>{submitting ? 'Creating account…' : 'Complete account'}</button></form>}<div className="qs-auth-meta"><span>Already have an account?</span> <Link to={authPageHref('/login', returnTo)}>Sign in</Link></div></div></AuthCard>;
  }

  return <AuthCard title="Create account" subtitle="Create a verified researcher account for controlled Quantum Studio access."><div className="qs-auth-form-wrap">{notice && <div className={`qs-alert qs-alert--${notice.kind}`}>{notice.text}</div>}<div className="qs-form"><GoogleAuthLink returnTo={returnTo} /></div><div className="qs-auth-meta"><span>OR</span></div>{step === 'signup' ? <form className="qs-form" onSubmit={onSignupSubmit}><label className="qs-form__full"><span>Full name</span><input type="text" value={fullName} onChange={(event) => setFullName(event.target.value)} required /></label><label className="qs-form__full"><span>Institution or organization</span><input type="text" value={institution} onChange={(event) => setInstitution(event.target.value)} required /></label><label className="qs-form__full"><span>Email address</span><input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></label><TurnstileField action="auth_otp" onToken={setTurnstileToken} token={turnstileToken} setToken={setTurnstileToken} /><button className="qs-button qs-button--primary" type="submit" disabled={submitting}>{submitting ? 'Sending…' : 'Continue'}</button> <div className="qs-auth-meta"><span>Already have an account?</span> <Link to={authPageHref('/login', returnTo)}>Sign in</Link></div></form> : <form className="qs-form" onSubmit={onOtpSubmit}><label className="qs-form__full"><span>Verification code</span> <input type="text" value={otp} onChange={(event) => setOtp(event.target.value.replace(/\D/g, '').slice(0, 6))} inputMode="numeric" maxLength={6} placeholder="123456" required /></label><button className="qs-button qs-button--primary" type="submit" disabled={submitting}>{submitting ? 'Verifying…' : 'Continue'}</button><div className="qs-auth-actions"><button type="button" className="qs-button qs-button--secondary" onClick={onResend} disabled={resending}>{resending ? 'Sending…' : 'Resend code'}</button><button type="button" className="qs-button qs-button--link" onClick={() => {setStep('signup'); setOtp(''); setNotice(null);}}>Change details</button></div></form>}</div></AuthCard>;
}

export function AccountPage(): React.ReactNode {
  const [account, setAccount] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    getAuthSession().then((session) => {
      if (!active) {
        return;
      }
      setAccount(session.authenticated ? session.user ?? null : null);
      setLoading(false);
    }).catch(() => {
      if (active) {
        setAccount(null);
        setLoading(false);
      }
    });
    return () => {
      active = false;
    };
  }, []);

  const handleSignOut = async () => {
    await logout();
    window.location.assign('/');
  };

  return <Layout title="Account" description="Researcher account details and sign-out controls"><main className="qs-page"><section className="qs-intro"><div className="container qs-intro__layout"><span className="qs-kicker">Research account</span><h1>Account</h1><p>Manage your researcher authentication and access state.</p></div></section><section className="qs-section"><div className="container"><div className="qs-auth-card">{loading ? <p>Loading your account…</p> : !account ? <div><p>You are not signed in.</p><Link to="/login?returnTo=/account">Sign in</Link></div> : <div className="qs-account-details"><div className="qs-account-row"><span className="qs-account-label">Full name</span><strong>{account.fullName}</strong></div><div className="qs-account-row"><span className="qs-account-label">Institution</span><strong>{account.institution}</strong></div><div className="qs-account-row"><span className="qs-account-label">Email</span><strong>{account.email}</strong></div><div className="qs-account-row"><span className="qs-account-label">Account status</span><strong>{account.status}</strong></div><BetaAccountStatus /><button className="qs-button qs-button--secondary" type="button" onClick={handleSignOut}>Sign out</button></div>}</div></div></section></main></Layout>;
}
