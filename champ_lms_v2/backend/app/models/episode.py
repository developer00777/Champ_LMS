import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.db import Base


class Episode(Base):
    __tablename__ = "episodes"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    module_id: Mapped[str] = mapped_column(ForeignKey("modules.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    sequence_order: Mapped[int] = mapped_column(Integer, nullable=False)

    # Bunny Stream video ID (returned when video is created in library)
    bunny_video_id: Mapped[str | None] = mapped_column(String(255))
    # Bunny Stream GUID (same as bunny_video_id but stored explicitly for clarity)
    bunny_video_guid: Mapped[str | None] = mapped_column(String(255))

    # status: processing | ready | failed
    status: Mapped[str] = mapped_column(String(50), default="processing")

    # Transcript + AI outputs
    transcript: Mapped[str | None] = mapped_column(Text)
    ai_summary: Mapped[str | None] = mapped_column(Text)

    # Bunny Storage path for episode thumbnail
    thumbnail_bunny_path: Mapped[str | None] = mapped_column(String(500))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    module: Mapped["Module"] = relationship(back_populates="episodes")
