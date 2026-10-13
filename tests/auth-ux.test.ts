import {readFileSync} from 'node:fs';
import {describe, expect, it, vi} from 'vitest';
import {authPageHref, betaAccessDestination, googleAuthHref, logout, resolvePostAuthDestination, resolveSafeReturnTo} from '../src/lib/auth-client';

vi.mock('../functions/_lib/auth.js', () => ({
  authRuntimeValidation: () => ({ok: true}),
  getValidatedSessionFromRequest: async () => ({ok: false}),
}));

import {onRequest} from '../functions/_middleware.js';

describe('standalone authentication navigation', () => {
  it('renders only one logged-out Sign in link to /login, without forms or overlays', () => {
    const controlsSource = readFileSync(new URL('../src/components/NavbarAuthControls.tsx', import.meta.url), 'utf8');
    expect(controlsSource.match(/href=\{loginHref\}/g)).toHaveLength(1);
    expect(controlsSource).toContain("useBaseUrl('/login')");
    expect(controlsSource.match(/Sign in/g)).toHaveLength(1);
    expect(controlsSource).not.toContain('Create account');
    expect(controlsSource).not.toContain('<form');
    expect(controlsSource).not.toContain('dialog');
    expect(controlsSource).not.toContain('backdrop');
  });

  it('keeps forms and modal UI out of NavbarContent while reading server auth state', () => {
    const navbarSource = readFileSync(new URL('../src/theme/Navbar/Content/index.tsx', import.meta.url), 'utf8');
    const authPagesSource = readFileSync(new URL('../src/components/AuthPages.tsx', import.meta.url), 'utf8');
    expect(navbarSource).toContain("fetch('/api/auth/session'");
    expect(navbarSource).toContain('<NavbarAuthControls');
    expect(navbarSource).not.toContain('AuthModal');
    expect(navbarSource).not.toContain('<form');
    expect(navbarSource).not.toContain('createPortal');
    expect(navbarSource).toContain('await logout()');
    expect(navbarSource).toContain('window.location.assign(homeUrl)');
    expect(navbarSource).toContain("useBaseUrl('/')");
    expect(authPagesSource).not.toContain('AuthModal');
    expect(authPagesSource).not.toContain('qs-auth-modal');
  });

  it('shows Beta Access and a profile menu, without permanent Account or Sign out controls', () => {
    const controlsSource = readFileSync(new URL('../src/components/NavbarAuthControls.tsx', import.meta.url), 'utf8');
    expect(controlsSource).toContain('if (!authenticated)');
    expect(controlsSource).toContain('className="navbar__auth-beta-action"');
    expect(controlsSource).toContain('className="navbar__profile-button"');
    expect(controlsSource).toContain('aria-haspopup="menu"');
    expect(controlsSource).toContain('aria-expanded={menuOpen}');
    expect(controlsSource).toContain('role="menu"');
    expect(controlsSource).toContain('role="menuitem" href={accountHref}');
    expect(controlsSource).toContain('role="menuitem" type="button" onClick={onSignOut}>Sign out</button>');
    expect(controlsSource).toContain('href={loginHref}');
    expect(controlsSource).toContain('user?.fullName');
    expect(controlsSource).toContain('user?.email');
    expect(controlsSource).toContain("event.key === 'Escape'");
    expect(controlsSource).toContain("event.key === 'ArrowDown'");
    expect(controlsSource).toContain("event.key === 'ArrowUp'");
    expect(controlsSource).toContain("event.key === 'Home'");
    expect(controlsSource).toContain("event.key === 'End'");
    expect(controlsSource).toContain("document.addEventListener('pointerdown', closeOnOutsideClick)");
    expect(controlsSource).toContain('closeMenu(true)');
  });

  it('links Create account and Sign in between the standalone pages with safe returnTo preserved', () => {
    const authPagesSource = readFileSync(new URL('../src/components/AuthPages.tsx', import.meta.url), 'utf8');
    expect(authPageHref('/signup', '/beta-access')).toBe('/signup?returnTo=%2Fbeta-access');
    expect(authPageHref('/login', '/beta-access')).toBe('/login?returnTo=%2Fbeta-access');
    expect(authPageHref('/signup', null)).toBe('/signup');
    expect(authPageHref('/login', null)).toBe('/login');
    expect(authPagesSource).toContain("authPageHref('/signup', returnTo)");
    expect(authPagesSource).toContain("authPageHref('/login', returnTo)");
    expect(authPagesSource).toContain("window.location.assign(resolveSafeReturnTo(data.redirectTo || returnTo || '/'))");
  });

  it('sends logged-out beta requests through login and authenticated requests to beta access', () => {
    const professorPagesSource = readFileSync(new URL('../src/components/ProfessorPages.tsx', import.meta.url), 'utf8');
    expect(betaAccessDestination(false)).toBe('/login?returnTo=%2Fbeta-access');
    expect(betaAccessDestination(true)).toBe('/beta-access');
    expect(betaAccessDestination(false, '/QuantumStudio-Website/')).toBe('/QuantumStudio-Website/login?returnTo=%2Fbeta-access');
    expect(betaAccessDestination(true, '/QuantumStudio-Website/')).toBe('/QuantumStudio-Website/beta-access');
    expect(professorPagesSource).toContain('getAuthSession()');
    expect(professorPagesSource).toContain('betaAccessDestination(authenticated, baseUrl)');
  });

  it('uses the original safe returnTo after OTP login when the server provides no redirect', () => {
    const authPagesSource = readFileSync(new URL('../src/components/AuthPages.tsx', import.meta.url), 'utf8');
    expect(resolvePostAuthDestination(undefined, null)).toBe('/');
    expect(resolvePostAuthDestination(undefined, '/beta-access')).toBe('/beta-access');
    expect(resolvePostAuthDestination(undefined, '/account')).toBe('/account');
    expect(resolvePostAuthDestination(undefined, 'https://evil.example')).toBe('/');
    expect(resolvePostAuthDestination('/', '/beta-access')).toBe('/beta-access');
    expect(resolvePostAuthDestination('/account', '/beta-access')).toBe('/account');
    expect(resolvePostAuthDestination('https://evil.example', '/beta-access')).toBe('/beta-access');
    expect(resolvePostAuthDestination(undefined, '/beta-access', '/QuantumStudio-Website/')).toBe('/QuantumStudio-Website/beta-access');
    expect(resolvePostAuthDestination(undefined, null, '/QuantumStudio-Website/')).toBe('/QuantumStudio-Website/');
    expect(authPagesSource).toContain('setReturnTo(readCurrentReturnTo())');
    expect(authPagesSource).toContain('const returnTo = useReturnToFromLocation()');
    expect(authPagesSource).toContain('resolvePostAuthDestination(data.redirectTo, currentReturnTo || retainedReturnTo, baseUrl)');
  });

  it('defaults Google login to home and preserves only a safe returnTo', () => {
    expect(googleAuthHref('/api/auth/google/start', null)).toBe('/api/auth/google/start?returnTo=%2F');
    expect(googleAuthHref('/api/auth/google/start', '/beta-access')).toBe('/api/auth/google/start?returnTo=%2Fbeta-access');
    expect(googleAuthHref('/api/auth/google/start', '//example.test')).toBe('/api/auth/google/start?returnTo=%2F');
  });

  it('preserves safe returnTo in both login and signup cross-links', () => {
    expect(authPageHref('/signup', '/beta-access')).toBe('/signup?returnTo=%2Fbeta-access');
    expect(authPageHref('/login', '/beta-access')).toBe('/login?returnTo=%2Fbeta-access');
    expect(authPageHref('/signup', '/account')).toBe('/signup?returnTo=%2Faccount');
    expect(authPageHref('/login', '/account')).toBe('/login?returnTo=%2Faccount');
    expect(authPageHref('/signup', 'https://evil.example')).toBe('/signup');
    expect(authPageHref('/login', 'https://evil.example')).toBe('/login');
  });

  it('posts logout to the existing endpoint and navigates home from the navbar', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ok: true}), {status: 200}));
    vi.stubGlobal('fetch', fetchMock);
    try {
      await logout();
      expect(fetchMock).toHaveBeenCalledWith('/api/auth/logout', expect.objectContaining({
        method: 'POST',
        credentials: 'same-origin',
      }));
    } finally {
      vi.unstubAllGlobals();
    }
    const navbarSource = readFileSync(new URL('../src/theme/Navbar/Content/index.tsx', import.meta.url), 'utf8');
    expect(navbarSource).toContain('window.location.assign(homeUrl)');
    expect(navbarSource).toContain('await logout()');
  });

  it('preserves the single logged-out navbar Sign in control', () => {
    const controlsSource = readFileSync(new URL('../src/components/NavbarAuthControls.tsx', import.meta.url), 'utf8');
    const unauthenticatedBranch = controlsSource.split('if (!authenticated)')[1]?.split('const closeMenu')[0] ?? '';
    expect(unauthenticatedBranch).toContain('Sign in');
    expect(unauthenticatedBranch).not.toContain('Create account');
    expect(unauthenticatedBranch).not.toContain('Account');
    expect(unauthenticatedBranch).not.toContain('Sign out');
  });

  it('opens the profile menu with focus and closes it on Escape or outside click', () => {
    const controlsSource = readFileSync(new URL('../src/components/NavbarAuthControls.tsx', import.meta.url), 'utf8');
    expect(controlsSource).toContain('onClick={() => setMenuOpen((open) => !open)}');
    expect(controlsSource).toContain("querySelector<HTMLElement>('[role=\"menuitem\"]')?.focus()");
    expect(controlsSource).toContain("document.addEventListener('pointerdown', closeOnOutsideClick)");
    expect(controlsSource).toContain("event.key === 'Escape'");
    expect(controlsSource).toContain('profileButtonRef.current?.focus()');
  });

  it('moves Account and Sign out into the profile menu', () => {
    const controlsSource = readFileSync(new URL('../src/components/NavbarAuthControls.tsx', import.meta.url), 'utf8');
    const menu = controlsSource.split('role="menu"')[1] ?? '';
    expect(controlsSource).toContain("const accountHref = useBaseUrl('/account')");
    expect(menu).toContain('href={accountHref} onClick={() => closeMenu()}>Account</a>');
    expect(menu).toContain('onClick={onSignOut}>Sign out</button>');
    expect(controlsSource).not.toContain('className="navbar__link" href={accountHref}');
    expect(controlsSource).not.toContain('className="navbar__auth-button" onClick={onSignOut}');
  });

  it('keeps the Google OAuth API untouched by carrying an explicit safe UI returnTo', () => {
    const authPagesSource = readFileSync(new URL('../src/components/AuthPages.tsx', import.meta.url), 'utf8');
    expect(authPagesSource).toContain('googleAuthHref(googleStartPath, returnTo)');
  });

  it('rejects unsafe destinations and defaults direct safe-return resolution to home', () => {
    expect(resolveSafeReturnTo('/beta-access')).toBe('/beta-access');
    expect(resolveSafeReturnTo('//example.test')).toBe('/');
    expect(resolveSafeReturnTo('https://example.test')).toBe('/');
    expect(resolveSafeReturnTo('/\\example.test')).toBe('/');
    expect(resolveSafeReturnTo(null)).toBe('/');
  });
});

describe('protected authentication routes', () => {
  it.each(['/beta-access', '/account'])('%s redirects unauthenticated requests to login with returnTo', async (path) => {
    const response = await onRequest({
      request: new Request(`https://quantumstudio.test${path}`),
      env: {BETA_DB: {}},
      next: async () => new Response('protected'),
    } as never);

    expect(response.status).toBe(302);
    expect(response.headers.get('Location')).toBe(`https://quantumstudio.test/login?returnTo=${encodeURIComponent(path)}`);
  });
});
