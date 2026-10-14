<script lang="ts">
  // One tooltip for the whole app, mounted once in the root layout. Any
  // element with a `title` (or `data-tooltip`) gets this bubble instead of the
  // browser's plain native tooltip: on first hover/focus the title moves to
  // data-tooltip, so the native one never appears, and to aria-description,
  // so screen readers still hear it. Pages keep writing plain `title="…"`.
  // (The top-bar tabs use their own CSS label off `data-tip`; that attribute
  // is deliberately not picked up here, or each tab would show two.)
  import { onMount, tick } from 'svelte';

  const SHOW_DELAY = 280;
  // Moving straight from one tooltip to the next skips the delay.
  const WARM_FOR = 400;
  const GAP = 8;
  const MARGIN = 10;

  let text = '';
  let visible = false;
  let below = false;
  let x = 0;
  let y = 0;
  let arrowX = 0;
  let bubble: HTMLDivElement;
  let target: HTMLElement | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let settle: ReturnType<typeof setTimeout> | undefined;
  let hiddenAt = 0;

  function claim(el: HTMLElement): string {
    const title = el.getAttribute('title');
    if (title !== null) {
      el.removeAttribute('title');
      if (title.trim()) {
        el.dataset.tooltip = title;
        if (!el.hasAttribute('aria-label') && !el.hasAttribute('aria-describedby')) el.setAttribute('aria-description', title);
      } else {
        delete el.dataset.tooltip;
        el.removeAttribute('aria-description');
      }
    }
    return el.dataset.tooltip?.trim() ?? '';
  }

  function find(node: EventTarget | null): HTMLElement | null {
    if (!(node instanceof Element)) return null;
    // An iframe's title is its accessible name, not a tooltip.
    const el = node.closest<HTMLElement>('[title]:not(iframe), [data-tooltip]');
    return el && el !== document.body ? el : null;
  }

  async function place() {
    if (!target || !bubble) return;
    await tick();
    if (!target || !bubble) return;
    const r = target.getBoundingClientRect();
    // offsetWidth/Height, not the bounding box: the pop-in animation scales
    // the bubble, and measuring mid-animation put it a few pixels off.
    const w = bubble.offsetWidth;
    const h = bubble.offsetHeight;
    below = r.top - h - GAP < MARGIN;
    const cx = r.left + r.width / 2;
    x = Math.max(MARGIN, Math.min(cx - w / 2, window.innerWidth - MARGIN - w));
    y = below ? r.bottom + GAP : r.top - h - GAP;
    arrowX = Math.max(12, Math.min(cx - x, w - 12));
  }

  function show(el: HTMLElement) {
    const tip = claim(el);
    if (!tip) return;
    clearTimeout(timer);
    clearTimeout(settle);
    target = el;
    const open = () => {
      text = tip; visible = true; place();
      // Cards and pills lift on hover; place again once that motion settles.
      settle = setTimeout(place, 480);
    };
    if (visible || Date.now() - hiddenAt < WARM_FOR) open();
    else timer = setTimeout(open, SHOW_DELAY);
  }

  function hide() {
    clearTimeout(timer);
    clearTimeout(settle);
    if (visible) hiddenAt = Date.now();
    visible = false;
    target = null;
  }

  onMount(() => {
    const over = (e: PointerEvent) => {
      if (e.pointerType === 'touch') return;
      const el = find(e.target);
      if (el && el !== target) show(el);
    };
    const out = (e: PointerEvent) => {
      if (target && !target.contains(e.relatedTarget as Node)) hide();
    };
    const focusIn = (e: FocusEvent) => {
      const el = find(e.target);
      if (el && (e.target as Element).matches(':focus-visible')) show(el);
    };
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') hide(); };
    // A title that changes later (e.g. the theme toggle after a click) is
    // claimed straight away, so the native tooltip can't slip through.
    // To clear a tooltip, set title to '' — not undefined/null: once claimed
    // the attribute is already gone, so removing it again records no
    // mutation and the old text would stay.
    const mo = new MutationObserver(list => {
      for (const m of list) {
        const el = m.target as HTMLElement;
        if (el.tagName === 'IFRAME' || !el.hasAttribute('title')) continue;
        const tip = claim(el);
        if (el === target) { if (tip) { text = tip; place(); } else hide(); }
      }
    });
    mo.observe(document.body, { attributes: true, attributeFilter: ['title'], subtree: true });

    document.addEventListener('pointerover', over);
    document.addEventListener('pointerout', out);
    document.addEventListener('pointerdown', hide, true);
    document.addEventListener('focusin', focusIn);
    document.addEventListener('focusout', hide);
    document.addEventListener('keydown', key);
    window.addEventListener('scroll', hide, true);
    window.addEventListener('resize', hide);
    return () => {
      clearTimeout(timer);
      clearTimeout(settle);
      mo.disconnect();
      document.removeEventListener('pointerover', over);
      document.removeEventListener('pointerout', out);
      document.removeEventListener('pointerdown', hide, true);
      document.removeEventListener('focusin', focusIn);
      document.removeEventListener('focusout', hide);
      document.removeEventListener('keydown', key);
      window.removeEventListener('scroll', hide, true);
      window.removeEventListener('resize', hide);
    };
  });
</script>

{#if visible}
  <div
    class="tip"
    class:below
    role="tooltip"
    aria-hidden="true"
    bind:this={bubble}
    style="left:{x}px;top:{y}px;--ax:{arrowX}px"
  >{text}</div>
{/if}

<style>
  /* Frame colours: an ink bubble in light mode, a light one in dark mode,
     so it always stands off the page. */
  .tip {
    position: fixed; z-index: 3000; pointer-events: none;
    max-width: min(280px, calc(100vw - 20px));
    padding: 0.5rem 0.75rem; border-radius: 11px;
    background: var(--frame); color: var(--on-frame);
    font-size: 0.78rem; font-weight: 600; line-height: 1.4; letter-spacing: 0.005em;
    box-shadow: 0 10px 28px -10px rgba(0, 0, 0, 0.45), 0 2px 6px rgba(0, 0, 0, 0.12);
    overflow-wrap: anywhere;
    transform-origin: var(--ax) 100%;
    animation: tip-in 200ms var(--ease-out);
  }
  .tip.below { transform-origin: var(--ax) 0; animation-name: tip-in-below; }
  :global([data-theme='dark']) .tip { background: var(--on-frame); color: var(--frame); }

  .tip::after {
    content: ''; position: absolute; left: var(--ax); top: 100%;
    width: 10px; height: 10px; margin-left: -5px; margin-top: -5px;
    background: inherit; border-radius: 0 0 3px 0; rotate: 45deg;
  }
  .tip.below::after { top: 0; border-radius: 3px 0 0 0; }

  @keyframes tip-in { from { opacity: 0; transform: translateY(4px) scale(0.94); } }
  @keyframes tip-in-below { from { opacity: 0; transform: translateY(-4px) scale(0.94); } }
  @media (prefers-reduced-motion: reduce) { .tip, .tip.below { animation: none; } }
</style>
