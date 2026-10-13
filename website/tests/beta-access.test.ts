import {describe, expect, it, vi} from 'vitest';
import {
  BetaSubmissionError, initialBetaApplication, normalizeBetaApplication,
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
});
