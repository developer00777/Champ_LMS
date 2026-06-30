import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Boolean, DateTime, Text, ForeignKey, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.db import Base


class Module(Base):
    __tablename__ = "modules"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(100))
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    target_roles: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    source_type: Mapped[str] = mapped_column(String(50), default="manual")  # manual|zoom|upload
    zoom_session_id: Mapped[str | None] = mapped_column(ForeignKey("zoom_sessions.id"))
    # Bunny Storage path for thumbnail, served via CDN with Optimizer
    thumbnail_bunny_path: Mapped[str | None] = mapped_column(String(500))
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    total_episodes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    episodes: Mapped[list["Episode"]] = relationship(
        back_populates="module", order_by="Episode.sequence_order", lazy="select"
    )
    enrollments: Mapped[list["Enrollment"]] = relationship(back_populates="module", lazy="select")
