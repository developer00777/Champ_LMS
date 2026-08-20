<script lang="ts">
  /**
   * A person's profile picture, with a deterministic initials fallback.
   *
   * Every place a face appears — nav, leaderboard, home, admin roster — uses
   * this, so an employee who hasn't uploaded a picture still reads as a
   * distinct person rather than a blank circle. The fallback colour is derived
   * from the name, so the same person is the same colour everywhere.
   */
  export let src: string | null | undefined = null;
  export let name: string | null | undefined = null;
  export let size = 36;
  /** Ring highlight, used for the signed-in user's own row. */
  export let ring = false;

  // Failed loads fall through to initials: a dead CDN link should degrade to
  // the fallback, not show a broken-image icon in the middle of the nav.
  let broken = false;
  $: if (src) broken = false;

  $: initials = (name ?? '')
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? '')
    .join('') || '?';

  // Hash the name to a hue so colours are stable across sessions and pages.
  $: hue = (() => {
    const s = (name ?? '?').trim().toLowerCase();
    let h = 0;
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 360;
    return h;
  })();
</script>

{#if src && !broken}
  <img
    class="avatar"
    class:ring
    {src}
    alt={name ?? 'Profile picture'}
    style="width:{size}px;height:{size}px"
    on:error={() => (broken = true)}
  />
{:else}
  <span
    class="avatar fallback"
    class:ring
    aria-label={name ?? 'Profile picture'}
    style="width:{size}px;height:{size}px;font-size:{Math.max(10, Math.round(size * 0.38))}px;
           background:hsl({hue} 45% 32%); color:hsl({hue} 85% 88%)"
  >{initials}</span>
{/if}

<style>
  .avatar {
    border-radius: 50%;
    flex-shrink: 0;
    object-fit: cover;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: var(--surface2);
    border: 1px solid var(--border);
  }
  .fallback { font-weight: 700; letter-spacing: 0.02em; user-select: none; }
  .ring { border: 2px solid var(--accent); }
</style>
