/**
 * Permissive CORS for the storefront-facing /api/* routes.
 *
 * These endpoints are called directly from the theme extension running
 * on the storefront ({shop}.myshopify.com), so we need to allow that
 * origin. We use `*` for the demo. In production you'd:
 *   (a) switch to Shopify App Proxy and remove CORS entirely, or
 *   (b) restrict Allow-Origin to known shop domains.
 */

export const CORS_HEADERS: Record<string, string> = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
  "Access-Control-Max-Age": "86400",
};

export function withCors(init: ResponseInit = {}): ResponseInit {
  return {
    ...init,
    headers: { ...CORS_HEADERS, ...(init.headers || {}) },
  };
}

export function corsPreflight(): Response {
  return new Response(null, { status: 204, headers: CORS_HEADERS });
}
