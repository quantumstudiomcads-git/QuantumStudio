export type AuthUser = {
  userId: string;
  fullName: string;
  institution: string;
  email: string;
  status: string;
  emailVerifiedAt: string | null;
};

export type AuthSessionResponse = {
  authenticated: boolean;
  user?: AuthUser;
  reason?: string;
};

export function resolveSafeReturnTo(value: string | null | undefined, fallback = '/'): string {
  if (!value || !value.startsWith('/') || value.startsWith('//') || value.includes('\\')) {
    return fallback;
  }

  try {
    const target = new URL(value, 'https://quantumstudio.invalid');
    if (target.origin !== 'https://quantumstudio.invalid') {
      return fallback;
    }
    return `${target.pathname}${target.search}${target.hash}`;
  } catch {
    return fallback;
  }
}

export function authPageHref(path: '/login' | '/signup', returnTo: string | null): string {
  if (!returnTo) {
    return path;
  }
  const safeReturnTo = resolveSafeReturnTo(returnTo, '');
  return safeReturnTo ? `${path}?${new URLSearchParams({returnTo: safeReturnTo})}` : path;
}

export function googleAuthHref(googleStartPath: string, returnTo: string | null): string {
  const safeReturnTo = resolveSafeReturnTo(returnTo);
  return `${googleStartPath}?${new URLSearchParams({returnTo: safeReturnTo})}`;
}

export function resolvePostAuthDestination(redirectTo: string | null | undefined, returnTo: string | null | undefined, baseUrl = ''): string {
  const safeReturnTo = resolveSafeReturnTo(returnTo, '');
  const safeRedirectTo = resolveSafeReturnTo(redirectTo, '');
  const destination = safeRedirectTo && (safeRedirectTo !== '/' || !safeReturnTo)
    ? safeRedirectTo
    : safeReturnTo || safeRedirectTo || '/';
  const basePath = baseUrl.endsWith('/') ? baseUrl.slice(0, -1) : baseUrl;
  return `${basePath}${destination}`;
}

export function betaAccessDestination(authenticated: boolean, baseUrl = ''): string {
  const path = authenticated ? '/beta-access' : '/login?returnTo=%2Fbeta-access';
  const basePath = baseUrl.endsWith('/') ? baseUrl.slice(0, -1) : baseUrl;
  return `${basePath}${path}`;
}

export async function getAuthSession(): Promise<AuthSessionResponse> {
  const response = await fetch('/api/auth/session', {credentials: 'same-origin'});
  if (!response.ok) {
    return {authenticated: false};
  }
  return (await response.json()) as AuthSessionResponse;
}

export async function logout(): Promise<void> {
  await fetch('/api/auth/logout', {
    method: 'POST',
    credentials: 'same-origin',
    headers: {'Content-Type': 'application/json; charset=utf-8'},
  });
}
