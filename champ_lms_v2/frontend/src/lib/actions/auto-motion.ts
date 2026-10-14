/**
 * App-wide motion that needs no per-page markup:
 *  - staggered entrances for repeated items (cards, rows, list items, tiles),
 *    including content that arrives later from the API;
 *  - a click ripple on buttons;
 *  - 3D tilt for `use:tilt` surfaces.
 *
 * Everything runs through the Web Animations API, so no classes or styles
 * are written onto Svelte-owned nodes (except a `position` fix for ripple
 * hosts that are statically positioned). Opt out of entrances with
 * `data-no-motion` on any ancestor.
 */
import { motionReduced } from '$lib/stores/motion';

const EASE = 'cubic-bezier(0.16, 1, 0.3, 1)';
const MAX_STAGGER = 14;
const SKIP = '[data-no-motion], .ui-rise, .reveal-pending, .reveal-in, .ripple-clip, svg, video, canvas, iframe, script, style';

// The individual translate/scale properties, not `transform`: they stack on
// top of an element's own transform, so things centred with
// translate(-50%) (captions, notices) don't jump sideways while rising.
function rise(el: Element, delay: number) {
  (el as HTMLElement).animate(
    [
      { opacity: 0, translate: '0 14px', scale: '0.985' },
      { opacity: 1, translate: '0 0', scale: '1' },
    ],
    { duration: 520, delay, easing: EASE, fill: 'backwards' },
  );
}

/** Children that look like a repeated set: three or more of the same tag. */
function repeatedChildren(parent: Element): Element[] {
  const kids = Array.from(parent.children).filter((c) => !c.matches(SKIP));
  if (kids.length < 3) return [];
  const tag = kids[0].tagName;
  const same = kids.filter((k) => k.tagName === tag);
  return same.length / kids.length >= 0.7 ? same : [];
}

/** Stagger the repeated groups inside `root` (a few levels deep). Returns how many items moved. */
export function staggerIn(root: Element, baseDelay = 0): number {
  if (motionReduced() || root.closest('[data-no-motion]') || document.body.classList.contains('exam-locked')) return 0;
  let animated = 0;
  const walk = (el: Element, depth: number) => {
    if (animated > 60 || depth > 4 || el.matches(SKIP)) return;
    const group = repeatedChildren(el);
    if (group.length) {
      group.slice(0, MAX_STAGGER).forEach((k, i) => rise(k, baseDelay + i * 45));
      animated += Math.min(group.length, MAX_STAGGER);
      // Items of a group are animated as units; don't descend into them.
      return;
    }
    for (const c of Array.from(el.children)) walk(c, depth + 1);
  };
  walk(root, 0);
  return animated;
}

/**
 * Watch a container and give newly inserted content an entrance. Called once
 * from the root layout on <main>.
 */
export function autoMotion(node: HTMLElement) {
  const seen = new WeakSet<Node>();
  const mo = new MutationObserver((records) => {
    if (motionReduced()) return;
    const added: Element[] = [];
    for (const r of records) {
      r.addedNodes.forEach((n) => {
        if (n.nodeType === 1 && !seen.has(n)) { seen.add(n); added.push(n as Element); }
      });
    }
    // Only the outermost of a batch; nested ones are covered by it.
    const roots = added.filter((el) => !added.some((o) => o !== el && o.contains(el)));
    if (roots.length > 40) return; // a big re-render (filtering a long table): leave it be
    // Several siblings at once (a list filling in) stagger as a group.
    roots.forEach((el, i) => {
      if (el.matches(SKIP) || el.closest('[data-no-motion]') || !el.isConnected) return;
      if (document.body.classList.contains('exam-locked')) return;
      if (roots.length >= 3) rise(el, Math.min(i, MAX_STAGGER) * 40);
      // A block that arrived on its own: stagger what's inside it, or, if it
      // holds no repeated items, bring the block in as one piece.
      else if (staggerIn(el) === 0) rise(el, 0);
    });
  });
  mo.observe(node, { childList: true, subtree: true });
  return { destroy: () => mo.disconnect() };
}

/* ------------------------------------------------------------------ ripple */

const RIPPLE_HOSTS = 'button, .btn-primary, .btn-ghost, .btn, a.ui-round, [role="button"]';

/** One document-level listener; ink spreads from the pointer on press. */
export function installRipple() {
  const onDown = (e: PointerEvent) => {
    if (motionReduced() || e.button !== 0) return;
    const host = (e.target as Element)?.closest?.(RIPPLE_HOSTS) as HTMLElement | null;
    if (!host || host.hasAttribute('disabled') || host.closest('[data-no-ripple]')) return;
    const cs = getComputedStyle(host);
    if (cs.position === 'static') host.style.position = 'relative';

    const r = host.getBoundingClientRect();
    const size = Math.hypot(r.width, r.height) * 2;
    const clip = document.createElement('span');
    clip.className = 'ripple-clip';
    const ink = document.createElement('span');
    ink.className = 'ripple-ink';
    ink.style.width = ink.style.height = `${size}px`;
    ink.style.left = `${e.clientX - r.left - size / 2}px`;
    ink.style.top = `${e.clientY - r.top - size / 2}px`;
    clip.appendChild(ink);
    host.appendChild(clip);
    const a = ink.animate(
      [{ transform: 'scale(0)', opacity: 0.35 }, { transform: 'scale(1)', opacity: 0 }],
      { duration: 650, easing: EASE },
    );
    a.onfinish = () => clip.remove();
  };
  document.addEventListener('pointerdown', onDown, { passive: true });
  return () => document.removeEventListener('pointerdown', onDown);
}

/* -------------------------------------------------------------------- tilt */

/** Gentle 3D tilt toward the pointer. `use:tilt` or `use:tilt={{ max: 6 }}`. */
export function tilt(node: HTMLElement, opts: { max?: number } = {}) {
  const max = opts.max ?? 5;
  let frame = 0;
  const move = (e: PointerEvent) => {
    if (motionReduced() || e.pointerType === 'touch') return;
    const r = node.getBoundingClientRect();
    const x = (e.clientX - r.left) / r.width - 0.5;
    const y = (e.clientY - r.top) / r.height - 0.5;
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => {
      node.style.setProperty('--tilt-x', `${(-y * max).toFixed(2)}deg`);
      node.style.setProperty('--tilt-y', `${(x * max).toFixed(2)}deg`);
      node.style.setProperty('--glare-x', `${((x + 0.5) * 100).toFixed(1)}%`);
      node.style.setProperty('--glare-y', `${((y + 0.5) * 100).toFixed(1)}%`);
    });
  };
  const leave = () => {
    cancelAnimationFrame(frame);
    node.style.setProperty('--tilt-x', '0deg');
    node.style.setProperty('--tilt-y', '0deg');
  };
  node.classList.add('tilt');
  node.addEventListener('pointermove', move);
  node.addEventListener('pointerleave', leave);
  return {
    destroy() {
      node.removeEventListener('pointermove', move);
      node.removeEventListener('pointerleave', leave);
      cancelAnimationFrame(frame);
    },
  };
}
