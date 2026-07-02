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

    const res = await fetch(target, {
      method: event.request.method,
      headers,
      body: ['GET', 'HEAD'].includes(event.request.method) ? undefined : await event.request.arrayBuffer(),
      // @ts-expect-error - Node fetch requires duplex for streamed bodies
      duplex: 'half',
    });

    return new Response(res.body, { status: res.status, headers: res.headers });
  }

  return resolve(event);
};
