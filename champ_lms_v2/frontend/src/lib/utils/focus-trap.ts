// A modal's keyboard focus: it moves into the modal when it opens (to
// [data-autofocus], else the first control), Tab and Shift+Tab stay inside,
// and it goes back to where it was when the modal closes.
const FOCUSABLE =
  'button:not([disabled]), [href], input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function trapFocus(node: HTMLElement) {
  const before = document.activeElement as HTMLElement | null;
  const items = () => [...node.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(el => el.getClientRects().length > 0);

  // After the modal's first render, so its controls exist.
  const t = setTimeout(() => {
    if (node.contains(document.activeElement)) return;
    const el = node.querySelector<HTMLElement>('[data-autofocus]') ?? items()[0] ?? node;
    el.focus({ preventScroll: true });
  });

  function onKey(e: KeyboardEvent) {
    if (e.key !== 'Tab') return;
    const list = items();
    if (!list.length) { e.preventDefault(); return; }
    const first = list[0], last = list[list.length - 1];
    const at = document.activeElement;
    if (e.shiftKey && (at === first || !node.contains(at))) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && (at === last || !node.contains(at))) { e.preventDefault(); first.focus(); }
  }
  node.addEventListener('keydown', onKey);

  return {
    destroy() {
      clearTimeout(t);
      node.removeEventListener('keydown', onKey);
      if (before?.isConnected) before.focus({ preventScroll: true });
    },
  };
}
