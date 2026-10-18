import Link from '@docusaurus/Link';
import React, {useCallback, useEffect, useState} from 'react';
import BetaAccessForm from './BetaAccessForm';
import {
  BetaStatusError, betaStatusPresentation, compactApplicationId, fetchMyBetaActivations,
  fetchMyBetaApplication, type CurrentBetaActivation, type CurrentBetaApplication,
} from './betaAccess';

function submittedDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? 'Date unavailable'
    : new Intl.DateTimeFormat(undefined, {dateStyle: 'long'}).format(date);
}

export function BetaApplicationStatusCard(
  {application}: {application: CurrentBetaApplication},
): React.ReactNode {
  const presentation = betaStatusPresentation(application.status);
  return <article className="qs-note" aria-label="Beta application status">
    <h3>{presentation.label}</h3>
    <p>{presentation.description}</p>
    <dl className="qs-definition-list">
      <dt>Submitted</dt><dd><time dateTime={application.submitted_at}>{submittedDate(application.submitted_at)}</time></dd>
      <dt>Application ID</dt><dd><code>{compactApplicationId(application.application_id)}</code></dd>
    </dl>
  </article>;
}

function BetaActivationSummary(): React.ReactNode {
  const [activations, setActivations] = useState<CurrentBetaActivation[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void fetchMyBetaActivations()
      .then((result) => {
        if (active) setActivations(result);
      })
      .catch(() => {
        if (active) setError('Beta device status is temporarily unavailable.');
      });
    return () => { active = false; };
  }, []);

  return <section aria-labelledby="account-beta-devices-title">
    <h3 id="account-beta-devices-title">Beta devices</h3>
    <p>Device registration status does not mean that a software licence has been issued.</p>
    {error && <p role="status">{error}</p>}
    {!error && activations === null && <p role="status">Loading beta devices…</p>}
    {!error && activations !== null && activations.length === 0 && <p>No beta devices have been registered.</p>}
    {activations && activations.length > 0 && <ul>
      {activations.map((activation) => {
        const status = activation.status === 'AUTHORIZED'
          ? 'Device authorized'
          : activation.status === 'FLAGGED'
            ? 'Needs review'
            : 'Revoked';
        return <li key={activation.activation_request_id}>
          <code>{activation.installation_id.slice(0, 12)}</code>
          {' — '}{activation.platform} — {status}
        </li>;
      })}
    </ul>}
  </section>;
}

function BetaStatusContent(
  {showEmptyApplicationLink, showActivations = false}: {
    showEmptyApplicationLink: boolean;
    showActivations?: boolean;
  },
): React.ReactNode {
  const [application, setApplication] = useState<CurrentBetaApplication | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setApplication(await fetchMyBetaApplication());
    } catch (cause) {
      setError(cause instanceof BetaStatusError
        ? cause.message
        : 'Beta status is temporarily unavailable. Please try again later.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) return <p role="status">Loading your beta application…</p>;
  if (error) {
    return <div className="qs-note" role="alert">
      <p>{error}</p>
      {error.startsWith('Sign in') && <Link to={`/login?returnTo=${showEmptyApplicationLink ? '%2Faccount' : '%2Fbeta-access'}`}>Sign in</Link>}
      <button className="qs-button qs-button--secondary" type="button" onClick={() => void load()}>Try again</button>
    </div>;
  }
  if (application) return <>
    <BetaApplicationStatusCard application={application} />
    {showActivations && <BetaActivationSummary />}
  </>;
  if (showEmptyApplicationLink) {
    return <div className="qs-note"><p>You do not have a beta application yet.</p><Link to="/beta-access">Apply for beta access</Link></div>;
  }
  return <BetaAccessForm onSubmitted={() => { void load(); }} />;
}

export function BetaAccessApplicationPanel(): React.ReactNode {
  return <BetaStatusContent showEmptyApplicationLink={false} />;
}

export function BetaAccountStatus(): React.ReactNode {
  return <section aria-labelledby="account-beta-access-title">
    <h2 id="account-beta-access-title">Beta Access</h2>
    <BetaStatusContent showEmptyApplicationLink showActivations />
  </section>;
}
