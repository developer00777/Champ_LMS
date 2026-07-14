<script lang="ts">
  import { api, type SharePayload } from '$lib/api/client';

  export let type: string | null = null;
  export let refId: string | null = null;
  export let share: SharePayload | null = null;
  export let buttonText = 'Share Achievement';

  let loading = false;
  let localShare = share;
  let copied = false;

  async function load() {
    if (localShare || !type || !refId) return;
    loading = true;
    try {
      localShare = await api.shareAchievement(type, refId);
    } finally {
      loading = false;
    }
  }

  async function copy() {
    if (!localShare) await load();
    if (!localShare) return;
    const text = `${localShare.share_text} ${localShare.share_url}`;
    try {
      await navigator.clipboard.writeText(text);
    } catch {}
    copied = true;
    setTimeout(() => (copied = false), 2000);
  }
</script>

<div class="share-card" class:loaded={Boolean(localShare)}>
  {#if localShare}
    <div class="icon">🏆</div>
    <p class="text">{localShare.share_text}</p>
    <button class="btn-ghost copy-btn" on:click={copy}>
      {copied ? 'Copied!' : 'Copy Share Text'}
    </button>
  {:else}
    <button class="btn-primary" on:click={load} disabled={loading}>
      {loading ? 'Loading…' : buttonText}
    </button>
  {/if}
</div>

<style>
  .share-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 1.25rem;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.75rem;
    text-align: center;
  }
  .share-card.loaded {
    border-color: var(--gold);
  }
  .icon {
    font-size: 2.5rem;
  }
  .text {
    font-size: 0.95rem;
    line-height: 1.45;
    color: var(--text-secondary);
  }
  .copy-btn {
    width: 100%;
  }
</style>
