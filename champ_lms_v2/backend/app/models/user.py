import uuid
from datetime import datetime, timezone
from beanie import Document
from pydantic import Field
from pymongo import IndexModel, ASCENDING


class User(Document):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: str
    full_name: str | None = None
    hashed_password: str
    # role: learner | admin | ld_lead
    role: str = "learner"
    department: str | None = None
    # Bunny Storage path for avatar, served via CDN
    avatar_bunny_path: str | None = None
    points: int = 0
    xp: int = 0
    level: int = 1
    streak_days: int = 0
    longest_streak: int = 0
    streak_freezes: int = 3
    last_activity_at: datetime | None = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def update_level(self) -> bool:
        """Recompute level from XP. Returns True if the user levelled up."""
        import math
        new_level = max(1, int(math.floor(math.sqrt(self.xp / 50))))
        level_up = new_level > self.level
        self.level = new_level
        return level_up

    @staticmethod
    def compute_level(xp: int) -> int:
        import math
        return max(1, int(math.floor(math.sqrt(xp / 50))))

    @staticmethod
    def tier_name(level: int) -> str:
        tiers = {1: "Rookie", 2: "Regular", 3: "Pro", 4: "All-Star", 5: "Champion"}
        return tiers.get(level, "Legend")

    class Settings:
        name = "users"
        indexes = [
            IndexModel([("email", ASCENDING)], unique=True),
        ]
