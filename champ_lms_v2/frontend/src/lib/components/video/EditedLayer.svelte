<script lang="ts">
  // Everything the video studio draws over a video: blurred boxes, filter
  // washes and vignette, visual effects and cut transitions, fades, text and
  // stickers, styled captions, the brand mark and a progress bar. Used by the
  // learner's player (clip time) and the studio's preview (source time); `t`,
  // `from`, `to`, the edits and the caption lines just have to share one time
  // base. In the studio (`editable`) text and stickers can be picked and
  // dragged on the picture.
  import type { TranscriptSegment } from '$lib/api/client';
  import logoUrl from '$lib/reports/champions-group-logo.png';
  import {
    CAPTION_DEFAULTS, effectsAt, fadeOpacity, frameStyle, fxAt, segmentAt, tintsOf, transitionAt, vignetteOf, wordsAt,
    type Overlay, type VideoEdits,
  } from '$lib/utils/video-edits';

  export let edits: VideoEdits | null = null;
  export let t = 0;
  // The stretch that plays, for fades: in at `from`, out at `to`.
  export let from = 0;
  export let to = 0;
  export let captions: TranscriptSegment[] = [];
  export let ccOn = false;
  // Custom controls cover the bottom of the player, so bottom text sits higher.
  export let raised = false;
  // Studio only: text and stickers answer to the pointer.
  export let editable = false;
  export let selected = -1;
  export let onPick: (index: number) => void = () => {};
  // Dragged to (x, y), % of the frame, centre of the text.
  export let onMove: (index: number, x: number, y: number, phase: 'start' | 'move' | 'end') => void = () => {};

  $: style = { ...CAPTION_DEFAULTS, ...(edits?.captions ?? {}) };
  $: seg = ccOn && captions.length ? segmentAt(captions, t) : null;
  $: animated = style.preset === 'pop' || style.preset === 'karaoke';
  $: words = seg && animated ? wordsAt(seg, t) : null;
  $: shown = (edits?.overlays ?? []).map((o, i) => ({ o, i })).filter(({ o }) => t >= o.start && t < o.end);
  $: fade = fadeOpacity(edits?.look, t, from, to);
  $: brand = edits?.brand?.watermark ? edits.brand : null;
  $: progress = edits?.brand?.progress_bar && to > from ? Math.min(1, Math.max(0, (t - from) / (to - from))) : null;
  // Blurred boxes sit on the picture, so they follow its zoom.
  $: boxes = effectsAt(edits?.effects, t, 'blur');
  $: picture = boxes.length ? frameStyle(edits?.look, edits?.effects, t, edits?.cuts) : '';
  $: tints = tintsOf(edits?.look);
  $: vignette = vignetteOf(edits?.look);
  $: fx = fxAt(edits?.effects, t);
  $: tr = transitionAt(edits?.look, edits?.cuts, t);
  // Glitch bars move every 1/14 s; a seeded shuffle keeps a frame the same when scrubbed back to.
  const rnd = (n: number) => { const x = Math.sin(n * 12.9898) * 43758.5453; return x - Math.floor(x); };
  $: tick = Math.floor(t * 14);

  // ---- dragging text on the picture --------------------------------------------
  let drag: { i: number; x0: number; y0: number; px: number; py: number; rect: DOMRect } | null = null;
  function down(e: PointerEvent, o: Overlay, i: number) {
    if (!editable || e.button !== 0) return;
    e.stopPropagation();
    e.preventDefault();
    onPick(i);
    const el = e.currentTarget as HTMLElement;
    const rect = (el.offsetParent ?? el.parentElement)!.getBoundingClientRect();
    const box = (el.firstElementChild as HTMLElement ?? el).getBoundingClientRect();
    // Where it is now: its saved spot, or the middle of where its position puts it.
    const x = o.position === 'free' && o.x != null ? o.x : ((box.left + box.width / 2 - rect.left) / rect.width) * 100;
    const y = o.position === 'free' && o.y != null ? o.y : ((box.top + box.height / 2 - rect.top) / rect.height) * 100;
    drag = { i, x0: x, y0: y, px: e.clientX, py: e.clientY, rect };
    // The text box takes the pointer; its moves bubble up to this row.
    (e.target as Element).setPointerCapture(e.pointerId);
    onMove(i, round1(x), round1(y), 'start');
  }
  function move(e: PointerEvent) {
    if (!drag) return;
    const x = clamp(drag.x0 + ((e.clientX - drag.px) / drag.rect.width) * 100);
    const y = clamp(drag.y0 + ((e.clientY - drag.py) / drag.rect.height) * 100);
    onMove(drag.i, round1(x), round1(y), 'move');
  }
  function up() {
    if (drag) onMove(drag.i, NaN, NaN, 'end');
    drag = null;
  }
  const clamp = (v: number) => Math.min(97, Math.max(3, v));
  const round1 = (v: number) => Math.round(v * 10) / 10;
  // Typewriter text: about 28 characters a second from the overlay's start.
  const typed = (text: string, start: number) => text.slice(0, Math.max(0, Math.floor((t - start) * 28)));
</script>

{#if boxes.length}
  <div class="pic" style={picture} aria-hidden="true">
    {#each boxes as b}
      <div class="redact {b.mode ?? 'blur'}" style="left:{b.x ?? 0}%; top:{b.y ?? 0}%; width:{b.w ?? 20}%; height:{b.h ?? 20}%"></div>
    {/each}
  </div>
{/if}

{#each tints as w}<div class="tint" style="background:{w.color}; mix-blend-mode:{w.blend}; opacity:{w.opacity}" aria-hidden="true"></div>{/each}
{#if vignette > 0.001}<div class="vignette" style="--v:{vignette}" aria-hidden="true"></div>{/if}

{#each fx as f}
  {#if f.style === 'glitch'}
    {#each [0, 1, 2] as n}
      <div class="glitch" aria-hidden="true"
        style="top:{rnd(tick * 3 + n) * 85}%; height:{4 + rnd(tick * 7 + n) * 12}%; translate:{(rnd(tick * 5 + n) - 0.5) * 8 * f.k}% 0; opacity:{f.k}"></div>
    {/each}
    {#if tick % 3 === 0}<div class="glitch-wash" style="opacity:{0.55 * f.k}" aria-hidden="true"></div>{/if}
  {:else if f.style === 'analog'}
    <div class="analog" style="opacity:{f.k}; --n:{rnd(tick) * 100}px" aria-hidden="true"></div>
  {:else if f.style === 'flash'}
    <div class="flash" style="opacity:{Math.max(0, 1 - f.since / 0.5) * f.k}" aria-hidden="true"></div>
  {:else if f.style === 'defocus'}
    <div class="defocus" style="--b:{6 * f.k}px" aria-hidden="true"></div>
  {/if}
{/each}

{#if tr?.kind === 'fade'}<div class="fade" style="opacity:{tr.p}" aria-hidden="true"></div>
{:else if tr?.kind === 'flash'}<div class="flash" style="opacity:{tr.p * 0.9}" aria-hidden="true"></div>
{:else if tr?.kind === 'blur'}<div class="defocus" style="--b:{tr.p * 14}px" aria-hidden="true"></div>{/if}

{#if fade > 0.001}<div class="fade" style="opacity:{fade}" aria-hidden="true"></div>{/if}

{#each shown as { o, i } (i + ':' + o.start + o.text)}
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div class="ov pos-{o.position} st-{o.style} osz-{o.size ?? 'm'}" class:raised class:editable class:picked={editable && selected === i}
    aria-hidden="true"
    style="{o.color ? `--ov-accent:${o.color};` : ''}{o.position === 'free' ? `--x:${o.x ?? 50}%; --y:${o.y ?? 50}%;` : ''}"
    on:pointerdown={e => down(e, o, i)} on:pointermove={move} on:pointerup={up} on:pointercancel={up}>
    <div class="ov-in anim-{o.anim ?? 'rise'}">
      {#if o.style === 'quote'}<span class="qmark">“</span>{/if}
      <b>{o.anim === 'type' ? typed(o.text, o.start) : o.text}</b>
      {#if o.subtext}<span class="sub">{o.anim === 'type' ? typed(o.subtext, o.start + o.text.length / 28) : o.subtext}</span>{/if}
    </div>
  </div>
{/each}

{#if seg}
  <div class="cap pre-{style.preset} cpos-{style.position} size-{style.size} font-{style.font}" class:raised class:upper={style.uppercase}
    aria-hidden="true" style="--cap-color:{style.color}; --cap-hi:{style.highlight}">
    {#if words}
      <span class="line">{#each words.words as w, i}<span class="w" class:said={i < words.active} class:now={i === words.active}>{w}</span>{' '}{/each}</span>
    {:else}
      <span class="line">{seg.text}</span>
    {/if}
  </div>
{/if}

{#if brand}
  <img class="mark pos-{brand.position}" class:raised src={logoUrl} alt="" style="opacity:{brand.opacity}" />
{/if}

{#if progress !== null}
  <div class="progress" aria-hidden="true"><i style="width:{progress * 100}%; background:{edits?.brand?.progress_color ?? '#ff3b45'}"></i></div>
{/if}

<style>
  .fade { position: absolute; inset: 0; background: #000; pointer-events: none; z-index: 2; }
  .tint { position: absolute; inset: 0; pointer-events: none; z-index: 1; }
  .vignette { position: absolute; inset: 0; pointer-events: none; z-index: 2;
    background: radial-gradient(ellipse at center, transparent 48%, rgba(0,0,0,calc(var(--v) * 0.85)) 100%); }
  .flash { position: absolute; inset: 0; background: #fff; pointer-events: none; z-index: 2; }
  .defocus { position: absolute; inset: 0; pointer-events: none; z-index: 2; backdrop-filter: blur(var(--b)); -webkit-backdrop-filter: blur(var(--b)); }
  .glitch { position: absolute; left: -5%; right: -5%; pointer-events: none; z-index: 2;
    backdrop-filter: hue-rotate(110deg) saturate(3) contrast(1.4); -webkit-backdrop-filter: hue-rotate(110deg) saturate(3) contrast(1.4);
    box-shadow: 0 0 0 1px rgba(0,255,234,.25); }
  .glitch-wash { position: absolute; inset: 0; pointer-events: none; z-index: 2; mix-blend-mode: screen;
    background: linear-gradient(90deg, rgba(255,0,80,.25), transparent 30%, transparent 70%, rgba(0,220,255,.25)); }
  .analog { position: absolute; inset: 0; pointer-events: none; z-index: 2;
    backdrop-filter: sepia(0.35) saturate(1.3) contrast(1.1); -webkit-backdrop-filter: sepia(0.35) saturate(1.3) contrast(1.1);
    background:
      repeating-linear-gradient(0deg, rgba(0,0,0,.22) 0 1px, transparent 1px 3px),
      url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='120' height='120'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2'/></filter><rect width='120' height='120' filter='url(%23n)' opacity='.35'/></svg>");
    background-position: 0 0, var(--n) var(--n); }
  .pic { position: absolute; inset: 0; pointer-events: none; z-index: 1; }
  .redact { position: absolute; border-radius: 6px; }
  .redact.blur { backdrop-filter: blur(18px) saturate(0.6); -webkit-backdrop-filter: blur(18px) saturate(0.6); background: rgba(40,40,48,.18); }
  .redact.black { background: #000; }
  .progress { position: absolute; top: 0; left: 0; right: 0; height: 4px; background: rgba(255,255,255,.18); pointer-events: none; z-index: 5; }
  .progress i { display: block; height: 100%; }

  /* ---- text overlays ---- */
  .ov { position: absolute; left: 0; right: 0; display: flex; justify-content: center; pointer-events: none; z-index: 3; padding: 0 5%; }
  .ov-in { display: grid; gap: 0.2em; justify-items: center; text-align: center; max-width: 90%; }
  .anim-rise { animation: ov-rise 420ms cubic-bezier(.2,.8,.2,1) both; }
  .anim-fade { animation: ov-fade 500ms ease-out both; }
  .anim-pop { animation: ov-pop 480ms cubic-bezier(.3,1.6,.5,1) both; }
  .anim-bounce { animation: ov-pop 480ms cubic-bezier(.3,1.6,.5,1) both, ov-float 1.6s ease-in-out 480ms infinite; }
  .ov.pos-free { left: var(--x); top: var(--y); right: auto; bottom: auto; transform: translate(-50%, -50%); padding: 0; width: max-content; max-width: 80%; }
  .ov.editable .ov-in { pointer-events: auto; cursor: grab; touch-action: none; }
  .ov.editable .ov-in:active { cursor: grabbing; }
  .ov.picked .ov-in { outline: 2px dashed rgba(255,255,255,.9); outline-offset: 6px; border-radius: 6px; }
  .st-sticker b { font-size: calc(var(--k, 1) * clamp(1.8rem, 9cqw, 6rem)); line-height: 1; font-weight: 400; filter: drop-shadow(0 4px 10px rgba(0,0,0,.35)); }
  .osz-xl { --k: 1.8; }
  .osz-s { --k: 0.75; } .osz-l { --k: 1.35; }
  .ov b { font-weight: 800; line-height: 1.15; }
  .ov .sub { font-weight: 500; opacity: 0.9; }
  .pos-top { top: 8%; }
  .pos-center { top: 50%; transform: translateY(-50%); }
  .pos-bottom { bottom: 10%; }
  .pos-bottom.raised { bottom: calc(10% + 44px); }
  .pos-lower-third { bottom: 18%; justify-content: flex-start; padding-left: 5%; }
  .pos-lower-third.raised { bottom: calc(18% + 30px); }
  .pos-lower-third .ov-in { justify-items: start; text-align: left; }

  .st-title b { font-size: calc(var(--k, 1) * clamp(1rem, 5.2cqw, 3rem)); color: var(--ov-accent, #fff); text-shadow: 0 2px 18px rgba(0,0,0,.6), 0 1px 2px rgba(0,0,0,.7); letter-spacing: -0.01em; }
  .st-title .sub { font-size: calc(var(--k, 1) * clamp(0.7rem, 2.3cqw, 1.3rem)); color: #fff; text-shadow: 0 1px 8px rgba(0,0,0,.7); }
  .st-callout .ov-in { background: var(--ov-accent, #ffd23f); color: #111; padding: 0.45em 0.9em; border-radius: 12px; box-shadow: 0 8px 24px rgba(0,0,0,.35); }
  .st-callout b { font-size: calc(var(--k, 1) * clamp(0.8rem, 2.8cqw, 1.6rem)); }
  .st-callout .sub { font-size: calc(var(--k, 1) * clamp(0.65rem, 1.8cqw, 1rem)); }
  .st-label .ov-in { background: rgba(10,10,14,.82); color: #fff; padding: 0.35em 0.75em; border-radius: 8px; border-left: 4px solid var(--ov-accent, #e50914); }
  .st-label b { font-size: calc(var(--k, 1) * clamp(0.7rem, 2.1cqw, 1.2rem)); font-weight: 700; }
  .st-label .sub { font-size: calc(var(--k, 1) * clamp(0.6rem, 1.6cqw, 0.9rem)); color: #d6d6dc; }
  .st-quote .ov-in { background: rgba(255,255,255,.94); color: #15151a; padding: 0.6em 1em 0.7em; border-radius: 14px; max-width: 70%; }
  .st-quote b { font-size: calc(var(--k, 1) * clamp(0.8rem, 2.6cqw, 1.5rem)); font-style: italic; font-weight: 600; }
  .st-quote .sub { font-size: calc(var(--k, 1) * clamp(0.6rem, 1.6cqw, 0.9rem)); color: #55555e; }
  .qmark { font-size: calc(var(--k, 1) * clamp(1.4rem, 5cqw, 3rem)); line-height: 0.6; color: var(--ov-accent, #e50914); font-weight: 900; }
  @keyframes ov-rise { from { opacity: 0; translate: 0 12px; scale: .96; } to { opacity: 1; translate: 0 0; scale: 1; } }
  @keyframes ov-fade { from { opacity: 0; } to { opacity: 1; } }
  @keyframes ov-pop { 0% { opacity: 0; scale: .5; } 100% { opacity: 1; scale: 1; } }
  @keyframes ov-float { 50% { translate: 0 -7%; } }

  /* ---- captions ---- */
  .cap {
    position: absolute; left: 50%; transform: translateX(-50%); z-index: 4;
    width: max-content; max-width: min(80%, 46em); text-align: center; pointer-events: none;
    --s: 1; font-size: calc(clamp(0.72rem, 2.1cqw, 1.2rem) * var(--s)); line-height: 1.45;
  }
  .size-s { --s: 0.85; } .size-l { --s: 1.3; }
  .cpos-bottom { bottom: 13%; } .cpos-bottom.raised { bottom: 70px; }
  .cpos-middle { top: 50%; transform: translate(-50%, -50%); }
  .cpos-top { top: 9%; }
  .line { box-decoration-break: clone; -webkit-box-decoration-break: clone; }
  .font-display { font-family: 'Arial Black', 'Impact', system-ui, sans-serif; }
  .font-serif { font-family: Georgia, 'Times New Roman', serif; }
  .font-rounded { font-family: ui-rounded, 'Nunito', 'Arial Rounded MT Bold', system-ui, sans-serif; }
  .font-mono { font-family: ui-monospace, Consolas, monospace; }
  .cap.upper .line { text-transform: uppercase; }
  .pre-classic .line { color: var(--cap-color, #fff); background: rgba(8,8,12,.72); padding: 0.18em 0.6em; border-radius: 6px; font-weight: 500; text-shadow: 0 1px 2px rgba(0,0,0,.5); }
  .pre-minimal .line { color: var(--cap-color, #fff); font-weight: 500; text-shadow: 0 1px 3px rgba(0,0,0,.95), 0 0 10px rgba(0,0,0,.6); }
  .pre-bold .line, .pre-pop .line, .pre-karaoke .line {
    color: var(--cap-color, #fff); font-weight: 900; letter-spacing: 0.01em; font-size: 1.18em;
    -webkit-text-stroke: 0.06em #000; paint-order: stroke fill; text-shadow: 0 3px 10px rgba(0,0,0,.55);
  }
  .pre-bold .line { text-transform: uppercase; }
  .pre-pop .w { display: inline-block; transition: transform 120ms, background-color 120ms, color 120ms; border-radius: 0.2em; padding: 0 0.08em; }
  .pre-pop .w.now { background: var(--cap-hi, #ffd23f); color: #111; -webkit-text-stroke: 0; transform: scale(1.12) rotate(-1.5deg); }
  /* Words still to come are dimmed in colour, not faded, so their outline keeps them readable on a light slide. */
  .pre-karaoke .w { color: color-mix(in srgb, var(--cap-color, #fff) 50%, #6b6b75); transition: color 120ms; }
  .pre-karaoke .w.said { color: var(--cap-color, #fff); }
  .pre-karaoke .w.now { color: var(--cap-hi, #7ef0a8); }

  /* ---- brand mark ---- */
  .mark { position: absolute; z-index: 3; width: clamp(44px, 11cqw, 120px); height: auto; pointer-events: none;
    filter: drop-shadow(0 1px 4px rgba(0,0,0,.45)); }
  .mark.pos-tl { top: 4%; left: 3%; } .mark.pos-tr { top: 4%; right: 3%; }
  .mark.pos-bl { bottom: 6%; left: 3%; } .mark.pos-br { bottom: 6%; right: 3%; }
  .mark.pos-bl.raised, .mark.pos-br.raised { bottom: 64px; }
  /* Top-left is where the player's CC and Q&A buttons sit. */
  :global(.player-wrap) .mark.pos-tl { top: 56px; }
</style>
