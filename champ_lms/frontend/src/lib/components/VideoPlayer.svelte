<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import Hls from 'hls.js';
	import { startProgressSync, stopProgressSync } from '$lib/stores/player';

	let { streamUrl, episodeId, onEnded = null }: {
		streamUrl: string;
		episodeId: string;
		onEnded?: (() => void) | null;
	} = $props();

	let videoEl: HTMLVideoElement = $state(null as any);
	let hls: Hls | null = null;
	let autoAdvanceTimer: ReturnType<typeof setTimeout> | null = null;
	let countdown = $state(5);
	let showAutoAdvance = $state(false);

	onMount(() => {
		if (Hls.isSupported()) {
			hls = new Hls({ enableWorker: true });
			hls.loadSource(streamUrl);
			hls.attachMedia(videoEl);
		} else if (videoEl.canPlayType('application/vnd.apple.mpegurl')) {
			videoEl.src = streamUrl;
		}

		startProgressSync(episodeId, () => ({
			watched: videoEl?.currentTime ?? 0,
			total: videoEl?.duration ?? 0,
		}));

		videoEl.addEventListener('ended', handleEnded);
	});

	function handleEnded() {
		if (!onEnded) return;
		showAutoAdvance = true;
		countdown = 5;
		autoAdvanceTimer = setInterval(() => {
			countdown--;
			if (countdown <= 0) {
				clearInterval(autoAdvanceTimer!);
				showAutoAdvance = false;
				onEnded?.();
			}
		}, 1000);
	}

	function cancelAutoAdvance() {
		if (autoAdvanceTimer) clearInterval(autoAdvanceTimer);
		showAutoAdvance = false;
	}

	onDestroy(() => {
		hls?.destroy();
		stopProgressSync();
		if (autoAdvanceTimer) clearInterval(autoAdvanceTimer);
		videoEl?.removeEventListener('ended', handleEnded);
	});
</script>

<div class="player-wrapper">
	<video
		bind:this={videoEl}
		controls
		autoplay
		class="video"
	></video>

	{#if showAutoAdvance}
		<div class="auto-advance">
			<p>Next episode in <strong>{countdown}</strong>s</p>
			<div class="advance-actions">
				<button class="btn-primary" onclick={() => { cancelAutoAdvance(); onEnded?.(); }}>
					Play Now
				</button>
				<button class="btn-secondary" onclick={cancelAutoAdvance}>Cancel</button>
			</div>
		</div>
	{/if}
</div>

<style>
	.player-wrapper { position: relative; background: #000; border-radius: 8px; overflow: hidden; }
	.video { width: 100%; max-height: 70vh; display: block; }

	.auto-advance {
		position: absolute;
		bottom: 4rem;
		right: 2rem;
		background: rgba(0,0,0,0.85);
		border: 1px solid #444;
		border-radius: 8px;
		padding: 1.25rem 1.5rem;
		text-align: center;
		min-width: 240px;
	}
	.auto-advance p { margin-bottom: 1rem; font-size: 0.95rem; color: #ccc; }
	.advance-actions { display: flex; gap: 0.75rem; justify-content: center; }
	.btn-primary {
		background: #e50914; color: #fff; border: none;
		padding: 0.5rem 1.2rem; border-radius: 4px; font-weight: 600; cursor: pointer;
	}
	.btn-secondary {
		background: rgba(255,255,255,0.15); color: #fff; border: none;
		padding: 0.5rem 1.2rem; border-radius: 4px; font-weight: 600; cursor: pointer;
	}
</style>
