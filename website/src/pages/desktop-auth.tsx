import Layout from '@theme/Layout';
import React, {useEffect, useState} from 'react';
import {authPageHref} from '../lib/auth-client';
import {confirmDesktopChallenge, loadDesktopChallenge, DesktopConfirmationError, type DesktopChallengeSummary} from '../lib/desktop-auth';

export default function DesktopAuthPage(): React.ReactNode {
  const [challenge, setChallenge] = useState('');
  const [summary, setSummary] = useState<DesktopChallengeSummary | null>(null);
  const [message, setMessage] = useState('Loading desktop activation?');
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [failed, setFailed] = useState(false);
  function showError(error: unknown) {
    if (error instanceof DesktopConfirmationError && error.status === 401) {
      window.location.assign(authPageHref('/login', `${window.location.pathname}${window.location.search}`));
      return;
    }
    setFailed(true);
    setMessage(error instanceof DesktopConfirmationError ? error.message : 'Desktop activation is unavailable. Start again in Quantum Studio.');
  }
  useEffect(() => {
    let active = true;
    const id = new URLSearchParams(window.location.search).get('challenge') || '';
    setChallenge(id);
    void loadDesktopChallenge(id).then((data) => {
      if (active) { setSummary(data); setMessage('Confirm only if you started Sign in / Activate in Quantum Studio on this device.'); }
    }).catch((error: unknown) => { if (active) showError(error); });
    return () => { active = false; };
  }, []);
  async function confirm() {
    setBusy(true);
    try {
      await confirmDesktopChallenge(challenge);
      setDone(true);
      setMessage('Confirmation complete. Return to Quantum Studio to see the device activation result.');
    } catch (error) { showError(error); }
    finally { setBusy(false); }
  }
  return <Layout title="Activate Quantum Studio" description="Confirm your desktop device activation">
    <main className="qs-page"><section className="qs-section"><div className="container"><div className="qs-auth-card">
      <h1>Activate Quantum Studio</h1><p role="status">{message}</p>
      {summary && !done && !failed && <>
        <p>Use your currently signed-in account to register this desktop device.</p>
        <dl><dt>Device</dt><dd><code>{summary.installation_id}</code></dd>
          <dt>Platform</dt><dd>{summary.platform}</dd><dt>Version</dt><dd>{summary.app_version}</dd></dl>
        <button className="qs-button" type="button" disabled={busy} onClick={() => void confirm()}>
          {busy ? 'Confirming?' : 'Confirm desktop activation'}
        </button>
      </>}
    </div></div></section></main>
  </Layout>;
}
