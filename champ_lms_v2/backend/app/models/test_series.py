"""
Admin-authored test series, ingested from a Q&A PDF.

Distinct from Assessment: an Assessment is a quiz bolted to one module/episode,
auto-generated from a transcript. A TestSeries is standalone exam content the
admin uploads as a PDF, reviews, publishes, and scores people against — it need
not belong to any module.
"""
import uuid
from datetime import datetime, timezone
from beanie import Document
from pydantic import BaseModel, Field
from pymongo import IndexModel, ASCENDING, DESCENDING


# Question kinds. "mcq" keeps the historical shape (options + correct_index);
# "written" has no options and is graded by the AI against a model answer.
QUESTION_TYPE_MCQ = "mcq"
QUESTION_TYPE_WRITTEN = "written"
QUESTION_TYPES = (QUESTION_TYPE_MCQ, QUESTION_TYPE_WRITTEN)


class TestQuestion(BaseModel):
    """
    One question inside a TestSeries. Embedded, not a collection — questions are
    only ever read as part of their parent test.

    Two kinds:
      * mcq     — options plus correct_index. For questions parsed out of a PDF
                  where the answer key couldn't be matched, correct_index is
                  None and the question is unscorable until an admin fixes it
                  (see TestSeries.is_ready).
      * written — the learner types prose. Graded by the AI, which is why a
                  written question stays scorable with no answer key at all:
                  `expected_answer` helps a lot but the model can also assess
                  an answer on subject-matter merit when the source document
                  never supplied one.

    question_type defaults to mcq so documents and rows written before written
    questions existed keep their exact previous behaviour.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    question: str
    question_type: str = QUESTION_TYPE_MCQ
    options: list[str] = Field(default_factory=list)
    correct_index: int | None = None
    explanation: str | None = None
    # * free-form tag used to group results into weak areas, e.g. "Pricing"
    topic: str | None = None
    marks: int = 1

    # --- written questions only --------------------------------------------
    # The model answer / marking guidance. Optional: when the PDF had no answer
    # key, the AI grades on subject knowledge instead of against a reference.
    expected_answer: str | None = None
    # Soft guidance shown to the learner and given to the grader as context.
    max_words: int | None = None

    # --- per-question time limit -------------------------------------------
    # Seconds allowed for this question. None = no per-question limit (the
    # whole-test duration_minutes still applies if set).
    time_limit_seconds: int | None = None
    # True when time_limit_seconds came from the AI rather than being typed by
    # an admin, so the UI can show it as a suggestion they may override.
    time_limit_source: str | None = None  # "ai" | "manual" | None

    @property
    def is_written(self) -> bool:
        return self.question_type == QUESTION_TYPE_WRITTEN

    @property
    def scorable(self) -> bool:
        """
        Can this question contribute to a score?

        A written question always can — the AI grades it, with or without a
        reference answer. An MCQ needs a valid correct_index.
        """
        if self.is_written:
            return bool(self.question.strip())
        return (
            self.correct_index is not None
            and 0 <= self.correct_index < len(self.options)
            and len(self.options) >= 2
        )


class TestSeries(Document):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str | None = None
    category: str | None = None
    department: str | None = None  # None = visible to everyone
    questions: list[TestQuestion] = Field(default_factory=list)

    pass_threshold: int = 70  # percent
    duration_minutes: int | None = None  # None = untimed
    max_attempts: int | None = None  # None = unlimited
    shuffle_questions: bool = False

    # --- proctoring ---------------------------------------------------------
    # When on, the exam runs in a locked-down client (copy/paste/context menu
    # blocked, tab switching logged) and every attempt gets an AI integrity
    # verdict. Defaults to on: a company exam should be proctored unless the
    # admin deliberately opts out, and tests written before this field existed
    # inherit the default.
    proctoring_enabled: bool = True

    is_published: bool = False
    # * provenance from the PDF ingest, so the admin can see where this came from
    source_filename: str | None = None
    source_parser: str | None = None  # "pattern" | "ai" | "manual"

    created_by: str | None = None  # users.id
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def total_marks(self) -> int:
        return sum(q.marks for q in self.questions if q.scorable)

    @property
    def unscorable_count(self) -> int:
        return sum(1 for q in self.questions if not q.scorable)

    @property
    def is_ready(self) -> bool:
        """Publishable only when there's at least one question and all of them score."""
        return bool(self.questions) and self.unscorable_count == 0

    class Settings:
        name = "test_series"
        indexes = [
            IndexModel([("is_published", ASCENDING), ("department", ASCENDING)]),
            IndexModel([("created_at", DESCENDING)]),
        ]


# ==========================================================================
# Proctoring
# ==========================================================================
# Event kinds a proctored attempt can record. The client names the kind; the
# server keeps this whitelist so a tampered client can't invent categories that
# would confuse the AI proctor or the admin UI.
PROCTOR_EVENT_KINDS = (
    "tab_hidden",       # page became invisible (tab switch, minimise, app switch)
    "tab_visible",      # came back — pairs with tab_hidden to measure the gap
    "window_blur",      # focus left the window without the page hiding
    "window_focus",
    "copy_attempt",     # copy/cut on question or answer text, blocked
    "paste_attempt",    # paste into a written answer, blocked
    "context_menu",     # right-click, blocked
    "devtools_open",    # devtools-sized viewport gap or the shortcut pressed
    "shortcut_blocked", # print/save/select-all/view-source key combo
    "fullscreen_exit",  # left the exam's fullscreen
    "answer_burst",     # a long written answer appeared faster than typing allows
    "multi_session",    # the same attempt opened in a second tab/window
)


class ProctorEvent(BaseModel):
    """
    One integrity signal captured while the learner was taking the test.

    Embedded in the attempt rather than its own collection: events are only ever
    read alongside the attempt they belong to, and an exam produces tens of them,
    not thousands. `at_seconds` is the offset from the start of the attempt —
    more useful than a wall clock when reconstructing a timeline, and immune to a
    client whose system clock is wrong.
    """
    kind: str
    at_seconds: int = 0
    # How long the excursion lasted, for kinds that have a duration
    # (tab_hidden -> tab_visible). None for instantaneous events.
    duration_seconds: int | None = None
    # Which question was on screen when it happened, when the client knew.
    question_id: str | None = None
    # Short human-readable extra ("Ctrl+P", "pasted 480 chars"). Truncated
    # server-side — it is client-supplied text that an admin will read.
    detail: str | None = None


class ProctorReport(BaseModel):
    """
    The proctoring summary attached to a finished attempt: what happened, plus
    the AI's read on whether it looks like cheating.

    Counts are derived server-side from `events` so the admin UI and the AI
    prompt agree, and so a client can't send a flattering summary.
    """
    events: list[ProctorEvent] = Field(default_factory=list)
    # Denormalised tallies, keyed by event kind, for cheap list rendering.
    counts: dict[str, int] = Field(default_factory=dict)
    # Total seconds the learner spent with the exam not visible/focused.
    away_seconds: int = 0
    # Longest single excursion — one 4-minute absence matters more than
    # eight 2-second alt-tabs, and the average hides that.
    longest_away_seconds: int = 0
    # True when the client never sent any telemetry at all, which itself is
    # worth flagging: it means scripts were blocked or the submit API was called directly.
    telemetry_missing: bool = False

    # --- AI verdict --------------------------------------------------------
    # "clean" | "minor" | "suspicious" | "high_risk" | "unavailable"
    risk_level: str = "clean"
    # 0-100. Deterministic score from the signals; the AI can adjust it.
    risk_score: int = 0
    # One or two sentences an admin reads next to the result.
    summary: str | None = None
    # Bullet points naming the specific signals behind the verdict.
    findings: list[str] = Field(default_factory=list)
    # "rules" when only the deterministic scorer ran, "ai" when the model
    # reviewed the timeline, so nobody mistakes a fallback for a judgement.
    verdict_by: str = "rules"


class TestAttempt(Document):
    """
    One learner's submission. Stores the graded per-question breakdown so the
    admin can see exactly what was answered without re-deriving it, and caches
    the AI improvement analysis so repeat views don't re-bill the model.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    test_id: str  # references test_series.id
    user_id: str  # references users.id

    # answers[question_id] = selected option index (None = skipped).
    # MCQ only; written responses live in `text_answers` since they are prose.
    answers: dict[str, int | None] = Field(default_factory=dict)
    # text_answers[question_id] = what the learner typed for a written question
    text_answers: dict[str, str] = Field(default_factory=dict)
    # True when at least one written answer was graded by the model, so the
    # result screen can say the score involved AI judgement.
    ai_graded: bool = False
    # Written questions the grader could not reach (model down, bad response).
    # They score 0 but are flagged rather than silently counted as wrong.
    ungraded_question_ids: list[str] = Field(default_factory=list)
    # [{question_id, question, your_answer, correct_answer, correct, topic, marks}]
    breakdown: list[dict] = Field(default_factory=list)

    score: int = 0  # percent
    marks_earned: int = 0
    marks_total: int = 0
    correct_count: int = 0
    total_questions: int = 0
    passed: bool = False

    # * AI "areas of improvement" — generated once, on demand, then cached here
    ai_analysis: dict | None = None

    # * integrity telemetry + AI verdict. None for attempts made before
    # * proctoring existed and for tests with proctoring switched off — the UI
    # * must show "not proctored" for those, never "clean".
    proctoring: ProctorReport | None = None

    started_at: datetime | None = None
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "test_attempts"
        indexes = [
            IndexModel([("test_id", ASCENDING), ("user_id", ASCENDING)]),
            IndexModel([("user_id", ASCENDING), ("submitted_at", DESCENDING)]),
        ]
