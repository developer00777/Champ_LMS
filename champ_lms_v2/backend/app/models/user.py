import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255))
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    # role: learner | admin | ld_lead
    role: Mapped[str] = mapped_column(String(50), default="learner")
    department: Mapped[str | None] = mapped_column(String(100))
    # Bunny Storage path for avatar, served via CDN
    avatar_bunny_path: Mapped[str | None] = mapped_column(String(500))
    points: Mapped[int] = mapped_column(Integer, default=0)
    streak_days: Mapped[int] = mapped_column(Integer, default=0)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    badges: Mapped[list["UserBadge"]] = relationship(back_populates="user", lazy="select")
    enrollments: Mapped[list["Enrollment"]] = relationship(back_populates="user", lazy="select")
