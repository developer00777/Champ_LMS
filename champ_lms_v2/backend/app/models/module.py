import uuid
from datetime import datetime, timezone
from beanie import Document
from pydantic import BaseModel, Field
from pymongo import IndexModel, ASCENDING

# Kinds of thing that can sit on a course canvas, each backed by its own
# collection: video -> Episode, quiz -> Assessment, test -> TestSeries,
# notes -> CourseNote.
ITEM_VIDEO = "video"
ITEM_QUIZ = "quiz"
ITEM_TEST = "test"
ITEM_NOTES = "notes"
ITEM_KINDS = (ITEM_VIDEO, ITEM_QUIZ, ITEM_TEST, ITEM_NOTES)

# "classic" modules are the episode lists that predate the canvas and keep
# their own editor and player. "canvas" modules are built on the course canvas.
LAYOUT_CLASSIC = "classic"
LAYOUT_CANVAS = "canvas"

# "open": an empty audience means everyone, the historical rule every module
# created before the canvas relies on. "closed": an empty audience means nobody.
ACCESS_OPEN = "open"
ACCESS_CLOSED = "closed"


class CourseSection(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str


class CourseItem(BaseModel):
    """
    One entry in a canvas course's running order.

    The order lives here, on the module, rather than as a position field on
    each backing document: the canvas mixes four collections, and one list is
    the only thing that can say "the quiz comes after episode 2 and before the
    notes" without four sequence numbers that can disagree.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    kind: str  # one of ITEM_KINDS
    ref_id: str  # id in the backing collection
    section_id: str


class Module(Document):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    target_roles: list[str] | None = None
    created_by: str | None = None  # references users.id
    source_type: str = "manual"  # manual|zoom|upload
    zoom_session_id: str | None = None  # references zoom_sessions.id
    # Bunny Storage path for thumbnail, served via CDN with Optimizer
    thumbnail_bunny_path: str | None = None
    # Thumbnail studio (models/thumbnail.py): the image in Mongo, how it was
    # made, and for text designs the settings, so the admin can reopen and
    # edit them. Takes precedence over thumbnail_bunny_path.
    thumbnail_id: str | None = None
    thumbnail_source: str | None = None  # upload | ai | text
    thumbnail_design: dict | None = None
    is_published: bool = False
    total_episodes: int = 0
    # module_type distinguishes the two training tracks:
    # onboarding = department-specific induction; upskilling = domain skill growth.
    module_type: str = "upskilling"  # onboarding | upskilling
    # target_department scopes onboarding modules to one of the company departments.
    target_department: str | None = None

    # --- Audience (see app/services/content_access.py) ----------------------
    # Empty/None on every dimension = open to everyone, which is what modules
    # created before this feature look like. Setting any of them restricts the
    # module to people matching at least ONE populated dimension.
    audience_teams: list[str] | None = None
    audience_departments: list[str] | None = None
    # Teams/users for whom this module is required rather than merely
    # available. Being required implies access, so a required audience is also
    # honoured by the visibility check.
    required_for_teams: list[str] | None = None
    # Admin-configurable point multiplier (1.0 = baseline). Used by the scoring engine
    # to make harder / longer / certification modules worth more points.
    points_weight: float = 1.0

    # --- Course canvas -------------------------------------------------------
    layout: str = LAYOUT_CLASSIC
    # Canvas courses are created closed, so nothing is visible until an admin
    # grants it. Existing modules keep "open" and behave exactly as before.
    access_mode: str = ACCESS_OPEN
    sections: list[CourseSection] = Field(default_factory=list)
    items: list[CourseItem] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "modules"
        indexes = [
            IndexModel([("is_published", ASCENDING), ("created_at", ASCENDING)]),
            IndexModel([("category", ASCENDING)]),
        ]
