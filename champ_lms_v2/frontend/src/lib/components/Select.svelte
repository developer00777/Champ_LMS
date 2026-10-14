<script lang="ts" context="module">
  export type SelectOption = { value: unknown; label: string; hint?: string };
  let uid = 0;
</script>

<script lang="ts">
  // The app's dropdown. Replaces the native <select>, whose open list is drawn
  // by the OS and can't be themed. The list is portalled to <body> so a
  // scrolling panel or table cell never clips it, and so a click on an option
  // doesn't re-activate a <label> wrapped around the trigger.
  import { createEventDispatcher, tick } from 'svelte';
  import Icon from './Icon.svelte';

  export let value: unknown;
  export let options: SelectOption[] = [];
  /** Shown when no option matches `value`. */
  export let placeholder = 'Select…';
  export let ariaLabel: string | undefined = undefined;
  export let disabled = false;
  /** 'pill' for toolbar filters; 'field' matches the form inputs. */
  export let shape: 'field' | 'pill' = 'field';
  export let size: 'sm' | 'md' | 'lg' = 'md';
  /** 'raised' on a card that is already --surface2. */
  export let tone: 'sunk' | 'raised' = 'sunk';
  /** Search box above the list; on by default once the list is long. */
  export let searchable: boolean | undefined = undefined;
  let className = '';
  export { className as class };

  const dispatch = createEventDispatcher<{ change: unknown }>();
  const id = `sel-${++uid}`;

  let open = false;
  let trigger: HTMLButtonElement;
  let list: HTMLDivElement;
  let scroller: HTMLDivElement;
  let searchInput: HTMLInputElement;
  let query = '';
  let active = -1;
  let style = '';
  let up = false;

  $: selected = options.find(o => o.value === value);
  // '' / null options are the "all" or "none" choice: shown, but quieter.
  $: quiet = !selected || selected.value === '' || selected.value == null;
  $: canSearch = searchable ?? options.length > 8;
  $: needle = query.trim().toLowerCase();
  $: shown = needle ? options.filter(o => o.label.toLowerCase().includes(needle)) : options;

  function place() {
    if (!trigger) return;
    const r = trigger.getBoundingClientRect();
    const gap = 6, margin = 12;
    const below = window.innerHeight - r.bottom - gap - margin;
    const above = r.top - gap - margin;
    up = below < 240 && above > below;
    const width = Math.max(r.width, 200);
    const left = Math.max(margin, Math.min(r.left, window.innerWidth - margin - width));
    const maxHeight = Math.max(160, Math.min(340, up ? above : below));
    style = `left:${left}px;width:${width}px;max-height:${maxHeight}px;` +
      (up ? `bottom:${window.innerHeight - r.top + gap}px;` : `top:${r.bottom + gap}px;`);
  }

  async function show() {
    if (disabled || open) return;
    query = '';
    active = Math.max(0, options.findIndex(o => o.value === value));
    place();
    open = true;
    await tick();
    if (canSearch) searchInput?.focus();
    reveal();
  }

  function hide(refocus = true) {
    if (!open) return;
    open = false;
    if (refocus) trigger?.focus();
  }

  function choose(o: SelectOption) {
    const changed = o.value !== value;
    value = o.value;
    hide();
    if (changed) dispatch('change', o.value);
  }

  async function reveal() {
    await tick();
    scroller?.querySelector<HTMLElement>(`#${id}-o${active}`)?.scrollIntoView({ block: 'nearest' });
  }

  function move(step: number) {
    if (!shown.length) return;
    active = (active + step + shown.length) % shown.length;
    reveal();
  }

  let typed = '';
  let typedAt = 0;
  function typeahead(ch: string) {
    const now = Date.now();
    typed = now - typedAt > 700 ? ch : typed + ch;
    typedAt = now;
    const i = shown.findIndex(o => o.label.toLowerCase().startsWith(typed.toLowerCase()));
    if (i >= 0) { active = i; reveal(); }
  }

  function onKey(e: KeyboardEvent) {
    if (!open) {
      if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(e.key)) { e.preventDefault(); show(); }
      return;
    }
    switch (e.key) {
      case 'ArrowDown': e.preventDefault(); move(1); break;
      case 'ArrowUp': e.preventDefault(); move(-1); break;
      case 'Home': if (!canSearch) { e.preventDefault(); active = 0; reveal(); } break;
      case 'End': if (!canSearch) { e.preventDefault(); active = shown.length - 1; reveal(); } break;
      case 'Enter': e.preventDefault(); if (shown[active]) choose(shown[active]); break;
      case ' ': if (!canSearch) { e.preventDefault(); if (shown[active]) choose(shown[active]); } break;
      // Stop here so a dialog or menu listening on window stays open.
      case 'Escape': e.preventDefault(); e.stopPropagation(); hide(); break;
      // Focus goes back to the trigger first, so Tab moves on from there
      // rather than from the search box at the end of <body>.
      case 'Tab': hide(); break;
      default:
        if (!canSearch && e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) typeahead(e.key);
    }
  }

  function onOutside(e: PointerEvent) {
    const t = e.target as Node;
    // A wrapping <label> forwards its click to the trigger, which toggles.
    const own = trigger?.closest('label') ?? trigger;
    if (open && !own?.contains(t) && !list?.contains(t)) hide(false);
  }

  function onScroll(e: Event) {
    if (open && !list?.contains(e.target as Node)) place();
  }

  function portal(node: HTMLElement) {
    document.body.appendChild(node);
    return { destroy: () => node.remove() };
  }
</script>

<svelte:window on:pointerdown={onOutside} on:resize={() => open && place()} on:scroll|capture={onScroll} />

<div class="sel {shape} {size} {tone} {className}" class:open>
  <button
    type="button"
    class="trigger"
    bind:this={trigger}
    {disabled}
    role="combobox"
    aria-label={ariaLabel}
    aria-haspopup="listbox"
    aria-expanded={open}
    aria-controls={open ? `${id}-list` : undefined}
    aria-activedescendant={open && !canSearch && shown[active] ? `${id}-o${active}` : undefined}
    on:click={() => (open ? hide() : show())}
    on:keydown={onKey}
    on:keyup={e => e.key === ' ' && e.preventDefault()}
  >
    <span class="value" class:quiet>{selected ? selected.label : placeholder}</span>
    <span class="chev" aria-hidden="true"><Icon name="chevronDown" size={16} stroke={2} /></span>
  </button>
</div>

{#if open}
  <div class="sel-pop" class:up {style} bind:this={list} use:portal>
    {#if canSearch}
      <label class="sel-search">
        <Icon name="search" size={15} />
        <input
          bind:this={searchInput}
          bind:value={query}
          on:input={() => { active = 0; reveal(); }}
          on:keydown={onKey}
          placeholder="Search…"
          aria-label="Search options"
          aria-controls="{id}-list"
          aria-activedescendant={shown[active] ? `${id}-o${active}` : undefined}
        />
      </label>
    {/if}
    <div class="sel-scroll" role="listbox" id="{id}-list" aria-label={ariaLabel} bind:this={scroller}>
      {#each shown as o, i}
        {@const isSel = o.value === value}
        <!-- svelte-ignore a11y-click-events-have-key-events -->
        <div
          id="{id}-o{i}"
          role="option"
          tabindex="-1"
          aria-selected={isSel}
          class="sel-opt"
          class:active={i === active}
          class:selected={isSel}
          on:pointermove={() => (active = i)}
          on:mousedown|preventDefault
          on:click={() => choose(o)}
        >
          <span class="txt">
            <span class="lbl">{o.label}</span>
            {#if o.hint}<span class="hint">{o.hint}</span>{/if}
          </span>
          {#if isSel}<span class="tick"><Icon name="check" size={16} stroke={2.4} /></span>{/if}
        </div>
      {:else}
        <p class="sel-empty">No matches for “{query.trim()}”</p>
      {/each}
    </div>
  </div>
{/if}

<style>
  .sel { position: relative; display: block; width: 100%; min-width: 0; }

  .trigger {
    width: 100%; height: 44px; min-width: 0;
    display: flex; align-items: center; gap: 0.5rem;
    padding: 0 0.55rem 0 0.9rem; text-align: left;
    background: var(--surface2); color: var(--text);
    border: 1px solid var(--border-hover); border-radius: 14px;
    font-size: 0.9rem; font-weight: 500; line-height: 1.2;
  }
  .trigger:hover:not(:disabled) { background: var(--surface3); border-color: color-mix(in srgb, var(--text) 32%, transparent); }
  .trigger:focus-visible, .open .trigger {
    outline: none; background: var(--surface); border-color: var(--accent);
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 14%, transparent);
  }
  .trigger:disabled { opacity: 0.55; cursor: not-allowed; }

  .value { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .value.quiet { color: var(--text-secondary); font-weight: 400; }

  /* The chevron sits in its own chip so the box reads as a dropdown at a glance. */
  .chev {
    flex: none; display: grid; place-items: center; width: 26px; height: 26px; border-radius: 50%;
    background: var(--surface); color: var(--text); box-shadow: var(--shadow-sm), 0 0 0 1px var(--border);
    transition: rotate var(--dur-3) var(--ease-out), color var(--dur-2), background-color var(--dur-2);
  }
  .trigger:hover:not(:disabled) .chev, .open .chev { background: var(--accent); color: var(--on-accent); box-shadow: none; }
  .open .chev { rotate: 180deg; }

  .pill .trigger { border-radius: var(--radius-pill); padding-left: 1.05rem; }
  .sm .trigger { height: 38px; font-size: 0.86rem; border-radius: 12px; padding-left: 0.75rem; }
  .sm.pill .trigger { border-radius: var(--radius-pill); }
  .lg .trigger { height: 46px; }
  .raised .trigger { background: var(--surface); }
  .raised .trigger:hover:not(:disabled) { background: var(--surface3); }
  .raised .chev { background: var(--surface2); }

  /* ---------- the open list ---------- */
  .sel-pop {
    position: fixed; z-index: 2000;
    display: flex; flex-direction: column;
    background: var(--surface); color: var(--text);
    border: 1px solid var(--border-hover); border-radius: 18px;
    box-shadow: 0 6px 16px -6px rgba(12, 12, 13, 0.14), 0 26px 52px -18px rgba(12, 12, 13, 0.38);
    overflow: hidden;
    transform-origin: top center;
    animation: pop-in 220ms var(--ease-out);
  }
  .sel-pop.up { transform-origin: bottom center; animation-name: pop-up; }
  /* Shadows barely show on a dark canvas, so the list steps up a surface instead. */
  :global([data-theme='dark']) .sel-pop {
    background: var(--surface2); border-color: rgba(255, 255, 255, 0.14);
    box-shadow: 0 26px 52px -18px rgba(0, 0, 0, 0.85);
  }
  @keyframes pop-in { from { opacity: 0; transform: translateY(-6px) scale(0.97); } }
  @keyframes pop-up { from { opacity: 0; transform: translateY(6px) scale(0.97); } }

  .sel-search {
    flex: none; display: flex; align-items: center; gap: 0.5rem;
    margin: 0.4rem 0.4rem 0; padding: 0 0.75rem; height: 40px;
    background: var(--surface2); border-radius: 12px; color: var(--muted);
  }
  .sel-search:focus-within { color: var(--text); box-shadow: inset 0 0 0 1.5px var(--border-hover); }
  .sel-search input {
    flex: 1; min-width: 0; height: 100%; background: none; border: none; outline: none;
    font-size: 0.88rem; color: var(--text);
  }
  .sel-search input::placeholder { color: var(--muted); }

  .sel-scroll {
    flex: 1; min-height: 0; overflow-y: auto; overscroll-behavior: contain;
    padding: 0.4rem; display: flex; flex-direction: column; gap: 2px;
    scrollbar-width: thin;
  }

  .sel-opt {
    position: relative;
    display: flex; align-items: center; gap: 0.6rem;
    padding: 0.58rem 0.7rem 0.58rem 0.85rem; border-radius: 11px;
    font-size: 0.88rem; font-weight: 500; color: var(--text); cursor: pointer; user-select: none;
    transition: background-color var(--dur-1) var(--ease-out), padding-left var(--dur-2) var(--ease-out);
  }
  /* Hover/keyboard focus: a soft fill plus an accent bar that slides in. */
  .sel-opt::before {
    content: ''; position: absolute; left: 4px; top: 50%; width: 3px; height: 0; border-radius: 99px;
    background: var(--accent); translate: 0 -50%;
    transition: height var(--dur-2) var(--ease-out);
  }
  .sel-opt.active { background: color-mix(in srgb, var(--text) 9%, transparent); padding-left: 1.05rem; }
  .sel-opt.active::before { height: 60%; }
  .sel-opt.selected { background: color-mix(in srgb, var(--text) 5%, transparent); }
  .sel-opt.selected.active { background: color-mix(in srgb, var(--text) 12%, transparent); }

  .txt { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 0.1rem; }
  .lbl { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .selected .lbl { font-weight: 700; }
  .hint { font-size: 0.74rem; color: var(--muted); line-height: 1.35; }

  .tick {
    flex: none; display: grid; place-items: center; width: 22px; height: 22px; border-radius: 50%;
    background: var(--accent); color: var(--on-accent);
    animation: tick-in 260ms var(--ease-out);
  }
  @keyframes tick-in { from { scale: 0.4; opacity: 0; } }

  .sel-empty { padding: 0.9rem 0.8rem; font-size: 0.84rem; color: var(--muted); text-align: center; }

  @media (prefers-reduced-motion: reduce) {
    .sel-pop, .tick { animation: none; }
    .chev, .sel-opt, .sel-opt::before { transition: none; }
  }
</style>
