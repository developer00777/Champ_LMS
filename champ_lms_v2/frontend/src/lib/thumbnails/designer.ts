// Text thumbnails, drawn on a 1280x720 canvas in the browser.
//
// The studio's preview is this canvas, and saving uploads its pixels, so what
// the admin sees is exactly what learners get. Every template takes the same
// design (title, kicker, palette, font) and an optional background image, so
// switching templates never loses what was typed.

import type { ThumbnailDesign, ThumbnailSource } from '$lib/api/client';

// A thumbnail made in the studio before its episode exists; the page saves it
// with api.saveThumbnail once it has an id to save it under.
export interface PickedThumbnail {
  blob: Blob; url: string; source: ThumbnailSource; design: ThumbnailDesign | null;
}

export const W = 1280;
export const H = 720;

export type TemplateId = 'aurora' | 'editorial' | 'split' | 'poster' | 'grid' | 'overlay';
export type FontId = 'grotesk' | 'serif' | 'condensed' | 'sans';

export interface Palette {
  id: string; name: string;
  bg: [string, string]; // background, from and to
  ink: string;          // title
  soft: string;         // kicker and fine lines
  accent: string;       // bars, glows, monogram panel
  accent2: string;      // second glow
}

export const PALETTES: Palette[] = [
  { id: 'ember', name: 'Ember', bg: ['#14070a', '#4a0c16'], ink: '#fff4ee', soft: '#f3b8a8', accent: '#ff4d3d', accent2: '#ff9a3c' },
  { id: 'midnight', name: 'Midnight', bg: ['#070b1f', '#1a2766'], ink: '#eef2ff', soft: '#a9b8ff', accent: '#5aa9ff', accent2: '#9b6bff' },
  { id: 'grape', name: 'Grape', bg: ['#140a24', '#46195f'], ink: '#fdf3ff', soft: '#e0b3f2', accent: '#ff7ac8', accent2: '#7d5cff' },
  { id: 'ocean', name: 'Ocean', bg: ['#03202d', '#0b5a68'], ink: '#ecfdff', soft: '#9fe3ea', accent: '#ffd166', accent2: '#2ad1c4' },
  { id: 'forest', name: 'Forest', bg: ['#08160f', '#1c4632'], ink: '#f1f8ec', soft: '#b7d9a8', accent: '#c4f25c', accent2: '#2fbf84' },
  { id: 'graphite', name: 'Graphite', bg: ['#0c0c0f', '#26262e'], ink: '#f6f6f8', soft: '#a3a3b2', accent: '#e50914', accent2: '#5b5b6e' },
  { id: 'sand', name: 'Sand', bg: ['#f5eee2', '#e6d7bf'], ink: '#1f1a14', soft: '#7a6650', accent: '#d9480f', accent2: '#f2a541' },
  { id: 'paper', name: 'Paper', bg: ['#f7f7f4', '#e8e8e2'], ink: '#111114', soft: '#6b6b74', accent: '#e50914', accent2: '#3d5afe' },
];

export const TEMPLATES: { id: TemplateId; name: string }[] = [
  { id: 'aurora', name: 'Aurora' },
  { id: 'editorial', name: 'Editorial' },
  { id: 'split', name: 'Split' },
  { id: 'poster', name: 'Poster' },
  { id: 'grid', name: 'Grid' },
  { id: 'overlay', name: 'Photo' },
];

// `scale` evens out how big each face looks at the same pixel size: the
// condensed face is so narrow that it needs to be set larger to carry.
interface FontSpec { name: string; family: string; weight: number; lineHeight: number; upper?: boolean; scale?: number }
export const FONTS: Record<FontId, FontSpec> = {
  grotesk: { name: 'Grotesk', family: '"Space Grotesk", "Segoe UI", system-ui, sans-serif', weight: 700, lineHeight: 1.04 },
  sans: { name: 'Sans', family: '"Inter", "Segoe UI", system-ui, sans-serif', weight: 800, lineHeight: 1.05 },
  serif: { name: 'Serif', family: '"Fraunces", Georgia, "Times New Roman", serif', weight: 700, lineHeight: 1.06 },
  condensed: { name: 'Condensed', family: '"Bebas Neue", Impact, "Arial Narrow", sans-serif', weight: 400, lineHeight: 0.92, upper: true, scale: 1.4 },
};
const KICKER = '"Inter", "Segoe UI", system-ui, sans-serif';
const MONO = '"JetBrains Mono", ui-monospace, Consolas, monospace';

const FONT_CSS = 'https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Fraunces:opsz,wght@9..144,700'
  + '&family=Inter:wght@700;800&family=JetBrains+Mono:wght@500&family=Space+Grotesk:wght@700&display=swap';

let fontsReady: Promise<void> | null = null;

// Canvas text only uses a web font once it has loaded, so the studio waits
// for these (briefly: offline, the fallbacks in each stack are used).
export function ensureFonts(): Promise<void> {
  if (fontsReady) return fontsReady;
  fontsReady = (async () => {
    if (typeof document === 'undefined') return;
    if (!document.querySelector('link[data-thumb-fonts]')) {
      const link = document.createElement('link');
      link.rel = 'stylesheet'; link.href = FONT_CSS; link.dataset.thumbFonts = '';
      document.head.appendChild(link);
      await new Promise(r => { link.onload = r; link.onerror = r; setTimeout(r, 2500); });
    }
    const loads = [
      ...Object.values(FONTS).map(f => `${f.weight} 64px ${f.family}`),
      `700 24px ${KICKER}`, `500 24px ${MONO}`,
    ].map(spec => document.fonts.load(spec).catch(() => []));
    await Promise.race([Promise.all(loads), new Promise(r => setTimeout(r, 3000))]);
  })();
  return fontsReady;
}

export function paletteOf(id: string): Palette {
  return PALETTES.find(p => p.id === id) ?? PALETTES[0];
}
function fontOf(id: string): FontSpec {
  return FONTS[id as FontId] ?? FONTS.grotesk;
}

// A starting design that differs from course to course, so two courses
// opened for the first time don't get identical thumbnails.
export function defaultDesign(title: string, kicker: string): ThumbnailDesign {
  let h = 0;
  for (const ch of title) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  const dark = PALETTES.filter(p => !isLight(p));
  return { template: 'aurora', palette: dark[h % dark.length].id, font: 'grotesk', title, kicker };
}

export function shuffleDesign(d: ThumbnailDesign, withImage: boolean): ThumbnailDesign {
  const pick = <T>(xs: T[], not?: T) => {
    const pool = xs.length > 1 ? xs.filter(x => x !== not) : xs;
    return pool[Math.floor(Math.random() * pool.length)];
  };
  const templates = TEMPLATES.map(t => t.id).filter(t => withImage || t !== 'overlay');
  return {
    ...d,
    template: pick(templates, d.template as TemplateId),
    palette: pick(PALETTES.map(p => p.id), d.palette),
    font: pick(Object.keys(FONTS), d.font),
  };
}

export function isLight(p: Palette): boolean {
  const n = parseInt(p.bg[0].slice(1), 16);
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  return 0.299 * r + 0.587 * g + 0.114 * b > 150;
}

// ---- drawing helpers ------------------------------------------------------
type Ctx = CanvasRenderingContext2D;

function rgba(hex: string, a: number): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
}

function glow(ctx: Ctx, x: number, y: number, r: number, color: string, a: number) {
  const g = ctx.createRadialGradient(x, y, 0, x, y, r);
  g.addColorStop(0, rgba(color, a));
  g.addColorStop(1, rgba(color, 0));
  ctx.fillStyle = g;
  ctx.fillRect(x - r, y - r, r * 2, r * 2);
}

function wash(ctx: Ctx, p: Palette, angle: 'diag' | 'down' = 'diag') {
  const g = angle === 'diag' ? ctx.createLinearGradient(0, 0, W, H) : ctx.createLinearGradient(0, 0, 0, H);
  g.addColorStop(0, p.bg[0]);
  g.addColorStop(1, p.bg[1]);
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, W, H);
}

let noise: HTMLCanvasElement | null = null;
// Film grain over flat gradients, so they don't band and look less digital.
function grain(ctx: Ctx, amount = 0.07) {
  if (!noise) {
    noise = document.createElement('canvas');
    noise.width = noise.height = 160;
    const n = noise.getContext('2d')!;
    const img = n.createImageData(160, 160);
    for (let i = 0; i < img.data.length; i += 4) {
      const v = Math.random() * 255;
      img.data[i] = img.data[i + 1] = img.data[i + 2] = v;
      img.data[i + 3] = 255;
    }
    n.putImageData(img, 0, 0);
  }
  ctx.save();
  ctx.globalAlpha = amount;
  ctx.globalCompositeOperation = 'overlay';
  ctx.fillStyle = ctx.createPattern(noise, 'repeat')!;
  ctx.fillRect(0, 0, W, H);
  ctx.restore();
}

function spacing(ctx: Ctx, px: number) {
  if ('letterSpacing' in ctx) (ctx as Ctx & { letterSpacing: string }).letterSpacing = `${px}px`;
}

function kicker(ctx: Ctx, text: string, x: number, y: number, color: string, family = KICKER, weight = 700) {
  if (!text.trim()) return;
  ctx.save();
  ctx.font = `${weight} 25px ${family}`;
  spacing(ctx, 5);
  ctx.fillStyle = color;
  ctx.textBaseline = 'alphabetic';
  ctx.fillText(text.trim().toUpperCase().slice(0, 48), x, y);
  ctx.restore();
}

interface Fitted { size: number; lines: string[]; lineHeight: number }

// The largest size at which the text wraps into maxLines within maxWidth.
// Explicit line breaks in the title are kept. At the smallest size, the last
// line is cut short with an ellipsis rather than overflowing.
function fit(ctx: Ctx, raw: string, f: FontSpec, maxWidth: number, maxLines: number, max: number, min: number): Fitted {
  const text = (f.upper ? raw.toUpperCase() : raw).trim() || ' ';
  max = Math.round(max * (f.scale ?? 1));
  min = Math.round(min * (f.scale ?? 1));
  const wrap = (size: number) => {
    ctx.font = `${f.weight} ${size}px ${f.family}`;
    const lines: string[] = [];
    for (const para of text.split(/\n+/)) {
      let line = '';
      for (const word of para.split(/\s+/).filter(Boolean)) {
        const next = line ? `${line} ${word}` : word;
        if (line && ctx.measureText(next).width > maxWidth) { lines.push(line); line = word; }
        else line = next;
      }
      if (line) lines.push(line);
    }
    return lines;
  };
  for (let size = max; size >= min; size -= 2) {
    const lines = wrap(size);
    if (lines.length <= maxLines && lines.every(l => ctx.measureText(l).width <= maxWidth)) {
      return { size, lines, lineHeight: size * f.lineHeight };
    }
  }
  const lines = wrap(min).slice(0, maxLines);
  let last = lines[lines.length - 1] ?? '';
  while (last.length > 1 && ctx.measureText(`${last}…`).width > maxWidth) last = last.slice(0, -1);
  lines[lines.length - 1] = `${last.trimEnd()}…`;
  return { size: min, lines, lineHeight: min * f.lineHeight };
}

// Draws fitted lines. `y` is the top of the first line's capitals.
function lines(ctx: Ctx, t: Fitted, f: FontSpec, x: number, y: number, color: string | ((i: number) => string)) {
  ctx.save();
  ctx.font = `${f.weight} ${t.size}px ${f.family}`;
  ctx.textBaseline = 'alphabetic';
  t.lines.forEach((l, i) => {
    ctx.fillStyle = typeof color === 'string' ? color : color(i);
    ctx.fillText(l, x, y + t.size * 0.78 + i * t.lineHeight);
  });
  ctx.restore();
}
const blockHeight = (t: Fitted) => t.size * 0.78 + (t.lines.length - 1) * t.lineHeight + t.size * 0.08;

function roundRect(ctx: Ctx, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function cover(ctx: Ctx, img: CanvasImageSource & { width: number; height: number }) {
  const s = Math.max(W / img.width, H / img.height);
  const w = img.width * s, h = img.height * s;
  ctx.drawImage(img, (W - w) / 2, (H - h) / 2, w, h);
}

// ---- templates --------------------------------------------------------------
type Img = (CanvasImageSource & { width: number; height: number }) | null;

function aurora(ctx: Ctx, d: ThumbnailDesign, p: Palette, f: FontSpec) {
  wash(ctx, p);
  glow(ctx, W * 0.84, H * 0.16, 560, p.accent, 0.62);
  glow(ctx, W * 0.98, H * 0.92, 420, p.accent2, 0.42);
  glow(ctx, W * 0.04, -40, 380, p.accent2, 0.22);
  grain(ctx);
  kicker(ctx, d.kicker, 88, 112, p.soft);
  const t = fit(ctx, d.title, f, W * 0.74, 3, 128, 50);
  const top = H - 92 - blockHeight(t);
  ctx.fillStyle = p.accent;
  roundRect(ctx, 88, top - 44, 72, 9, 4.5); ctx.fill();
  lines(ctx, t, f, 88, top, p.ink);
}

function editorial(ctx: Ctx, d: ThumbnailDesign, p: Palette, f: FontSpec) {
  wash(ctx, p, 'down');
  ctx.fillStyle = p.accent;
  ctx.beginPath(); ctx.arc(W + 30, H * 0.66, 330, 0, Math.PI * 2); ctx.fill();
  ctx.strokeStyle = rgba(p.ink, 0.28); ctx.lineWidth = 3;
  ctx.beginPath(); ctx.arc(W * 0.79, H * 0.27, 112, 0, Math.PI * 2); ctx.stroke();
  ctx.strokeStyle = rgba(p.ink, 0.16); ctx.lineWidth = 2;
  ctx.strokeRect(40, 40, W - 80, H - 80);
  grain(ctx, 0.05);
  kicker(ctx, d.kicker, 96, 132, p.soft, MONO, 500);
  if (d.kicker.trim()) {
    ctx.save(); ctx.font = `500 25px ${MONO}`; spacing(ctx, 5);
    const w = ctx.measureText(d.kicker.trim().toUpperCase().slice(0, 48)).width; ctx.restore();
    ctx.fillStyle = rgba(p.ink, 0.3); ctx.fillRect(96 + w + 22, 123, 90, 2);
  }
  const t = fit(ctx, d.title, f, W * 0.6, 3, 116, 50);
  lines(ctx, t, f, 96, H * 0.56 - blockHeight(t) / 2, p.ink);
  ctx.fillStyle = p.accent; ctx.fillRect(96, H - 118, 120, 7);
}

function split(ctx: Ctx, d: ThumbnailDesign, p: Palette, f: FontSpec) {
  wash(ctx, p);
  const pw = Math.round(W * 0.38);
  const g = ctx.createLinearGradient(0, 0, pw, H);
  g.addColorStop(0, p.accent); g.addColorStop(1, p.accent2);
  ctx.fillStyle = g; ctx.fillRect(0, 0, pw, H);
  glow(ctx, pw * 0.2, H * 0.1, 360, '#ffffff', 0.18);
  const mono = (d.title.match(/[\p{L}\p{N}]/u)?.[0] ?? '•').toUpperCase();
  ctx.save();
  ctx.font = `${f.weight} 440px ${f.family}`;
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillStyle = rgba(p.bg[0], 0.88);
  ctx.fillText(mono, pw / 2, H / 2 + (f.upper ? 30 : 10));
  ctx.restore();
  ctx.strokeStyle = rgba(p.bg[0], 0.35); ctx.lineWidth = 3;
  ctx.beginPath(); ctx.arc(pw - 30, H - 70, 70, 0, Math.PI * 2); ctx.stroke();
  grain(ctx, 0.06);
  const x = pw + 72;
  const t = fit(ctx, d.title, f, W - x - 84, 4, 104, 44);
  const top = H / 2 - blockHeight(t) / 2 + (d.kicker.trim() ? 24 : 0);
  kicker(ctx, d.kicker, x, top - 40, p.accent);
  lines(ctx, t, f, x, top, p.ink);
}

function poster(ctx: Ctx, d: ThumbnailDesign, p: Palette, f: FontSpec) {
  wash(ctx, p, 'down');
  glow(ctx, W * 0.9, H * 0.05, 520, p.accent2, 0.35);
  grain(ctx, 0.08);
  ctx.fillStyle = p.accent;
  ctx.beginPath(); ctx.arc(100, 103, 9, 0, Math.PI * 2); ctx.fill();
  kicker(ctx, d.kicker, 124, 112, p.soft);
  ctx.fillStyle = rgba(p.ink, 0.25); ctx.fillRect(W - 88 - 160, 102, 160, 2);
  // Poster type always shouts: the condensed face fits far more per line.
  const pf = { ...f, upper: true, lineHeight: Math.min(f.lineHeight, 0.98) };
  const t = fit(ctx, d.title, pf, W - 176, 3, 168, 64);
  lines(ctx, t, pf, 88, H - 78 - blockHeight(t), i => (i === t.lines.length - 1 && t.lines.length > 1 ? p.accent : p.ink));
}

function grid(ctx: Ctx, d: ThumbnailDesign, p: Palette, f: FontSpec) {
  ctx.fillStyle = p.bg[0]; ctx.fillRect(0, 0, W, H);
  glow(ctx, W * 0.82, H * 0.45, 640, p.bg[1], 1);
  ctx.strokeStyle = rgba(p.ink, 0.06); ctx.lineWidth = 1;
  ctx.beginPath();
  for (let x = 48; x < W; x += 48) { ctx.moveTo(x + 0.5, 0); ctx.lineTo(x + 0.5, H); }
  for (let y = 48; y < H; y += 48) { ctx.moveTo(0, y + 0.5); ctx.lineTo(W, y + 0.5); }
  ctx.stroke();
  const cx = W * 0.86, cy = H * 0.4;
  glow(ctx, cx, cy, 250, p.accent, 0.95);
  [150, 230, 310].forEach((r, i) => {
    ctx.strokeStyle = rgba(p.accent, 0.38 - i * 0.12); ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke();
  });
  grain(ctx, 0.05);
  if (d.kicker.trim()) kicker(ctx, `// ${d.kicker.trim()}`, 88, 116, p.accent, MONO, 500);
  const t = fit(ctx, d.title, f, W * 0.54, 3, 110, 46);
  lines(ctx, t, f, 88, H - 104 - blockHeight(t), p.ink);
}

function overlay(ctx: Ctx, d: ThumbnailDesign, p: Palette, f: FontSpec, img: Img) {
  if (img) cover(ctx, img);
  else { wash(ctx, p); glow(ctx, W * 0.8, H * 0.3, 560, p.accent, 0.5); }
  const g = ctx.createLinearGradient(0, 0, W, 0);
  g.addColorStop(0, rgba(p.bg[0], 0.95));
  g.addColorStop(0.36, rgba(p.bg[0], 0.78));
  g.addColorStop(0.78, rgba(p.bg[0], 0));
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  const v = ctx.createLinearGradient(0, H * 0.55, 0, H);
  v.addColorStop(0, rgba(p.bg[0], 0)); v.addColorStop(1, rgba(p.bg[0], 0.55));
  ctx.fillStyle = v; ctx.fillRect(0, 0, W, H);
  kicker(ctx, d.kicker, 88, 112, p.soft);
  const t = fit(ctx, d.title, f, W * 0.56, 3, 104, 48);
  const top = H - 96 - blockHeight(t);
  ctx.fillStyle = p.accent;
  roundRect(ctx, 88, top - 42, 64, 8, 4); ctx.fill();
  lines(ctx, t, f, 88, top, p.ink);
}

export function drawThumbnail(ctx: Ctx, d: ThumbnailDesign, img: Img = null) {
  const p = paletteOf(d.palette);
  const f = fontOf(d.font);
  ctx.save();
  ctx.clearRect(0, 0, W, H);
  switch (d.template as TemplateId) {
    case 'editorial': editorial(ctx, d, p, f); break;
    case 'split': split(ctx, d, p, f); break;
    case 'poster': poster(ctx, d, p, f); break;
    case 'grid': grid(ctx, d, p, f); break;
    case 'overlay': overlay(ctx, d, p, f, img); break;
    default: aurora(ctx, d, p, f);
  }
  ctx.restore();
}

// Draws any image into a 16:9 frame, cropped from the centre, the same way
// the server crops it, so a preview never promises a framing it won't keep.
export function coverInto(ctx: Ctx, img: Img) {
  ctx.fillStyle = '#0a0a0f'; ctx.fillRect(0, 0, W, H);
  if (img) cover(ctx, img);
}

export function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error('That image could not be opened.'));
    img.src = src;
  });
}

export function canvasBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) =>
    canvas.toBlob(b => (b ? resolve(b) : reject(new Error('Could not export the image.'))), 'image/png'));
}
