// Office-network gate. When IP_ALLOWLIST_ENABLED=true on the Railway service,
// every request from an address outside the allowlist gets a 403 before it
// reaches a page or the /api proxy. Unset or false, the gate is off.
//
// Env vars (Railway → service → Variables, redeploys on save):
//   IP_ALLOWLIST_ENABLED   true | false (default false)
//   IP_ALLOWLIST           optional override of ORG_ALLOWLIST below; comma or
//                          newline separated, each an IP, a CIDR (1.2.3.0/24)
//                          or a range (1.2.3.4-1.2.3.9)
//   IP_ALLOWLIST_XFF_DEPTH which X-Forwarded-For entry is the client, counted
//                          from the right (default 1: the one Railway's edge
//                          appended). Raise it only if another proxy such as
//                          Cloudflare sits in front of Railway.

const ORG_ALLOWLIST = `
  # TATA new ISP
  14.99.3.34-14.99.3.38
  14.99.4.34-14.99.4.38
  # Cloud ISP
  190.92.198.57, 49.0.205.220, 159.138.107.202, 119.8.170.37, 119.8.165.6,
  159.138.106.128, 114.119.172.181, 159.138.90.112, 94.74.82.243, 119.8.160.197
  # Airtel ISP JST
  182.72.210.5-182.72.210.6
  182.75.51.225-182.75.51.255
  # TATA ISP JST and TATA TDS (same blocks)
  103.170.162.0/24
  103.170.163.0/24
  # Airtel TDS
  182.78.39.1-182.78.39.255
`;

// Paths that must answer without an office IP: Railway's healthcheck, and the
// Bunny and Zoom webhooks, which carry their own signatures.
const EXEMPT_PREFIXES = ['/healthz', '/api/webhooks/', '/api/api/webhooks/', '/api/zoom/webhook'];

type Range = [number, number];

function ipv4ToInt(ip: string): number | null {
  const parts = ip.split('.');
  if (parts.length !== 4) return null;
  let n = 0;
  for (const p of parts) {
    if (!/^\d{1,3}$/.test(p) || Number(p) > 255) return null;
    n = n * 256 + Number(p);
  }
  return n;
}

function parseEntry(entry: string): Range | null {
  if (entry.includes('/')) {
    const [base, bitsStr] = entry.split('/');
    const start = ipv4ToInt(base);
    const bits = Number(bitsStr);
    if (start === null || !Number.isInteger(bits) || bits < 0 || bits > 32) return null;
    const size = 2 ** (32 - bits);
    const network = start - (start % size);
    return [network, network + size - 1];
  }
  if (entry.includes('-')) {
    const [a, b] = entry.split('-').map((s) => ipv4ToInt(s.trim()));
    if (a === null || b === null) return null;
    return a <= b ? [a, b] : [b, a];
  }
  const n = ipv4ToInt(entry);
  return n === null ? null : [n, n];
}

function parseList(raw: string): Range[] {
  const ranges: Range[] = [];
  for (const line of raw.split('\n')) {
    for (const entry of line.replace(/#.*/, '').split(',')) {
      const trimmed = entry.trim();
      if (!trimmed) continue;
      const range = parseEntry(trimmed);
      if (range) ranges.push(range);
      else console.warn(`[ip-allowlist] ignoring unparseable entry "${trimmed}"`);
    }
  }
  return ranges;
}

export const ipAllowlistEnabled = /^(1|true|yes|on)$/i.test(process.env.IP_ALLOWLIST_ENABLED?.trim() ?? '');

const ranges = parseList(process.env.IP_ALLOWLIST?.trim() || ORG_ALLOWLIST);
const xffDepth = Math.max(1, Number(process.env.IP_ALLOWLIST_XFF_DEPTH) || 1);

if (ipAllowlistEnabled) {
  console.log(`[ip-allowlist] enforcing, ${ranges.length} ranges, XFF depth ${xffDepth}`);
}

export function isExemptPath(pathname: string): boolean {
  return EXEMPT_PREFIXES.some((p) => pathname === p || pathname.startsWith(p));
}

// Railway's edge appends the connecting address to X-Forwarded-For, so the
// entry counted from the right is the one a client can't forge. With no
// header, fall back to the socket address (Railway's proxy, so it fails closed).
export function clientIp(headers: Headers, socketAddress: () => string): string {
  const xff = headers.get('x-forwarded-for');
  let ip = '';
  if (xff) {
    const hops = xff.split(',').map((s) => s.trim()).filter(Boolean);
    ip = hops[Math.max(0, hops.length - xffDepth)] ?? '';
  }
  if (!ip) {
    try {
      ip = socketAddress();
    } catch {
      ip = '';
    }
  }
  return ip.replace(/^::ffff:/i, '');
}

export function isAllowedIp(ip: string): boolean {
  const n = ipv4ToInt(ip);
  if (n === null) return false;
  return ranges.some(([lo, hi]) => n >= lo && n <= hi);
}

export function blockedResponse(ip: string, wantsJson: boolean): Response {
  const headers = { 'cache-control': 'no-store' };
  if (wantsJson) {
    return Response.json({ detail: 'Access is limited to the office network.', ip }, { status: 403, headers });
  }
  const safeIp = ip.replace(/[^0-9a-fA-F.:]/g, '') || 'unknown';
  const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Office network only</title>
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;font-family:system-ui,sans-serif;background:#f7f7f8;color:#1a1a1a}main{max-width:420px;padding:32px 24px;text-align:center}h1{font-size:20px;margin:0 0 8px}p{margin:0 0 6px;color:#555;line-height:1.5}code{background:#eee;padding:2px 6px;border-radius:4px}@media (prefers-color-scheme:dark){body{background:#111;color:#eee}p{color:#aaa}code{background:#222}}</style></head>
<body><main><h1>Office network only</h1><p>Champ LMS can only be opened from the organisation's network.</p><p>Your address: <code>${safeIp}</code></p></main></body></html>`;
  return new Response(html, { status: 403, headers: { ...headers, 'content-type': 'text/html; charset=utf-8' } });
}
