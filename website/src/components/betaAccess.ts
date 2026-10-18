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

export const betaApplicationStatuses = [
  'APPLIED', 'UNDER_REVIEW', 'APPROVED', 'REJECTED',
  'LICENSE_ISSUED', 'EXPIRED', 'REVOKED',
] as const;

export type BetaApplicationStatus = typeof betaApplicationStatuses[number];

export type CurrentBetaApplication = {
  application_id: string;
  status: BetaApplicationStatus;
  submitted_at: string;
  updated_at: string;
};

export type BetaActivationStatus = 'AUTHORIZED' | 'FLAGGED' | 'REVOKED';

export type CurrentBetaActivation = {
  activation_request_id: string;
  installation_id: string;
  platform: 'windows' | 'linux';
  architecture: 'x86_64';
  app_version: string;
  status: BetaActivationStatus;
  created_at: string;
  authorized_at: string | null;
};

export class BetaStatusError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = 'BetaStatusError';
  }
}

export async function fetchMyBetaActivations(fetchImpl: FetchLike = fetch): Promise<CurrentBetaActivation[]> {
  const response = await fetchImpl('/api/beta/activation', {
    credentials: 'same-origin',
    cache: 'no-store',
  });
  if (!response.ok) {
    throw new BetaStatusError(
      response.status,
      response.status === 401
        ? 'Sign in to view your beta devices.'
        : 'Beta device status is temporarily unavailable. Please try again later.',
    );
  }
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new BetaStatusError(502, 'The beta device service returned an invalid response.');
  }
  if (
    typeof payload !== 'object'
    || payload === null
    || !('activations' in payload)
    || !Array.isArray(payload.activations)
  ) {
    throw new BetaStatusError(502, 'The beta device service returned an invalid response.');
  }
  return payload.activations.map((activation: unknown) => {
    const expectedFields = [
      'activation_request_id', 'installation_id', 'platform', 'architecture',
      'app_version', 'status', 'created_at', 'authorized_at',
    ];
    if (
      typeof activation !== 'object'
      || activation === null
      || Object.keys(activation).length !== expectedFields.length
      || expectedFields.some((field) => !(field in activation))
      || !('activation_request_id' in activation)
      || typeof activation.activation_request_id !== 'string'
      || !('installation_id' in activation)
      || typeof activation.installation_id !== 'string'
      || !('platform' in activation)
      || (activation.platform !== 'windows' && activation.platform !== 'linux')
      || !('architecture' in activation)
      || activation.architecture !== 'x86_64'
      || !('app_version' in activation)
      || typeof activation.app_version !== 'string'
      || !('status' in activation)
      || !['AUTHORIZED', 'FLAGGED', 'REVOKED'].includes(String(activation.status))
      || !('created_at' in activation)
      || typeof activation.created_at !== 'string'
      || !('authorized_at' in activation)
      || (activation.authorized_at !== null && typeof activation.authorized_at !== 'string')
    ) {
      throw new BetaStatusError(502, 'The beta device service returned an invalid response.');
    }
    return {
      activation_request_id: activation.activation_request_id,
      installation_id: activation.installation_id,
      platform: activation.platform,
      architecture: activation.architecture,
      app_version: activation.app_version,
      status: activation.status as BetaActivationStatus,
      created_at: activation.created_at,
      authorized_at: activation.authorized_at,
    };
  });
}

export function betaStatusPresentation(status: BetaApplicationStatus): {label: string; description: string} {
  switch (status) {
    case 'APPLIED':
      return {label: 'Application submitted', description: 'Your beta application has been submitted and is awaiting review.'};
    case 'UNDER_REVIEW':
      return {label: 'Under review', description: 'Your application is currently being reviewed. No further action is required.'};
    case 'APPROVED':
      return {label: 'Approved', description: 'Your beta application has been approved. A licence may still need to be issued before software access is available.'};
    case 'REJECTED':
      return {label: 'Not approved', description: 'Your application was not approved for the current beta.'};
    case 'LICENSE_ISSUED':
      return {label: 'Beta access active', description: 'A beta licence has been issued for your application.'};
    case 'EXPIRED':
      return {label: 'Beta access expired', description: 'The beta licence associated with your application has expired.'};
    case 'REVOKED':
      return {label: 'Beta access revoked', description: 'The beta licence associated with your application is no longer active.'};
  }
}

export function compactApplicationId(applicationId: string): string {
  return applicationId.slice(0, 8);
}

export async function fetchMyBetaApplication(fetchImpl: FetchLike = fetch): Promise<CurrentBetaApplication | null> {
  const response = await fetchImpl('/api/beta/me', {
    credentials: 'same-origin',
    cache: 'no-store',
  });
  if (!response.ok) {
    throw new BetaStatusError(
      response.status,
      response.status === 401
        ? 'Sign in to view your beta application.'
        : 'Beta status is temporarily unavailable. Please try again later.',
    );
  }
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new BetaStatusError(502, 'The beta status service returned an invalid response.');
  }
  if (typeof payload !== 'object' || payload === null || !('application' in payload)) {
    throw new BetaStatusError(502, 'The beta status service returned an invalid response.');
  }
  const {application} = payload;
  if (application === null) return null;
  if (
    typeof application !== 'object'
    || !('application_id' in application)
    || typeof application.application_id !== 'string'
    || !('status' in application)
    || typeof application.status !== 'string'
    || !betaApplicationStatuses.includes(application.status as BetaApplicationStatus)
    || !('submitted_at' in application)
    || typeof application.submitted_at !== 'string'
    || !('updated_at' in application)
    || typeof application.updated_at !== 'string'
  ) {
    throw new BetaStatusError(502, 'The beta status service returned an invalid response.');
  }
  return {
    application_id: application.application_id,
    status: application.status as BetaApplicationStatus,
    submitted_at: application.submitted_at,
    updated_at: application.updated_at,
  };
}

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
