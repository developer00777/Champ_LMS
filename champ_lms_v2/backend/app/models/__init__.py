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
from app.models.test_series import TestSeries, TestAttempt, TestQuestion
# * ContentAccessRule: per-person module grants/revokes. Note this is unrelated
# * to models.team.Team, which is a gamification squad; content access keys off
# * the User.team org field an admin sets on the employee.
from app.models.content_access import ContentAccessRule
# * Daily engagement: rotating challenge pool + directed peer kudos. Streaks
# * stay in User/GamificationService rather than getting a second home here.
from app.models.daily import DailyChallenge, DailyChallengeCompletion, Kudos

__all__ = [
    "User", "Module", "Episode", "WatchProgress", "Enrollment",
    "ZoomSession", "Badge", "UserBadge", "Assessment", "AssessmentAttempt",
    "Recommendation", "XpEvent", "Quest", "UserQuest",
    "LearningPath", "UserPathProgress",
    "Team", "TeamChallenge", "TeamProgress",
    "SocialPost", "Notification",
    "TestSeries", "TestAttempt", "TestQuestion",
    "ContentAccessRule",
    "DailyChallenge", "DailyChallengeCompletion", "Kudos",
]

DOCUMENT_MODELS = [
    User, Module, Episode, WatchProgress, Enrollment,
    ZoomSession, Badge, UserBadge, Assessment, AssessmentAttempt,
    Recommendation, XpEvent, Quest, UserQuest,
    LearningPath, UserPathProgress,
    Team, TeamChallenge, TeamProgress,
    SocialPost, Notification,
    # * TestQuestion is an embedded BaseModel, not a Document — not registered here
    TestSeries, TestAttempt,
    ContentAccessRule,
    DailyChallenge, DailyChallengeCompletion, Kudos,
]
