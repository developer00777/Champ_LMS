import type { Handle } from '@sveltejs/kit';
import { blockedResponse, clientIp, ipAllowlistEnabled, isAllowedIp, isExemptPath } from '$lib/server/ip-allowlist';

// In the combined container, FastAPI runs internally on this port and is
// never exposed directly — the SvelteKit Node server is the only process
// bound to Railway's public $PORT. This mirrors the /api proxy rewrite
// already used by vite.config.ts for local dev.
const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? 'http://127.0.0.1:8000';

// Connection-level headers belong to the client's hop, not ours. Node's fetch
// refuses some outright: forwarding `expect: 100-continue` (sent by curl and
// .NET clients on POSTs, never by browsers) fails the request with a 500.
const HOP_BY_HOP = ['host', 'connection', 'keep-alive', 'expect', 'transfer-encoding', 'upgrade', 'proxy-connection', 'te', 'trailer'];

export const handle: Handle = async ({ event, resolve }) => {
  if (event.url.pathname === '/healthz') {
    return new Response('ok', { headers: { 'cache-control': 'no-store' } });
  }

  if (ipAllowlistEnabled && !isExemptPath(event.url.pathname)) {
    const ip = clientIp(event.request.headers, () => event.getClientAddress());
    if (!isAllowedIp(ip)) {
      return blockedResponse(ip, event.url.pathname.startsWith('/api'));
    }
  }

  if (event.url.pathname.startsWith('/api')) {
    const target = new URL(event.url.pathname.replace(/^\/api/, '') + event.url.search, API_INTERNAL_URL);
    const headers = new Headers(event.request.headers);
    for (const h of HOP_BY_HOP) headers.delete(h);

    // Forward the body as a stream rather than buffering it. The video
    // server-relay fallback carries files up to 1GB; an arrayBuffer() here
    // would hold the whole upload in the Node process's heap at once.
    const hasBody = !['GET', 'HEAD'].includes(event.request.method);

    const res = await fetch(target, {
      method: event.request.method,
      headers,
      body: hasBody ? event.request.body : undefined,
      // @ts-expect-error - Node fetch requires duplex for streamed bodies
      duplex: 'half',
    });

    return new Response(res.body, { status: res.status, headers: res.headers });
  }

  return resolve(event);
};
