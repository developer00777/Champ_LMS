<script lang="ts">
	import { adminApi } from '$lib/api/client';

	let moduleId = $state('');
	let episodeTitle = $state('');
	let sequenceOrder = $state(1);
	let file: File | null = $state(null);
	let uploading = $state(false);
	let uploadProgress = $state(0);
	let status = $state('');
	let episodeId = $state('');

	async function handleFileChange(e: Event) {
		file = (e.target as HTMLInputElement).files?.[0] ?? null;
	}

	async function upload() {
		if (!file || !moduleId || !episodeTitle) return;
		uploading = true;
		status = 'Creating episode record...';

		try {
			// 1. Create episode record
			const ep = await adminApi.addEpisode(moduleId, {
				title: episodeTitle,
				sequence_order: sequenceOrder,
			});
			episodeId = ep.id;

			// 2. Get S3 presigned URL
			status = 'Getting upload URL...';
			const { upload_url, fields } = await adminApi.getPresignUrl(ep.id);

			// 3. Upload directly to S3 via multipart form
			status = 'Uploading to S3...';
			const formData = new FormData();
			Object.entries(fields).forEach(([k, v]) => formData.append(k, v));
			formData.append('file', file);

			await fetch(upload_url, { method: 'POST', body: formData });

			status = '✅ Upload complete! MediaConvert is processing your video. Episode will be ready in a few minutes.';
		} catch (e: any) {
			status = '❌ Error: ' + e.message;
		} finally {
			uploading = false;
			uploadProgress = 0;
		}
	}
</script>

<svelte:head><title>Upload Video — Admin</title></svelte:head>

<div class="page">
	<a href="/admin" class="back">← Admin</a>
	<h1>Upload Video</h1>

	<div class="form-card">
		<div class="form-group">
			<label>Module ID *</label>
			<input bind:value={moduleId} placeholder="Paste module UUID here" />
		</div>
		<div class="form-group">
			<label>Episode Title *</label>
			<input bind:value={episodeTitle} placeholder="e.g. How to Handle Sales Objections" />
		</div>
		<div class="form-group">
			<label>Episode Order</label>
			<input type="number" bind:value={sequenceOrder} min="1" />
		</div>
		<div class="form-group">
			<label>Video File (MP4) *</label>
			<div class="file-drop">
				<input type="file" accept="video/mp4,video/*" onchange={handleFileChange} id="file-input" />
				<label for="file-input" class="file-label">
					{file ? file.name : '📁 Click to select MP4 file'}
				</label>
			</div>
		</div>

		{#if status}
			<div class="status" class:success={status.startsWith('✅')} class:error={status.startsWith('❌')}>
				{status}
			</div>
		{/if}

		<button
			class="btn-primary"
			onclick={upload}
			disabled={uploading || !file || !moduleId || !episodeTitle}
		>
			{uploading ? 'Uploading...' : 'Upload Video'}
		</button>
	</div>

	<div class="info-box">
		<h3>How it works</h3>
		<ol>
			<li>Your video uploads directly to S3 (bypasses our server)</li>
			<li>AWS MediaConvert transcodes it to HLS (360p / 720p / 1080p)</li>
			<li>Episode status automatically updates to "ready" when done (~2-5 minutes)</li>
		</ol>
	</div>
</div>

<style>
	.page { max-width: 700px; margin: 0 auto; padding: 2rem; }
	.back { font-size: 0.85rem; color: #e50914; display: block; margin-bottom: 1rem; }
	h1 { font-size: 1.8rem; font-weight: 800; margin-bottom: 2rem; }

	.form-card { background: #1f1f1f; border-radius: 12px; padding: 2rem; margin-bottom: 1.5rem; }
	.form-group { margin-bottom: 1.25rem; }
	label { display: block; font-size: 0.82rem; color: #aaa; margin-bottom: 0.4rem; }
	input[type="text"], input[type="number"], input:not([type]) {
		width: 100%; background: #2a2a2a; border: 1px solid #444; color: #fff;
		padding: 0.6rem 0.8rem; border-radius: 6px; font-size: 0.9rem;
	}
	input:focus { outline: none; border-color: #e50914; }

	.file-drop { border: 2px dashed #444; border-radius: 8px; overflow: hidden; }
	.file-drop input[type="file"] { display: none; }
	.file-label {
		display: block; padding: 2rem; text-align: center;
		cursor: pointer; color: #888; font-size: 0.9rem;
		transition: background 0.15s;
	}
	.file-label:hover { background: rgba(255,255,255,0.04); }

	.status { padding: 0.75rem 1rem; border-radius: 6px; margin-bottom: 1rem; font-size: 0.9rem; background: rgba(255,255,255,0.05); }
	.status.success { background: rgba(34,197,94,0.1); color: #22c55e; }
	.status.error { background: rgba(229,9,20,0.1); color: #e50914; }

	.btn-primary { background: #e50914; color: #fff; border: none; padding: 0.75rem 2rem; border-radius: 6px; font-size: 1rem; font-weight: 700; cursor: pointer; width: 100%; }
	.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

	.info-box { background: rgba(255,255,255,0.04); border-radius: 8px; padding: 1.25rem 1.5rem; }
	h3 { font-size: 0.9rem; font-weight: 700; margin-bottom: 0.75rem; }
	ol { padding-left: 1.25rem; font-size: 0.85rem; color: #888; line-height: 1.8; }
</style>
