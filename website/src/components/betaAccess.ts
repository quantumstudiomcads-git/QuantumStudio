export type BetaApplication = {
  fullName: string;
  email: string;
  institution: string;
  country: string;
  researchArea: string;
  operatingSystem: string;
  academicRole: string;
  evaluationDescription: string;
  privacyAccepted: boolean;
  termsAccepted: boolean;
  communicationsAccepted: boolean;
};

export type BetaFieldName = keyof Pick<BetaApplication,
  'fullName' | 'email' | 'institution' | 'country' | 'researchArea' |
  'operatingSystem' | 'academicRole' | 'evaluationDescription'>;

export const betaFieldLimits: Record<BetaFieldName, number> = {
  fullName: 120,
  email: 254,
  institution: 160,
  country: 100,
  researchArea: 1500,
  operatingSystem: 32,
  academicRole: 120,
  evaluationDescription: 2000,
};

export const betaOperatingSystems = ['Windows', 'Linux', 'Both', 'Other'] as const;

export const initialBetaApplication: BetaApplication = {
  fullName: '', email: '', institution: '', country: '', researchArea: '',
  operatingSystem: '', academicRole: '', evaluationDescription: '',
  privacyAccepted: false, termsAccepted: false, communicationsAccepted: false,
};

export function normalizeBetaText(value: string): string {
  return value.trim().replace(/\s+/g, ' ');
}

export function normalizeBetaApplication(application: BetaApplication): BetaApplication {
  return {
    ...application,
    fullName: normalizeBetaText(application.fullName),
    email: normalizeBetaText(application.email).toLowerCase(),
    institution: normalizeBetaText(application.institution),
    country: normalizeBetaText(application.country),
    researchArea: normalizeBetaText(application.researchArea),
    operatingSystem: normalizeBetaText(application.operatingSystem),
    academicRole: normalizeBetaText(application.academicRole),
    evaluationDescription: normalizeBetaText(application.evaluationDescription),
  };
}

export function validateBetaApplication(application: BetaApplication): Record<string, string> {
  const errors: Record<string, string> = {};
  const normalized = normalizeBetaApplication(application);
  (['fullName', 'email', 'institution', 'country', 'researchArea', 'operatingSystem'] as BetaFieldName[])
    .forEach((field) => {
      if (!normalized[field]) errors[field] = 'This field is required.';
    });
  if (normalized.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalized.email)) {
    errors.email = 'Enter a valid email address.';
  }
  (Object.keys(betaFieldLimits) as BetaFieldName[]).forEach((field) => {
    if (normalized[field].length > betaFieldLimits[field]) {
      errors[field] = `Use ${betaFieldLimits[field]} characters or fewer.`;
    }
  });
  if (normalized.operatingSystem && !betaOperatingSystems.includes(normalized.operatingSystem as typeof betaOperatingSystems[number])) {
    errors.operatingSystem = 'Select a supported operating system choice.';
  }
  if (!normalized.privacyAccepted) errors.privacyAccepted = 'Privacy-notice acceptance is required.';
  if (!normalized.termsAccepted) errors.termsAccepted = 'Beta-terms acceptance is required.';
  return errors;
}

export class BetaSubmissionError extends Error {
  constructor(public readonly code: string, message: string) {
    super(message);
    this.name = 'BetaSubmissionError';
  }
}

export type BetaSubmissionResult = {accepted: true; applicationId: string | null; message: string};
type FetchLike = typeof fetch;

export async function submitBetaApplication(
  application: BetaApplication,
  turnstileToken: string,
  fetchImpl: FetchLike = fetch,
): Promise<BetaSubmissionResult> {
  const response = await fetchImpl('/api/beta/applications', {
    method: 'POST',
    credentials: 'same-origin',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({...normalizeBetaApplication(application), turnstileToken}),
  });
  let payload: unknown;
  try { payload = await response.json(); } catch { throw new BetaSubmissionError('invalid_response', 'The registration service returned an invalid response.'); }
  if (!response.ok) {
    const message = typeof payload === 'object' && payload && 'error' in payload &&
      typeof payload.error === 'object' && payload.error && 'message' in payload.error &&
      typeof payload.error.message === 'string' ? payload.error.message : 'Unable to submit the application. Please try again later.';
    const code = typeof payload === 'object' && payload && 'error' in payload &&
      typeof payload.error === 'object' && payload.error && 'code' in payload.error &&
      typeof payload.error.code === 'string' ? payload.error.code : 'request_failed';
    throw new BetaSubmissionError(code, message);
  }
  if (!payload || typeof payload !== 'object' || !('accepted' in payload) || payload.accepted !== true ||
    !('message' in payload) || typeof payload.message !== 'string' ||
    !('applicationId' in payload) || (payload.applicationId !== null && typeof payload.applicationId !== 'string')) {
    throw new BetaSubmissionError('invalid_response', 'The registration service returned an invalid response.');
  }
  return payload as BetaSubmissionResult;
}
