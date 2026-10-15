import {describe, expect, it, vi} from 'vitest';
import {
  BetaSubmissionError, betaStatusPresentation, compactApplicationId, initialBetaApplication,
  normalizeBetaApplication, submitBetaApplication, validateBetaApplication,
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
});
