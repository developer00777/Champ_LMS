<script lang="ts">
  // Everything the video studio draws over a video: fades, blurred boxes,
  // text overlays, styled captions, the brand mark and a progress bar. Used by the learner's player (clip
  // time) and the studio's preview (source time); `t`, `from`, `to`, the
  // edits and the caption lines just have to share one time base.
  import type { TranscriptSegment } from '$lib/api/client';
  import logoUrl from '$lib/reports/champions-group-logo.png';
  import {
    CAPTION_DEFAULTS, effectsAt, fadeOpacity, frameStyle, overlaysAt, segmentAt, wordsAt, type VideoEdits,
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

  $: style = { ...CAPTION_DEFAULTS, ...(edits?.captions ?? {}) };
  $: seg = ccOn && captions.length ? segmentAt(captions, t) : null;
  $: animated = style.preset === 'pop' || style.preset === 'karaoke';
  $: words = seg && animated ? wordsAt(seg, t) : null;
  $: shown = overlaysAt(edits?.overlays, t);
  $: fade = fadeOpacity(edits?.look, t, from, to);
  $: brand = edits?.brand?.watermark ? edits.brand : null;
  $: progress = edits?.brand?.progress_bar && to > from ? Math.min(1, Math.max(0, (t - from) / (to - from))) : null;
  // Blurred boxes sit on the picture, so they follow its zoom.
  $: boxes = effectsAt(edits?.effects, t, 'blur');
  $: picture = boxes.length ? frameStyle(edits?.look, edits?.effects, t) : '';
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

{#if fade > 0.001}<div class="fade" style="opacity:{fade}" aria-hidden="true"></div>{/if}

{#each shown as o (o.start + o.text)}
  <div class="ov pos-{o.position} st-{o.style} osz-{o.size ?? 'm'}" class:raised aria-hidden="true"
    style={o.color ? `--ov-accent:${o.color}` : ''}>
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
