import {describe, expect, it, vi} from 'vitest';
import {loadDesktopChallenge, confirmDesktopChallenge} from '../src/lib/desktop-auth';
const challenge = 'a'.repeat(64);

describe('desktop confirmation browser adapter', () => {
  it('uses browser sessions only on the explicit website confirmation endpoints', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({state: 'pending', installation_id: `dev_${'a'.repeat(32)}`,
      platform: 'windows', app_version: '0.2.0', expires_at: 1800000000}), {status: 200}));
    await expect(loadDesktopChallenge(challenge, fetchMock)).resolves.toMatchObject({state: 'pending'});
    expect(fetchMock).toHaveBeenCalledWith(`/api/desktop-auth/confirm?challenge=${challenge}`, {credentials: 'same-origin', cache: 'no-store'});
    const confirm = vi.fn().mockResolvedValue(new Response('{"state":"completed"}', {status: 200}));
    await confirmDesktopChallenge(challenge, confirm);
    expect(confirm.mock.calls[0][1].body).toBe(JSON.stringify({challenge_id: challenge}));
    expect(confirm.mock.calls[0][1].credentials).toBe('same-origin');
  });
  it.each([401, 409, 410, 503])('provides safe %s errors and never echoes arbitrary server text', async (status) => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('sensitive-server-body', {status}));
    await expect(loadDesktopChallenge(challenge, fetchMock)).rejects.toMatchObject({status});
    await expect(confirmDesktopChallenge(challenge, fetchMock)).rejects.toMatchObject({status});
  });
  it('rejects malformed links without making a request', async () => {
    const fetchMock = vi.fn();
    await expect(loadDesktopChallenge('bad', fetchMock)).rejects.toMatchObject({status: 400});
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
