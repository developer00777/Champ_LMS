from app.models.user import User
from app.models.module import Module
from app.models.episode import Episode
from app.models.progress import WatchProgress
from app.models.enrollment import Enrollment
from app.models.zoom_session import ZoomSession
from app.models.gamification import Badge, UserBadge
from app.models.assessment import Assessment, AssessmentAttempt
from app.models.recommendation import Recommendation

__all__ = [
    "User", "Module", "Episode", "WatchProgress", "Enrollment",
    "ZoomSession", "Badge", "UserBadge", "Assessment", "AssessmentAttempt",
    "Recommendation",
]

DOCUMENT_MODELS = [
    User, Module, Episode, WatchProgress, Enrollment,
    ZoomSession, Badge, UserBadge, Assessment, AssessmentAttempt,
    Recommendation,
]
