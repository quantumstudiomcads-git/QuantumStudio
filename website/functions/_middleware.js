import {getValidatedSessionFromRequest, authRuntimeValidation} from './_lib/auth.js';

const PROTECTED_PATHS = ['/beta-access', '/account', '/desktop-auth'];
const PUBLIC_PATHS = [
  '/', '/login', '/signup', '/privacy', '/beta-terms', '/capabilities', '/applications', '/documentation',
  '/contact', '/technical-preview', '/resources', '/calculations', '/temporary-licence',
];

function isPublicAsset(pathname) {
  return pathname.startsWith('/_') || pathname.startsWith('/assets/') || pathname.startsWith('/img/') || pathname.startsWith('/css/') || pathname.startsWith('/js/') || pathname.startsWith('/fonts/') || pathname.startsWith('/docs');
}

function isProtectedPath(pathname) {
  return PROTECTED_PATHS.some((protectedPath) => pathname === protectedPath || pathname.startsWith(`${protectedPath}/`));
}

function isPublicPath(pathname) {
  return PUBLIC_PATHS.includes(pathname) || pathname.startsWith('/docs') || pathname.startsWith('/api/') || isPublicAsset(pathname);
}

export async function onRequest(context) {
  const {request, env, next} = context;
  const url = new URL(request.url);
  const pathname = url.pathname.replace(/\/+$/, '') || '/';

  if (request.method === 'OPTIONS') {
    return next();
  }

  if (isPublicPath(pathname)) {
    return next();
  }

  if (isProtectedPath(pathname)) {
    if (!env.BETA_DB) {
      return Response.redirect(new URL('/login', url.origin), 302);
    }

    const runtime = authRuntimeValidation(env);
    if (!runtime.ok) {
      return Response.redirect(new URL('/login', url.origin), 302);
    }

    const session = await getValidatedSessionFromRequest(request, env);
    if (!session.ok) {
      const safePath = pathname.startsWith('/') && !pathname.startsWith('//') ? pathname + url.search : '/account';
      const redirectUrl = new URL('/login', url.origin);
      redirectUrl.searchParams.set('returnTo', safePath);
      return Response.redirect(redirectUrl.toString(), 302);
    }
  }

  if (pathname === '/desktop-auth') {
    const response = await next();
    const headers = new Headers(response.headers);
    headers.set('Cache-Control', 'no-store');
    headers.set('Referrer-Policy', 'no-referrer');
    headers.set('X-Frame-Options', 'DENY');
    headers.set('Content-Security-Policy', "frame-ancestors 'none'");
    return new Response(response.body, {status: response.status, headers});
  }
  return next();
}
