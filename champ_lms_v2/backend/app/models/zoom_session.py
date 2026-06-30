import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base


class ZoomSession(Base):
    __tablename__ = "zoom_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    zoom_meeting_id: Mapped[str | None] = mapped_column(String(255))
    topic: Mapped[str | None] = mapped_column(String(500))
    summary: Mapped[str | None] = mapped_column(Text)
    transcript: Mapped[str | None] = mapped_column(Text)
    recording_download_url: Mapped[str | None] = mapped_column(Text)
    # Bunny Stream video ID after download + upload to Bunny
    bunny_video_id: Mapped[str | None] = mapped_column(String(255))
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    module_id: Mapped[str | None] = mapped_column(ForeignKey("modules.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
