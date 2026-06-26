<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { adminApi } from '$lib/api/client';
	import type { ZoomSession } from '$lib/api/client';

	let sessions: ZoomSession[] = $state([]);
	let loading = $state(true);
	let building: string | null = $state(null);
	let showForm = $state(false);
	let form = $state({ topic: '', summary: '', transcript: '', recording_url: '' });
	let saving = $state(false);

	onMount(async () => {
		try { sessions = await adminApi.getZoomSessions(); }
		finally { loading = false; }
	});

	async function buildModule(sessionId: string) {
		building = sessionId;
		try {
			const res = await adminApi.buildModule(sessionId) as { title: string; episodes: number };
			alert(`Module created: "${res.title}" with ${res.episodes} episodes. Redirecting to admin...`);
			sessions = await adminApi.getZoomSessions();
		} catch (e: any) {
			alert('Error: ' + e.message);
		} finally {
			building = null;
		}
	}

	async function createSession() {
		saving = true;
		try {
			await adminApi.createZoomSession(form);
			sessions = await adminApi.getZoomSessions();
			showForm = false;
			form = { topic: '', summary: '', transcript: '', recording_url: '' };
		} catch (e: any) {
			alert(e.message);
		} finally {
			saving = false;
		}
	}
</script>

<svelte:head><title>Zoom Sessions — Admin</title></svelte:head>

<div class="page">
	<div class="header">
		<div>
			<a href="/admin" class="back">← Admin</a>
			<h1>Zoom → Module Builder</h1>
		</div>
		<button class="btn-primary" onclick={() => showForm = !showForm}>
			{showForm ? 'Cancel' : '+ Add Session'}
		</button>
	</div>

	{#if showForm}
		<div class="form-card">
			<h2>Add Zoom Session Manually</h2>
			<div class="form-group">
				<label>Topic *</label>
				<input bind:value={form.topic} placeholder="e.g. Sales Training - Q3 Pipeline" />
			</div>
			<div class="form-group">
				<label>AI Summary *</label>
				<textarea bind:value={form.summary} rows="4" placeholder="Paste Zoom AI companion summary..."></textarea>
			</div>
			<div class="form-group">
				<label>Transcript *</label>
				<textarea bind:value={form.transcript} rows="8" placeholder="Paste full meeting transcript..."></textarea>
			</div>
			<div class="form-group">
				<label>Recording URL (optional)</label>
				<input bind:value={form.recording_url} placeholder="https://zoom.us/rec/..." />
			</div>
			<button class="btn-primary" onclick={createSession} disabled={saving || !form.topic || !form.transcript}>
				{saving ? 'Saving...' : 'Save Session'}
			</button>
		</div>
	{/if}

	{#if loading}
		<p class="loading">Loading sessions...</p>
	{:else if sessions.length === 0}
		<p class="empty">No Zoom sessions yet. Add one above or wait for webhook events.</p>
	{:else}
		<div class="sessions">
			{#each sessions as session}
				<div class="session-card">
					<div class="session-info">
						<p class="topic">{session.topic || 'Untitled Session'}</p>
						<p class="meta">{new Date(session.created_at).toLocaleDateString()}</p>
						{#if session.processed}
							<span class="badge-done">✓ Module Created</span>
						{/if}
					</div>
					<div class="actions">
						{#if !session.processed}
							<button
								class="btn-build"
								onclick={() => buildModule(session.id)}
								disabled={building === session.id}
							>
								{building === session.id ? '⏳ Building...' : '▶ Build Module with AI'}
							</button>
						{:else if session.module_id}
							<button class="btn-view" onclick={() => goto(`/module/${session.module_id}`)}>
								View Module
							</button>
						{/if}
					</div>
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
	.page { max-width: 900px; margin: 0 auto; padding: 2rem; }
	.header { display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 2rem; }
	.back { font-size: 0.85rem; color: #e50914; display: block; margin-bottom: 0.5rem; }
	h1 { font-size: 1.8rem; font-weight: 800; }
	.loading, .empty { color: #888; }

	.form-card { background: #1f1f1f; border-radius: 12px; padding: 2rem; margin-bottom: 2rem; }
	h2 { font-size: 1.1rem; font-weight: 700; margin-bottom: 1.5rem; }
	.form-group { margin-bottom: 1rem; }
	label { display: block; font-size: 0.82rem; color: #aaa; margin-bottom: 0.4rem; }
	input, textarea { width: 100%; background: #2a2a2a; border: 1px solid #444; color: #fff; padding: 0.6rem 0.8rem; border-radius: 6px; font-size: 0.9rem; font-family: inherit; resize: vertical; }
	input:focus, textarea:focus { outline: none; border-color: #e50914; }

	.sessions { display: flex; flex-direction: column; gap: 0.75rem; }
	.session-card { background: #1f1f1f; border-radius: 10px; padding: 1.25rem 1.5rem; display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
	.topic { font-size: 1rem; font-weight: 600; margin-bottom: 0.25rem; }
	.meta { font-size: 0.8rem; color: #888; }
	.badge-done { font-size: 0.75rem; color: #22c55e; font-weight: 600; }

	.btn-primary { background: #e50914; color: #fff; border: none; padding: 0.6rem 1.4rem; border-radius: 6px; font-size: 0.9rem; font-weight: 600; cursor: pointer; }
	.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
	.btn-build { background: rgba(229,9,20,0.15); color: #e50914; border: 1px solid rgba(229,9,20,0.4); padding: 0.5rem 1.2rem; border-radius: 6px; font-size: 0.85rem; font-weight: 600; cursor: pointer; }
	.btn-build:disabled { opacity: 0.5; cursor: not-allowed; }
	.btn-view { background: rgba(255,255,255,0.1); color: #fff; border: none; padding: 0.5rem 1.2rem; border-radius: 6px; font-size: 0.85rem; cursor: pointer; }
</style>
