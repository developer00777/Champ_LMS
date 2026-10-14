import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

const apiTarget = process.env.API_INTERNAL_URL ?? 'http://localhost:8000';

export default defineConfig({
  plugins: [sveltekit()],
  server: {
    proxy: {
      '/api': {
        // Same variable hooks.server.ts uses in production, so a dev box
        // with something else on :8000 can point the proxy elsewhere.
        target: apiTarget,
        // A remote target (e.g. the Railway deploy) routes on the Host header,
        // and its SvelteKit CSRF check 403s form POSTs (sign-in) whose Origin
        // isn't its own, so present both as the target's.
        // Origin is set via options rather than a proxyReq hook: for a POST the
        // body can flush the headers before that hook runs.
        changeOrigin: true,
        headers: { origin: new URL(apiTarget).origin },
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
});
