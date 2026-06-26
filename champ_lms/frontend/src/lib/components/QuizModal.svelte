<script lang="ts">
	import { assessmentApi } from '$lib/api/client';
	import type { Assessment } from '$lib/api/client';

	let { assessment, onClose, onComplete }: {
		assessment: Assessment;
		onClose: () => void;
		onComplete: (passed: boolean) => void;
	} = $props();

	let answers: Record<string, number> = $state({});
	let submitted = $state(false);
	let result: { score: number; passed: boolean } | null = $state(null);
	let loading = $state(false);

	async function submit() {
		if (Object.keys(answers).length < assessment.questions.length) return;
		loading = true;
		try {
			const res = await assessmentApi.attempt(assessment.id, answers);
			result = { score: res.score, passed: res.passed };
			submitted = true;
		} catch (e: any) {
			alert(e.message);
		} finally {
			loading = false;
		}
	}

	function finish() {
		onComplete(result?.passed ?? false);
		onClose();
	}
</script>

<div class="backdrop" role="dialog" aria-modal="true">
	<div class="modal">
		<div class="modal-header">
			<h2>{assessment.title || 'Episode Quiz'}</h2>
			{#if !submitted}
				<button class="close" onclick={onClose}>✕</button>
			{/if}
		</div>

		{#if !submitted}
			<div class="questions">
				{#each assessment.questions as q, i}
					<div class="question">
						<p class="q-text"><strong>Q{i + 1}.</strong> {q.question}</p>
						<div class="options">
							{#each q.options as opt, j}
								<label class="option" class:selected={answers[i] === j}>
									<input type="radio" name="q{i}" value={j}
										bind:group={answers[i]} />
									{opt}
								</label>
							{/each}
						</div>
					</div>
				{/each}
			</div>
			<button class="btn-primary submit" onclick={submit} disabled={loading}>
				{loading ? 'Grading...' : 'Submit Quiz'}
			</button>
		{:else}
			<div class="result">
				<div class="score-circle" class:passed={result?.passed}>
					{result?.score}%
				</div>
				<p>{result?.passed ? '🎉 Passed!' : '❌ Not quite'}</p>
				<p class="sub">Pass threshold: {assessment.pass_threshold}%</p>

				<div class="review">
					{#each assessment.questions as q, i}
						<div class="review-item" class:correct={answers[i] === q.correct_index}>
							<p><strong>Q{i + 1}.</strong> {q.question}</p>
							<p class="your-answer">Your answer: {q.options[answers[i]]} {answers[i] === q.correct_index ? '✓' : '✗'}</p>
							{#if answers[i] !== q.correct_index}
								<p class="correct-answer">Correct: {q.options[q.correct_index]}</p>
							{/if}
							<p class="explanation">{q.explanation}</p>
						</div>
					{/each}
				</div>

				<button class="btn-primary" onclick={finish}>Continue</button>
			</div>
		{/if}
	</div>
</div>

<style>
	.backdrop {
		position: fixed; inset: 0;
		background: rgba(0,0,0,0.85);
		display: flex; align-items: center; justify-content: center;
		z-index: 200;
		padding: 2rem;
	}
	.modal {
		background: #1f1f1f;
		border-radius: 12px;
		max-width: 640px;
		width: 100%;
		max-height: 85vh;
		overflow-y: auto;
		padding: 2rem;
	}
	.modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; }
	h2 { font-size: 1.3rem; font-weight: 700; }
	.close { background: none; border: none; color: #aaa; font-size: 1.2rem; cursor: pointer; }

	.question { margin-bottom: 1.5rem; }
	.q-text { margin-bottom: 0.75rem; line-height: 1.5; }
	.options { display: flex; flex-direction: column; gap: 0.5rem; }
	.option {
		display: flex; align-items: center; gap: 0.75rem;
		padding: 0.6rem 1rem;
		border: 1px solid #333;
		border-radius: 6px;
		cursor: pointer;
		transition: border-color 0.15s, background 0.15s;
		font-size: 0.9rem;
	}
	.option:hover { border-color: #666; background: rgba(255,255,255,0.05); }
	.option.selected { border-color: #e50914; background: rgba(229,9,20,0.1); }
	.option input { display: none; }

	.submit { width: 100%; margin-top: 1rem; padding: 0.75rem; font-size: 1rem; }
	.btn-primary {
		background: #e50914; color: #fff; border: none;
		padding: 0.6rem 1.4rem; border-radius: 4px; font-weight: 600; cursor: pointer;
	}
	.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }

	.result { text-align: center; }
	.score-circle {
		width: 100px; height: 100px;
		border-radius: 50%;
		border: 4px solid #e50914;
		display: flex; align-items: center; justify-content: center;
		font-size: 1.5rem; font-weight: 800;
		margin: 0 auto 1rem;
	}
	.score-circle.passed { border-color: #22c55e; color: #22c55e; }
	.sub { color: #aaa; font-size: 0.85rem; margin-bottom: 1.5rem; }

	.review { text-align: left; margin: 1.5rem 0; }
	.review-item { padding: 1rem; border-radius: 6px; margin-bottom: 0.75rem; background: rgba(255,255,255,0.04); }
	.review-item.correct { background: rgba(34, 197, 94, 0.08); }
	.your-answer { font-size: 0.85rem; color: #aaa; margin-top: 0.3rem; }
	.correct-answer { font-size: 0.85rem; color: #22c55e; }
	.explanation { font-size: 0.8rem; color: #888; margin-top: 0.3rem; font-style: italic; }
</style>
