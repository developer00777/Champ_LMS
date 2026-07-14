from app.models.user import User
from app.models.module import Module
from app.models.episode import Episode
from app.models.progress import WatchProgress
from app.models.enrollment import Enrollment
from app.models.zoom_session import ZoomSession
from app.models.gamification import Badge, UserBadge
from app.models.assessment import Assessment, AssessmentAttempt
from app.models.recommendation import Recommendation
from app.models.xp_event import XpEvent
from app.models.quest import Quest, UserQuest
from app.models.learning_path import LearningPath, UserPathProgress
from app.models.team import Team, TeamChallenge, TeamProgress
from app.models.social import SocialPost, Notification

__all__ = [
    "User", "Module", "Episode", "WatchProgress", "Enrollment",
    "ZoomSession", "Badge", "UserBadge", "Assessment", "AssessmentAttempt",
    "Recommendation", "XpEvent", "Quest", "UserQuest",
    "LearningPath", "UserPathProgress",
    "Team", "TeamChallenge", "TeamProgress",
    "SocialPost", "Notification",
]

DOCUMENT_MODELS = [
    User, Module, Episode, WatchProgress, Enrollment,
    ZoomSession, Badge, UserBadge, Assessment, AssessmentAttempt,
    Recommendation, XpEvent, Quest, UserQuest,
    LearningPath, UserPathProgress,
    Team, TeamChallenge, TeamProgress,
    SocialPost, Notification,
]
