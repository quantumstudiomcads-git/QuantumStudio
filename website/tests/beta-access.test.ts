import {describe, expect, it, vi} from 'vitest';
import {
  BetaStatusError, BetaSubmissionError, betaStatusPresentation, compactApplicationId,
  fetchMyBetaActivations, initialBetaApplication, normalizeBetaApplication,
  submitBetaApplication, validateBetaApplication,
} from '../src/components/betaAccess';

const application = {...initialBetaApplication, fullName: '  Ada  Example ', email: ' ADA@EXAMPLE.TEST ', institution: 'Example Institute', country: 'Exampleland', researchArea: 'Materials', operatingSystem: 'Linux', privacyAccepted: true, termsAccepted: true};

describe('beta form adapter', () => {
  it('normalizes fields and permits optional communications consent', () => {
    const normalized = normalizeBetaApplication(application); expect(normalized.fullName).toBe('Ada Example'); expect(normalized.email).toBe('ada@example.test'); expect(validateBetaApplication(normalized)).toEqual({});
  });
  it('returns a typed success without persisting browser data', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({accepted: true, applicationId: '00000000-0000-4000-8000-000000000000', message: 'Queued.'}), {status: 202, headers: {'Content-Type': 'application/json'}}));
    await expect(submitBetaApplication(application, 'token', fetchMock)).resolves.toMatchObject({accepted: true, applicationId: '00000000-0000-4000-8000-000000000000'});
    expect(fetchMock).toHaveBeenCalledOnce(); expect(fetchMock.mock.calls[0][0]).toBe('/api/beta/applications');
  });
  it('returns typed and network failures to the form', async () => {
    const rejected = vi.fn().mockResolvedValue(new Response(JSON.stringify({error: {code: 'verification_failed', message: 'Try again.'}}), {status: 400, headers: {'Content-Type': 'application/json'}}));
    await expect(submitBetaApplication(application, 'token', rejected)).rejects.toMatchObject({name: 'BetaSubmissionError', code: 'verification_failed'});
    await expect(submitBetaApplication(application, 'token', vi.fn().mockRejectedValue(new Error('offline')))).rejects.toThrow('offline');
    expect(BetaSubmissionError).toBeTypeOf('function');
  });

  it.each([
    ['APPLIED', 'Application submitted', 'Your beta application has been submitted and is awaiting review.'],
    ['UNDER_REVIEW', 'Under review', 'Your application is currently being reviewed. No further action is required.'],
    ['APPROVED', 'Approved', 'Your beta application has been approved. A licence may still need to be issued before software access is available.'],
    ['REJECTED', 'Not approved', 'Your application was not approved for the current beta.'],
  ] as const)('maps %s to the user-facing status card copy', (status, label, description) => {
    expect(betaStatusPresentation(status).label).toBe(label);
    expect(betaStatusPresentation(status).description).toBe(description);
  });

  it('keeps every workflow status mapped to public-facing copy', () => {
    expect(betaStatusPresentation('LICENSE_ISSUED').label).toBe('Beta access active');
    expect(betaStatusPresentation('EXPIRED').label).toBe('Beta access expired');
    expect(betaStatusPresentation('REVOKED').label).toBe('Beta access revoked');
    expect(compactApplicationId('12345678-1234-4123-8123-123456789abc')).toBe('12345678');
  });

  it('loads only the current user activation summary from the authenticated endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      activations: [{
        activation_request_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        installation_id: 'dev_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        platform: 'linux',
        architecture: 'x86_64',
        app_version: '0.1.0',
        status: 'AUTHORIZED',
        created_at: '2026-10-01T00:00:00.000Z',
        authorized_at: '2026-10-01T00:00:00.000Z',
      }],
    }), {status: 200}));
    await expect(fetchMyBetaActivations(fetchMock)).resolves.toMatchObject([
      {status: 'AUTHORIZED', platform: 'linux'},
    ]);
    expect(fetchMock).toHaveBeenCalledWith('/api/beta/activation', {
      credentials: 'same-origin',
      cache: 'no-store',
    });
  });

  it('rejects malformed activation summaries and unauthenticated access', async () => {
    await expect(fetchMyBetaActivations(vi.fn().mockResolvedValue(
      new Response(JSON.stringify({activations: [{status: 'AUTHORIZED', user_id: 'other-user'}]}), {status: 200}),
    ))).rejects.toBeInstanceOf(BetaStatusError);
    await expect(fetchMyBetaActivations(vi.fn().mockResolvedValue(
      new Response('{}', {status: 401}),
    ))).rejects.toMatchObject({status: 401});
  });
});
