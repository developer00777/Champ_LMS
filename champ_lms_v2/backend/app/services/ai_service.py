"""
AI service — OpenRouter for Zoom → Module pipeline and quiz generation.
OpenRouter gives access to 200+ models via one API key and OpenAI-compatible SDK.

Recommended cheap models for this task (verified live on OpenRouter):
  google/gemini-2.5-flash       ~$0.30/1M in  (fast, good JSON, 1M ctx)  <- default
  google/gemini-2.5-flash-lite  ~$0.10/1M in  (cheapest, still solid JSON)
  deepseek/deepseek-chat        ~$0.26/1M in  (strong reasoning)

Set OPENROUTER_MODEL in .env to switch without code changes.

NOTE: OpenRouter retires model ids. A retired id makes every call 404, which
surfaces as an opaque failure on the endpoints that depend on it — so verify a
new id against https://openrouter.ai/api/v1/models before setting it.
"""
import json
import httpx
from app.core.config import get_settings

OPENROUTER_BASE = "https://openrouter.ai/api/v1"

ZOOM_MODULE_PROMPT = """You are a learning design expert. Given the Zoom meeting transcript and AI summary below, create a structured microlearning module.

Rules:
- Max 5 episodes per module
- Each episode covers ONE concept (2-10 min equivalent)
- Episode titles must be action-oriented ("How to...", "Understanding...", "Mastering...")
- Generate 3 quiz questions per episode (multiple choice, 4 options each, with explanations)
- Tag with relevant skills and target roles based on content
- Category must be one of: sales, leadership, onboarding, product, engineering, ops

Transcript:
{transcript}

Summary:
{summary}

Return ONLY a valid JSON object with this exact structure (no markdown, no explanation):
{{
  "title": "string",
  "description": "string",
  "category": "string",
  "tags": ["string"],
  "target_roles": ["string"],
  "episodes": [
    {{
      "title": "string",
      "description": "string",
      "key_points": ["string"],
      "duration_estimate_seconds": 300,
      "quiz_questions": [
        {{
          "question": "string",
          "options": ["A", "B", "C", "D"],
          "correct_index": 0,
          "explanation": "string"
        }}
      ]
    }}
  ]
}}"""

QUIZ_PROMPT = """You are a learning assessment expert. Given the episode transcript below, generate 5 multiple-choice quiz questions.

Rules:
- Questions must be answerable from the transcript alone
- One clearly correct answer per question with 3 plausible distractors
- Include a brief explanation for the correct answer
- Questions should progress from recall → application → analysis

Transcript:
{transcript}

Return ONLY a valid JSON array (no markdown, no explanation):
[
  {{
    "question": "string",
    "options": ["A", "B", "C", "D"],
    "correct_index": 0,
    "explanation": "string"
  }}
]"""

RECOMMENDATIONS_PROMPT = """You are a learning recommendation engine. Create 4 personalized content rows for a Netflix-style learning feed.

User profile:
- Role: {role}
- Department: {department}
- Points: {points}
- Streak: {streak_days} days

Available modules (ID | category | title):
{modules_list}

Return ONLY a valid JSON array (no markdown):
[
  {{"row_title": "Trending in Sales", "module_ids": ["id1", "id2", "id3", "id4"]}}
]

Each row needs 4-8 module IDs. Use only IDs from the list above."""

PDF_QUESTIONS_PROMPT = """You are an exam digitisation assistant. The text below was extracted from a PDF of quiz/exam questions. Convert it into structured multiple-choice questions.

Rules:
- Extract ONLY questions that are actually present. Never invent questions.
- Set "question_type" to "mcq" when the document offers answer choices, or
  "written" when the candidate is expected to write prose (e.g. "Explain...",
  "Describe...", "Discuss...", or any question with no choices listed).
- For "written" questions: use an empty options array, null correct_index, and
  put any model/sample answer the document provides in "expected_answer"
  (null if the document gives none). If the question states a word limit, put
  the number in "max_words".
- For "mcq" questions: correct_index is the 0-based index into options. If the
  document does not indicate the answer anywhere (inline or in an answer key),
  use null.
- Preserve the original wording of questions and options.
- If the document marks a topic/section/subject for a question, put it in "topic".
  Otherwise infer a short (1-3 word) topic from the question itself.
- If a question is true/false, use exactly ["True", "False"] as options.
- "marks" defaults to 1 unless the document states a mark/point value.

Document text:
{text}

Return ONLY a valid JSON array (no markdown, no commentary):
[
  {{
    "question": "string",
    "question_type": "mcq",
    "options": ["A", "B", "C", "D"],
    "correct_index": 0,
    "explanation": "string or null",
    "expected_answer": null,
    "max_words": null,
    "topic": "string",
    "marks": 1
  }}
]"""

GRADE_WRITTEN_PROMPT = """You are marking a written exam answer. Award marks out of {marks}.

Question: {question}
Topic: {topic}
{reference_block}
Learner's answer:
\"\"\"
{answer}
\"\"\"

Rules:
- Mark on substance, not length, spelling or phrasing. A short correct answer
  scores full marks.
- {reference_rule}
- Award partial marks for a partially correct answer; be specific in "feedback"
  about what was missing.
- An empty, irrelevant, or copy-of-the-question answer scores 0.
- Never award more than {marks} marks or less than 0.
- "correct" is true only when the answer is substantially right (>= 60% of marks).
- "feedback" is 1-2 sentences addressed to the learner as "you".

Return ONLY a valid JSON object (no markdown, no commentary):
{{
  "marks_awarded": 0,
  "correct": false,
  "feedback": "string",
  "model_answer": "a brief correct answer, for the learner's review"
}}"""

SUGGEST_TIME_LIMITS_PROMPT = """You are setting per-question time limits for an exam. For each question below, decide how many seconds a prepared candidate needs.

Guidance:
- A simple recall multiple-choice question: 30-60 seconds.
- Multiple choice needing a calculation or reasoning: 60-150 seconds.
- A short written answer: 120-300 seconds.
- A long/essay written answer: 300-900 seconds.
- Scale with the marks available and the reading length of the question.
- Be realistic, not generous: these are limits, not targets.

Questions (index | type | marks | question text):
{questions_block}

Return ONLY a valid JSON array with one entry per question, in the same order
(no markdown, no commentary):
[
  {{"index": 0, "seconds": 60, "why": "short recall MCQ"}}
]"""

PROCTOR_REVIEW_PROMPT = """You are an exam proctor reviewing the integrity of one online test attempt. Decide how likely it is that this candidate cheated.

You are given only behavioural telemetry from the exam page — there is no camera
and no screen recording. Judge intent from the pattern, and be fair: an honest
candidate on a real laptop generates some noise.

Attempt duration: {elapsed_label}
Time with the exam not visible or not focused: {away_seconds}s total, longest single absence {longest_away_seconds}s
Event tallies: {counts_label}
Telemetry missing: {telemetry_missing}

Event timeline (mm:ss from the start of the attempt):
{timeline}

Written answers on this attempt:
{answer_profile}

A deterministic rule-based pass already scored this {rules_risk_score}/100 and found:
{rules_findings}

How to weigh the signals:
- Innocent by itself: one or two brief tab switches, a right-click, a blocked
  Ctrl+A, exiting fullscreen once. Laptops get notifications and people adjust
  windows.
- Meaningful: repeatedly leaving the exam, especially a long absence immediately
  before a hard question is answered, or absences that cluster on high-mark
  questions.
- Strong: a long written answer that appeared as a burst rather than typed;
  paste attempts into an answer field; developer tools opening; the same exam
  open in two windows.
- Correlate timing with content. A 200-word answer submitted right after a
  90-second absence is a very different story from the same answer typed steadily.
- If telemetry is missing entirely, say the attempt could not be monitored. Do
  not call it clean, and do not call it cheating either.

Scoring:
- 0-14 "clean": nothing meaningful.
- 15-39 "minor": ordinary noise, no evidence of misconduct.
- 40-69 "suspicious": a pattern that a human should look at.
- 70-100 "high_risk": strong behavioural evidence of outside help.

Write for an L&D administrator who must decide whether to act. Never state as
fact something the telemetry only suggests — say "consistent with" rather than
"the candidate did". Never name a candidate; you have not been told who this is.

Return ONLY a valid JSON object (no markdown, no commentary):
{{
  "risk_score": 0,
  "risk_level": "clean",
  "summary": "1-2 sentences an administrator reads next to the score",
  "findings": ["specific, evidence-anchored observations; [] if there are none"]
}}"""


COHORT_COACHING_PROMPT = """You are advising an L&D administrator on how to coach a team after a test. Base everything on the results below.

Test: {test_title} (pass mark {pass_threshold}%)
Attempts: {attempt_count} | Passed: {pass_count} | Average score: {average_score}%

Topic accuracy across everyone (worst first):
{cohort_block}

Individual results (name | score | pass/fail | weakest topics):
{learner_block}

Rules:
- Ground every point in the numbers above. Never invent a weakness.
- "cohort_summary" is 2-3 sentences to the administrator about how the group did.
- "group_actions" are things to run for the whole team (a refresher, a
  walkthrough of one topic), each specific enough to schedule.
- "per_learner" covers only people who need attention (failed, or scored well
  below the group). For each, "message_to_learner" is written so the admin can
  send it to that person as-is: direct, encouraging, and specific about what to
  study.
- Omit anyone who did fine — a coaching list that includes everyone is noise.
- If the whole group did well, say so, keep per_learner empty, and suggest a
  stretch topic.

Return ONLY a valid JSON object (no markdown, no commentary):
{{
  "cohort_summary": "string",
  "weakest_topics": [{{"topic": "string", "accuracy": 50, "why_it_matters": "string"}}],
  "group_actions": ["string"],
  "per_learner": [
    {{
      "user_id": "string",
      "full_name": "string",
      "score": 50,
      "focus": "string",
      "message_to_learner": "string"
    }}
  ]
}}"""

IMPROVEMENT_PROMPT = """You are a performance coach reviewing a learner's test result. Identify concrete areas of improvement.

Test: {test_title}
Learner: {learner_name} ({role} in {department})
Score: {score}% ({correct_count} of {total_questions} correct) — {verdict}

Per-question results (topic | correct? | question | their answer | correct answer):
{results_block}

Topic accuracy summary:
{topic_block}

Rules:
- Ground every claim in the questions they actually got wrong. Never invent weaknesses.
- "weak_areas" must be ordered worst-first, and only include topics with real errors.
- "recommendations" are specific and actionable ("Practice discounting scripts
  where the buyer anchors first"), never generic ("study more").
- "summary" is 2-3 sentences, addressed to the learner as "you", honest but constructive.
- If they scored perfectly, say so, leave weak_areas empty, and suggest stretch goals.

Return ONLY a valid JSON object (no markdown, no commentary):
{{
  "summary": "string",
  "weak_areas": [
    {{"topic": "string", "accuracy": 50, "why": "string", "action": "string"}}
  ],
  "strengths": ["string"],
  "recommendations": ["string"],
  "suggested_focus": "string"
}}"""


class AIServiceError(RuntimeError):
    """An AI call failed, with a message safe and useful to show an admin."""


def _error_detail(resp: httpx.Response) -> str:
    """Best-effort human-readable detail from an OpenRouter error response."""
    try:
        body = resp.json()
    except ValueError:
        return resp.text[:200].strip() or "(empty response)"
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])[:200]
        if isinstance(err, str):
            return err[:200]
    return str(body)[:200]


def _extract_json_object(text: str) -> dict:
    """Extract first JSON object from model output, handling markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}") + 1
    return json.loads(text[start:end])


def _extract_json_array(text: str) -> list:
    """Extract first JSON array from model output, handling markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    start = text.find("[")
    end = text.rfind("]") + 1
    return json.loads(text[start:end])


class AIService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://champ-lms.up.railway.app",
            "X-Title": "Champ LMS",
        }

    async def _chat(self, prompt: str, max_tokens: int = 4096) -> str:
        """
        Single chat completion via OpenRouter.

        Raises AIServiceError with an actionable message. The generic httpx
        error is useless to whoever sees it downstream: a 404 here almost
        always means OPENROUTER_MODEL names a model OpenRouter has retired,
        which is a config fix, not a transient failure.
        """
        model = self.settings.openrouter_model
        async with httpx.AsyncClient(timeout=120) as client:
            try:
                resp = await client.post(
                    f"{OPENROUTER_BASE}/chat/completions",
                    headers=self._headers(),
                    json={
                        "model": model,
                        "max_tokens": max_tokens,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.3,  # low temp for consistent JSON output
                    },
                )
            except httpx.RequestError as exc:
                raise AIServiceError(f"Could not reach OpenRouter: {exc}") from exc

        if resp.status_code == 404:
            raise AIServiceError(
                f"OpenRouter does not recognise model '{model}' — it has most "
                "likely been retired. Set OPENROUTER_MODEL to a current id "
                "(e.g. google/gemini-2.5-flash); see openrouter.ai/api/v1/models."
            )
        if resp.status_code in (401, 403):
            raise AIServiceError(
                "OpenRouter rejected the API key (check OPENROUTER_API_KEY)."
            )
        if resp.status_code == 402:
            raise AIServiceError("OpenRouter credits exhausted — top up the account.")
        if resp.status_code == 429:
            raise AIServiceError("OpenRouter rate-limited this request; try again shortly.")
        if resp.status_code >= 400:
            raise AIServiceError(
                f"OpenRouter returned {resp.status_code}: {_error_detail(resp)}"
            )

        try:
            return resp.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise AIServiceError(
                f"Unexpected response shape from OpenRouter: {_error_detail(resp)}"
            ) from exc

    async def build_module_from_zoom(self, transcript: str, summary: str) -> dict:
        """Convert a Zoom transcript into a structured module JSON."""
        prompt = ZOOM_MODULE_PROMPT.format(transcript=transcript[:12000], summary=summary)
        text = await self._chat(prompt, max_tokens=4096)
        return _extract_json_object(text)

    async def generate_quiz(self, transcript: str) -> list[dict]:
        """Generate quiz questions from an episode transcript."""
        prompt = QUIZ_PROMPT.format(transcript=transcript[:8000])
        text = await self._chat(prompt, max_tokens=2048)
        return _extract_json_array(text)

    async def generate_personalized_rows(
        self, user_profile: dict, available_modules: list[dict]
    ) -> list[dict]:
        """Generate personalized recommendation rows for the home feed."""
        modules_list = "\n".join(
            f"{m['id']} | {m.get('category', '?')} | {m['title']}"
            for m in available_modules[:50]
        )
        prompt = RECOMMENDATIONS_PROMPT.format(
            role=user_profile.get("role", "learner"),
            department=user_profile.get("department", ""),
            points=user_profile.get("points", 0),
            streak_days=user_profile.get("streak_days", 0),
            modules_list=modules_list,
        )
        text = await self._chat(prompt, max_tokens=1024)
        return _extract_json_array(text)

    @property
    def enabled(self) -> bool:
        """False when no OpenRouter key is configured — callers fall back."""
        return bool(self.settings.openrouter_api_key)

    async def parse_questions_from_text(self, text: str) -> list[dict]:
        """
        Fallback PDF parser for layouts the deterministic parser can't handle.
        Returns raw dicts; the caller validates them into TestQuestion.
        """
        prompt = PDF_QUESTIONS_PROMPT.format(text=text[:14000])
        out = await self._chat(prompt, max_tokens=8192)
        return _extract_json_array(out)

    async def grade_written_answer(
        self,
        question: str,
        answer: str,
        marks: int,
        expected_answer: str | None = None,
        topic: str | None = None,
    ) -> dict:
        """
        Mark one written answer out of `marks`.

        Works with or without a reference answer: when the source document had
        no answer key, the model marks on subject-matter correctness instead.
        Returns {marks_awarded, correct, feedback, model_answer}; the caller
        clamps the marks and handles failure.
        """
        if expected_answer:
            reference_block = f"Reference answer (the marking guide):\n{expected_answer}\n"
            reference_rule = (
                "Compare against the reference answer, but accept any wording "
                "that conveys the same substance."
            )
        else:
            reference_block = (
                "No reference answer was supplied with this exam.\n"
            )
            reference_rule = (
                "No reference answer exists, so judge the answer on subject-matter "
                "correctness using your own knowledge of the topic. Be fair but "
                "rigorous, and say in the feedback what a correct answer needed."
            )

        prompt = GRADE_WRITTEN_PROMPT.format(
            question=question,
            topic=topic or "General",
            marks=marks,
            answer=answer[:4000],  # a long essay shouldn't blow the context
            reference_block=reference_block,
            reference_rule=reference_rule,
        )
        out = await self._chat(prompt, max_tokens=1024)
        return _extract_json_object(out)

    async def suggest_time_limits(self, questions: list[dict]) -> list[dict]:
        """
        Suggest a per-question time limit, in seconds.

        `questions` is [{question, question_type, marks}]. Returns
        [{index, seconds, why}] which the caller matches back by index.
        """
        questions_block = "\n".join(
            f"{i} | {q.get('question_type', 'mcq')} | {q.get('marks', 1)} marks | "
            f"{str(q.get('question', ''))[:300]}"
            for i, q in enumerate(questions)
        )
        prompt = SUGGEST_TIME_LIMITS_PROMPT.format(questions_block=questions_block)
        out = await self._chat(prompt, max_tokens=4096)
        return _extract_json_array(out)

    async def review_proctoring(
        self,
        timeline: str,
        counts: dict,
        away_seconds: int,
        longest_away_seconds: int,
        elapsed_seconds: int | None,
        rules_risk_score: int,
        rules_findings: list[str],
        answer_profile: str,
        telemetry_missing: bool,
    ) -> dict:
        """
        Ask the model to judge one attempt's integrity from its event timeline.

        Returns {risk_score, risk_level, summary, findings}. The caller clamps
        the score against the deterministic one — this verdict is advisory, and
        must never be the only thing standing between a learner and an
        accusation.
        """
        if elapsed_seconds:
            mins, secs = divmod(elapsed_seconds, 60)
            elapsed_label = f"{mins}m {secs}s"
        else:
            elapsed_label = "unknown"

        counts_label = ", ".join(
            f"{k}={v}" for k, v in sorted(counts.items())
        ) or "none"
        findings_label = "\n".join(f"- {f}" for f in rules_findings) or "- nothing"

        prompt = PROCTOR_REVIEW_PROMPT.format(
            timeline=timeline,
            counts_label=counts_label,
            away_seconds=away_seconds,
            longest_away_seconds=longest_away_seconds,
            elapsed_label=elapsed_label,
            rules_risk_score=rules_risk_score,
            rules_findings=findings_label,
            answer_profile=answer_profile,
            telemetry_missing="yes" if telemetry_missing else "no",
        )
        out = await self._chat(prompt, max_tokens=1024)
        return _extract_json_object(out)

    async def coach_cohort(
        self,
        test_title: str,
        pass_threshold: int,
        attempts: list[dict],
        cohort_topics: dict[str, dict],
    ) -> dict:
        """
        Turn a whole test's results into coaching guidance for the admin,
        including a ready-to-send message per learner who needs attention.
        """
        cohort_block = "\n".join(
            f"- {topic}: {s['correct']}/{s['total']} correct ({s['accuracy']}%)"
            for topic, s in sorted(cohort_topics.items(), key=lambda kv: kv[1]["accuracy"])
        ) or "- (no topics tagged)"

        learner_block = "\n".join(
            f"- {a.get('user_id')} | {a.get('full_name') or a.get('email') or 'Unknown'} | "
            f"{a.get('score', 0)}% | {'PASS' if a.get('passed') else 'FAIL'} | "
            f"weak: {', '.join(a.get('weak_topics') or []) or 'none'}"
            for a in attempts[:80]
        ) or "- (no attempts)"

        scores = [a.get("score", 0) for a in attempts]
        prompt = COHORT_COACHING_PROMPT.format(
            test_title=test_title,
            pass_threshold=pass_threshold,
            attempt_count=len(attempts),
            pass_count=sum(1 for a in attempts if a.get("passed")),
            average_score=round(sum(scores) / len(scores)) if scores else 0,
            cohort_block=cohort_block,
            learner_block=learner_block,
        )
        out = await self._chat(prompt, max_tokens=3072)
        return _extract_json_object(out)

    async def analyze_test_performance(
        self,
        test_title: str,
        learner: dict,
        score: int,
        correct_count: int,
        total_questions: int,
        passed: bool,
        breakdown: list[dict],
        topic_stats: dict[str, dict],
    ) -> dict:
        """
        Turn a graded attempt into areas-of-improvement guidance.
        Only the questions matter here, so the payload stays small and cheap.
        """
        results_block = "\n".join(
            f"- {b.get('topic') or 'General'} | "
            f"{'correct' if b.get('correct') else 'WRONG'} | "
            f"{b.get('question', '')[:160]} | "
            f"theirs: {b.get('your_answer') or '(skipped)'} | "
            f"correct: {b.get('correct_answer')}"
            for b in breakdown[:60]
        )
        topic_block = "\n".join(
            f"- {topic}: {s['correct']}/{s['total']} correct ({s['accuracy']}%)"
            for topic, s in sorted(topic_stats.items(), key=lambda kv: kv[1]["accuracy"])
        ) or "- (no topics tagged)"

        prompt = IMPROVEMENT_PROMPT.format(
            test_title=test_title,
            learner_name=learner.get("full_name") or "the learner",
            role=learner.get("role") or "learner",
            department=learner.get("department") or "unspecified department",
            score=score,
            correct_count=correct_count,
            total_questions=total_questions,
            verdict="PASSED" if passed else "DID NOT PASS",
            results_block=results_block,
            topic_block=topic_block,
        )
        out = await self._chat(prompt, max_tokens=2048)
        return _extract_json_object(out)


def fallback_analysis(
    score: int, passed: bool, topic_stats: dict[str, dict]
) -> dict:
    """
    Deterministic stand-in for analyze_test_performance when the AI is
    unavailable (no key, model error). Weakest topics by accuracy, so the
    learner always gets *something* actionable rather than an error.
    """
    ranked = sorted(topic_stats.items(), key=lambda kv: kv[1]["accuracy"])
    weak = [
        {
            "topic": topic,
            "accuracy": s["accuracy"],
            "why": f"You answered {s['correct']} of {s['total']} correctly in this area.",
            "action": f"Review the material on {topic} and retake the test.",
        }
        for topic, s in ranked
        if s["accuracy"] < 100
    ]
    strengths = [t for t, s in topic_stats.items() if s["accuracy"] == 100]
    return {
        "summary": (
            f"You scored {score}%{' and passed' if passed else ' and did not reach the pass mark'}. "
            + (
                f"Your weakest area was {weak[0]['topic']} ({weak[0]['accuracy']}%)."
                if weak
                else "You answered every question correctly."
            )
        ),
        "weak_areas": weak[:5],
        "strengths": strengths[:5],
        "recommendations": [w["action"] for w in weak[:3]]
        or ["Try a harder test series to keep progressing."],
        "suggested_focus": weak[0]["topic"] if weak else "Advanced material",
        "generated_by": "fallback",
    }


ai_service = AIService()
