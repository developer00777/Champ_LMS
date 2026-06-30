"""
AI service — Claude API for Zoom → Module pipeline and quiz generation.
Unchanged from v1 architecture; only AWS/CloudFront references removed.
"""
import json
import anthropic
from app.core.config import get_settings

MODULE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "category": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "target_roles": {"type": "array", "items": {"type": "string"}},
        "episodes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "key_points": {"type": "array", "items": {"type": "string"}},
                    "duration_estimate_seconds": {"type": "integer"},
                    "quiz_questions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "question": {"type": "string"},
                                "options": {"type": "array", "items": {"type": "string"}},
                                "correct_index": {"type": "integer"},
                                "explanation": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
    },
}

ZOOM_MODULE_PROMPT = """
You are a learning design expert. Given the Zoom meeting transcript and AI summary below,
create a structured microlearning module following these rules:
- Max 5 episodes per module
- Each episode covers ONE concept (2-10 min equivalent)
- Episode titles must be action-oriented ("How to...", "Understanding...", "Mastering...")
- Generate 3 quiz questions per episode (multiple choice, with explanations)
- Tag with relevant skills and target roles based on content
- Category must be one of: sales, leadership, onboarding, product, engineering, ops

Transcript:
{transcript}

Summary:
{summary}

Return a valid JSON object matching the provided schema.
"""

QUIZ_PROMPT = """
You are a learning assessment expert. Given the episode transcript below,
generate 5 multiple-choice quiz questions that test comprehension of key concepts.

Rules:
- Questions must be answerable from the transcript alone
- One clearly correct answer per question with 3 plausible distractors
- Include a brief explanation for the correct answer
- Questions should progress from recall → application → analysis

Transcript:
{transcript}

Return a JSON array of question objects with fields:
question, options (array of 4 strings), correct_index (0-3), explanation
"""


class AIService:
    def __init__(self) -> None:
        settings = get_settings()
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    async def build_module_from_zoom(self, transcript: str, summary: str) -> dict:
        """Call Claude to convert a Zoom transcript into a structured module JSON."""
        message = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            tools=[
                {
                    "name": "create_module",
                    "description": "Create a structured learning module from a Zoom transcript",
                    "input_schema": MODULE_SCHEMA,
                }
            ],
            tool_choice={"type": "tool", "name": "create_module"},
            messages=[
                {
                    "role": "user",
                    "content": ZOOM_MODULE_PROMPT.format(
                        transcript=transcript, summary=summary
                    ),
                }
            ],
        )

        for block in message.content:
            if block.type == "tool_use" and block.name == "create_module":
                return block.input

        raise ValueError("Claude did not return tool_use block")

    async def generate_quiz(self, transcript: str) -> list[dict]:
        """Generate quiz questions from an episode transcript."""
        message = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            messages=[
                {
                    "role": "user",
                    "content": QUIZ_PROMPT.format(transcript=transcript),
                }
            ],
        )
        text = message.content[0].text
        # Claude returns JSON array
        start = text.find("[")
        end = text.rfind("]") + 1
        return json.loads(text[start:end])

    async def generate_personalized_rows(self, user_profile: dict, available_modules: list[dict]) -> list[dict]:
        """Generate personalized recommendation rows for the home feed."""
        prompt = f"""
        You are a learning recommendation engine. Given the user profile and available modules,
        create 4 personalized content rows for a Netflix-style learning feed.

        User profile:
        - Role: {user_profile.get('role')}
        - Department: {user_profile.get('department')}
        - Points: {user_profile.get('points')}
        - Streak: {user_profile.get('streak_days')} days

        Available modules (IDs and categories):
        {json.dumps(available_modules[:50], indent=2)}

        Return a JSON array of rows:
        [{{"row_title": "string", "module_ids": ["id1", "id2", ...]}}]

        Row titles should be engaging ("Trending in Sales", "Recommended for You", etc.)
        Each row should have 4-8 module IDs.
        """

        message = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text
        start = text.find("[")
        end = text.rfind("]") + 1
        return json.loads(text[start:end])


ai_service = AIService()
