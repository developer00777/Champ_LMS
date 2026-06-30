import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    module_id: Mapped[str] = mapped_column(ForeignKey("modules.id"))
    episode_id: Mapped[str | None] = mapped_column(ForeignKey("episodes.id"))
    title: Mapped[str | None] = mapped_column(String(500))
    # [{question, options[], correct_index, explanation}]
    questions: Mapped[list] = mapped_column(JSONB, nullable=False)
    pass_threshold: Mapped[int] = mapped_column(Integer, default=70)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class AssessmentAttempt(Base):
    __tablename__ = "assessment_attempts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id"))
    score: Mapped[int | None] = mapped_column(Integer)
    passed: Mapped[bool | None] = mapped_column(Boolean)
    answers: Mapped[list | None] = mapped_column(JSONB)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
