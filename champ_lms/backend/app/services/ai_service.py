import json
import anthropic
from app.core.config import get_settings

settings = get_settings()

ZOOM_MODULE_SCHEMA = {
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
    "required": ["title", "description", "category", "tags", "target_roles", "episodes"],
}

ZOOM_MODULE_PROMPT = """You are a learning design expert. Given the Zoom meeting transcript and AI summary below, create a structured microlearning module following these rules:
- Max 5 episodes per module
- Each episode covers ONE concept (2-10 min equivalent)
- Episode titles must be action-oriented ("How to...", "Understanding...")
- Generate 3 quiz questions per episode (multiple choice, 4 options each, with explanations)
- Tag with relevant skills and target roles

Transcript:
{transcript}

Summary:
{summary}

Return ONLY valid JSON matching the provided schema. No markdown, no explanation."""

QUIZ_PROMPT = """You are a learning design expert. Given the episode transcript below, generate exactly 3 multiple-choice quiz questions.

Episode title: {title}
Transcript:
{transcript}

Return ONLY valid JSON as an array of objects with: question, options (array of 4 strings), correct_index (0-3), explanation."""


async def generate_module_from_zoom(transcript: str, summary: str) -> dict:
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    prompt = ZOOM_MODULE_PROMPT.format(transcript=transcript, summary=summary)

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        tools=[{
            "name": "create_module",
            "description": "Create a structured learning module from Zoom transcript",
            "input_schema": ZOOM_MODULE_SCHEMA,
        }],
        tool_choice={"type": "tool", "name": "create_module"},
        messages=[{"role": "user", "content": prompt}],
    )

    for block in message.content:
        if block.type == "tool_use" and block.name == "create_module":
            return block.input

    raise ValueError("Claude did not return a valid module structure")


async def generate_quiz_from_transcript(title: str, transcript: str) -> list:
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    prompt = QUIZ_PROMPT.format(title=title, transcript=transcript)

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    text = message.content[0].text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)
