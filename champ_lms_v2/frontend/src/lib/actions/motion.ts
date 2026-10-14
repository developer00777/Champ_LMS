/**
 * Small motion helpers used across the UI. Both respect
 * the in-app animation switch (lib/stores/motion.ts) by jumping to the end.
 */

const reduced = () =>
  typeof document !== 'undefined' && document.documentElement.dataset.motion === 'reduced';

/**
 * Fade-and-rise an element the first time it scrolls into view.
 * `use:reveal` or `use:reveal={{ delay: 120 }}`.
 */
export function reveal(node: HTMLElement, opts: { delay?: number } = {}) {
  if (reduced() || !('IntersectionObserver' in window)) return {};
  node.classList.add('reveal-pending');
  if (opts.delay) node.style.setProperty('--reveal-delay', `${opts.delay}ms`);
  const io = new IntersectionObserver(
    (entries) => {
      for (const e of entries) {
        if (!e.isIntersecting) continue;
        node.classList.remove('reveal-pending');
        node.classList.add('reveal-in');
        io.disconnect();
        // Drop the animation class once done so no transform lingers.
        node.addEventListener('animationend', () => node.classList.remove('reveal-in'), { once: true });
      }
    },
    { rootMargin: '0px 0px -8% 0px', threshold: 0.05 },
  );
  io.observe(node);
  return { destroy: () => io.disconnect() };
}

/**
 * Count a number up from its previous value. `use:countUp={points}`.
 * The element's text is owned by the action, so render nothing inside it.
 */
export function countUp(node: HTMLElement, value: number | null | undefined) {
  let shown = 0;
  let frame = 0;
  const fmt = (n: number) => Math.round(n).toLocaleString();

  function run(target: number) {
    cancelAnimationFrame(frame);
    if (reduced() || !Number.isFinite(target)) {
      shown = target || 0;
      node.textContent = fmt(shown);
      return;
    }
    const from = shown;
    const start = performance.now();
    const dur = Math.min(1200, 500 + Math.abs(target - from) * 4);
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / dur);
      const eased = 1 - Math.pow(1 - t, 4);
      shown = from + (target - from) * eased;
      node.textContent = fmt(shown);
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
  }

  run(value ?? 0);
  return {
    update: (v: number | null | undefined) => run(v ?? 0),
    destroy: () => cancelAnimationFrame(frame),
  };
}
