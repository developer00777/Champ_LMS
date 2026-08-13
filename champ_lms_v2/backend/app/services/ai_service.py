"""
AI service — OpenRouter for Zoom → Module pipeline and quiz generation.
OpenRouter gives access to 200+ models via one API key and OpenAI-compatible SDK.

Recommended cheap models for this task:
  google/gemini-flash-1.5       ~$0.075/1M tokens  (fast, good JSON)
  meta-llama/llama-3.1-8b-instruct:free  FREE tier (rate limited)
  deepseek/deepseek-chat        ~$0.14/1M tokens   (strong reasoning)
  google/gemini-2.0-flash-001   ~$0.10/1M tokens   (best quality/cost)

Set OPENROUTER_MODEL in .env to switch without code changes.
Default: google/gemini-flash-1.5
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
- correct_index is the 0-based index into options. If the document does not
  indicate the answer anywhere (inline or in an answer key), use null.
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
    "options": ["A", "B", "C", "D"],
    "correct_index": 0,
    "explanation": "string or null",
    "topic": "string",
    "marks": 1
  }}
]"""

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
        """Single chat completion via OpenRouter."""
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{OPENROUTER_BASE}/chat/completions",
                headers=self._headers(),
                json={
                    "model": self.settings.openrouter_model,
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,  # low temp for consistent JSON output
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

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
