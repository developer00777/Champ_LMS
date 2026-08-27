import type { Handle } from '@sveltejs/kit';

// In the combined container, FastAPI runs internally on this port and is
// never exposed directly — the SvelteKit Node server is the only process
// bound to Railway's public $PORT. This mirrors the /api proxy rewrite
// already used by vite.config.ts for local dev.
const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? 'http://127.0.0.1:8000';

export const handle: Handle = async ({ event, resolve }) => {
  if (event.url.pathname.startsWith('/api')) {
    const target = new URL(event.url.pathname.replace(/^\/api/, '') + event.url.search, API_INTERNAL_URL);
    const headers = new Headers(event.request.headers);
    headers.delete('host');

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
