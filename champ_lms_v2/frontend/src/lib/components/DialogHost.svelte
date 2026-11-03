<script lang="ts">
  // Shows the app's confirm / alert dialogs (stores/dialog), one at a time,
  // above everything, the video studio included. Esc or a click on the
  // backdrop dismisses; keys pressed in the dialog stay in it, so the page's
  // shortcuts (the studio's Space, Esc, Ctrl+Z…) don't fire underneath.
  import Icon from '$lib/components/Icon.svelte';
  import { dialogs, settleDialog, type DialogRequest } from '$lib/stores/dialog';
  import { trapFocus } from '$lib/utils/focus-trap';

  $: req = $dialogs[0] as DialogRequest | undefined;

  const ICON = { alert: 'alert', trash: 'trash', info: 'info', unsaved: 'edit' } as const;

  function portal(node: HTMLElement) {
    document.body.appendChild(node);
    return { destroy() { node.remove(); } };
  }
  function onKey(e: KeyboardEvent) {
    if (!req) return;
    e.stopPropagation();
    if (e.key === 'Escape') { e.preventDefault(); settleDialog(req, null); }
  }
  // Keys from outside the dialog (focus left on the page) don't reach the page either.
  function onWindowKey(e: KeyboardEvent) {
    if (!req || (e.target as Element)?.closest?.('.dlg-overlay')) return;
    e.preventDefault();
    e.stopPropagation();
    if (e.key === 'Escape') settleDialog(req, null);
    else (document.querySelector('.dlg-overlay [data-autofocus], .dlg-overlay button') as HTMLElement | null)?.focus();
  }
</script>

<svelte:window on:keydown|capture={onWindowKey} />

{#if req}
  {#key req}
    <div class="overlay dlg-overlay" role="presentation" use:portal on:click|self={() => req && settleDialog(req, null)}>
      <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
      <div class="modal dlg tone-{req.tone ?? 'info'}" class:wide={req.actions.length > 2} role="alertdialog" aria-modal="true"
        aria-labelledby="dlg-title" aria-describedby={req.message ? 'dlg-msg' : undefined}
        tabindex="-1" use:trapFocus on:keydown={onKey}>
        {#if req.icon}
          <span class="dlg-ico" aria-hidden="true"><Icon name={ICON[req.icon]} size={22} /></span>
        {/if}
        <h2 id="dlg-title">{req.title}</h2>
        {#if req.message}<p id="dlg-msg">{req.message}</p>{/if}
        <div class="dlg-actions" class:three={req.actions.length > 2}>
          {#each req.actions as a}
            <button class="dlg-btn {a.kind ?? 'ghost'}" disabled={a.disabled}
              data-autofocus={(req.focus ?? req.actions[req.actions.length - 1].id) === a.id ? '' : undefined}
              on:click={() => req && settleDialog(req, a.id)}>{a.label}</button>
          {/each}
        </div>
      </div>
    </div>
  {/key}
{/if}

<style>
  /* The app's one modal look: the theme's scrim, a surface card with the
     large radius, the deep shadow. .overlay / .modal pick up the shared
     fade and rise-in from app.css. */
  .dlg-overlay {
    position: fixed; inset: 0; z-index: 3000; display: grid; place-items: center; padding: 1rem;
    background: var(--scrim);
  }
  .dlg {
    width: min(440px, 100%); max-height: calc(100vh - 2rem); overflow: auto;
    background: var(--surface); color: var(--text); border: 1px solid var(--border);
    border-radius: var(--radius-xl); box-shadow: var(--shadow-lg);
    padding: 1.5rem 1.5rem 1.25rem; outline: none;
  }
  /* Room for three choices on one row. */
  .dlg.wide { width: min(500px, 100%); }
  .dlg-ico {
    width: 46px; height: 46px; border-radius: 50%; display: grid; place-items: center; margin-bottom: 0.9rem;
    color: var(--info); background: color-mix(in srgb, var(--info) 13%, transparent);
  }
  .tone-danger .dlg-ico { color: var(--danger); background: color-mix(in srgb, var(--danger) 13%, transparent); }
  .tone-warn .dlg-ico { color: var(--warn); background: color-mix(in srgb, var(--warn) 15%, transparent); }
  h2 { margin: 0 0 0.45rem; font-size: 1.12rem; font-weight: 700; letter-spacing: -0.015em; line-height: 1.35; }
  p { margin: 0; color: var(--text-secondary); font-size: 0.9rem; line-height: 1.6; white-space: pre-line; }
  .dlg-actions { display: flex; justify-content: flex-end; gap: 0.5rem; margin-top: 1.35rem; flex-wrap: wrap; }
  /* Three choices: the dismissive one sits apart on the left. */
  .dlg-actions.three .dlg-btn:first-child { margin-right: auto; }
  .dlg-btn {
    min-height: 40px; padding: 0 1.1rem; border-radius: var(--radius-pill); border: 1px solid transparent;
    font: inherit; font-size: 0.88rem; font-weight: 700; cursor: pointer; white-space: nowrap;
    transition: background-color var(--dur-2), border-color var(--dur-2), translate var(--dur-2) var(--ease-out), box-shadow var(--dur-2);
  }
  .dlg-btn:not(:disabled):hover { translate: 0 -1px; }
  .dlg-btn:focus-visible { outline: 2px solid var(--text); outline-offset: 2px; }
  .dlg-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .dlg-btn.ghost { background: var(--surface2); color: var(--text); border-color: var(--border); font-weight: 600; }
  .dlg-btn.ghost:not(:disabled):hover { background: var(--surface3); border-color: var(--border-hover); }
  .dlg-btn.primary { background: var(--accent); color: var(--on-accent); }
  .dlg-btn.primary:not(:disabled):hover { background: var(--accent-hover); box-shadow: var(--shadow); }
  /* The light theme's red in both themes: the dark theme's --danger is a pale
     red that white text can't be read on. */
  .dlg-btn.danger { background: #c7232c; color: #fff; }
  .dlg-btn.danger:not(:disabled):hover { background: #a81d25; box-shadow: var(--shadow); }
  @media (min-width: 481px) { .dlg-actions { flex-wrap: nowrap; } }
  @media (max-width: 480px) {
    .dlg-actions { flex-direction: column-reverse; align-items: stretch; }
    .dlg-actions.three .dlg-btn:first-child { margin-right: 0; }
  }
</style>
