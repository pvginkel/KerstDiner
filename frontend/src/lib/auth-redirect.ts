/**
 * Shared authentication redirect utilities.
 * Used by both auth-context and API middleware for consistent 401 handling.
 */

declare module '@tanstack/react-router' {
  interface StaticDataRouteOption {
    /**
     * The route renders without a login: the AuthGate and the 401-to-login
     * redirect skip it. Set it with `staticData: { public: true }` on the
     * route's definition.
     */
    public?: boolean;
  }
}

let publicRouteCheck: () => boolean = () => false;

/**
 * Register how to tell whether the browser is on a public route. App.tsx
 * registers the router's check once it has created the router; until then no
 * route is public.
 */
export function registerPublicRouteCheck(check: () => boolean): void {
  publicRouteCheck = check;
}

/** Whether the route the browser is on carries `staticData: { public: true }`. */
export function isPublicRoute(): boolean {
  return publicRouteCheck();
}

/**
 * Build the login redirect URL with the current path preserved.
 * Encodes the current pathname and search params so the user can be
 * redirected back after authentication.
 */
export function buildLoginUrl(): string {
  const currentPath = window.location.pathname + window.location.search;
  const encodedRedirect = encodeURIComponent(currentPath);
  return `/api/auth/login?redirect=${encodedRedirect}`;
}
