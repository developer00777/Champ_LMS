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
            "HTTP-Referer": "https://learn.championsgroup.com",
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


ai_service = AIService()
