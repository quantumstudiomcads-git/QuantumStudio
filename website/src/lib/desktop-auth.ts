export type DesktopChallengeSummary = {
  state: 'pending'; installation_id: string; platform: string; app_version: string; expires_at: number;
};

type FetchLike = typeof fetch;
export class DesktopConfirmationError extends Error {
  constructor(public status: number) {
    super(status === 401 ? 'Sign in to confirm this device.' : status === 410
      ? 'This activation expired. Start again in Quantum Studio.'
      : status === 409 ? 'This activation was already completed or cancelled.'
        : 'Unable to confirm this device. Return to Quantum Studio and start again.');
  }
}

export async function loadDesktopChallenge(challenge: string, fetchImpl: FetchLike = fetch): Promise<DesktopChallengeSummary> {
  if (!/^[0-9a-f]{64}$/.test(challenge)) throw new DesktopConfirmationError(400);
  const response = await fetchImpl(`/api/desktop-auth/confirm?challenge=${encodeURIComponent(challenge)}`, {
    credentials: 'same-origin', cache: 'no-store',
  });
  if (!response.ok) throw new DesktopConfirmationError(response.status);
  const data = await response.json() as DesktopChallengeSummary;
  if (data.state !== 'pending' || !/^dev_[0-9a-f]{32}$/.test(data.installation_id)
      || !['windows', 'linux'].includes(data.platform) || typeof data.app_version !== 'string'
      || !Number.isInteger(data.expires_at)) throw new DesktopConfirmationError(502);
  return data;
}

export async function confirmDesktopChallenge(challenge: string, fetchImpl: FetchLike = fetch): Promise<void> {
  if (!/^[0-9a-f]{64}$/.test(challenge)) throw new DesktopConfirmationError(400);
  const response = await fetchImpl('/api/desktop-auth/confirm', {
    method: 'POST', credentials: 'same-origin', cache: 'no-store',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify({challenge_id: challenge}),
  });
  if (!response.ok) throw new DesktopConfirmationError(response.status);
  const data = await response.json() as {state?: string};
  if (data.state !== 'completed') throw new DesktopConfirmationError(502);
}
