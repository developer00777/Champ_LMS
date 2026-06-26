"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2026-06-26

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("cognito_sub", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255)),
        sa.Column("role", sa.String(100)),
        sa.Column("department", sa.String(100)),
        sa.Column("avatar_url", sa.Text),
        sa.Column("points", sa.Integer, nullable=False, server_default="0"),
        sa.Column("streak_days", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_activity_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cognito_sub"),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "modules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("category", sa.String(100)),
        sa.Column("tags", postgresql.ARRAY(sa.String)),
        sa.Column("target_roles", postgresql.ARRAY(sa.String)),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("source_type", sa.String(50), server_default="manual"),
        sa.Column("zoom_session_id", postgresql.UUID(as_uuid=True)),
        sa.Column("thumbnail_url", sa.Text),
        sa.Column("is_published", sa.Boolean, server_default="false"),
        sa.Column("total_episodes", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
    )

    op.create_table(
        "episodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("module_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("duration_seconds", sa.Integer),
        sa.Column("sequence_order", sa.Integer, nullable=False),
        sa.Column("s3_raw_key", sa.Text),
        sa.Column("hls_manifest_key", sa.Text),
        sa.Column("thumbnail_key", sa.Text),
        sa.Column("status", sa.String(50), server_default="processing"),
        sa.Column("transcript", sa.Text),
        sa.Column("ai_summary", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["module_id"], ["modules.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "watch_progress",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("episode_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("watched_seconds", sa.Integer, server_default="0"),
        sa.Column("total_seconds", sa.Integer),
        sa.Column("completed", sa.Boolean, server_default="false"),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("last_watched_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "episode_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "enrollments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("module_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("completion_percentage", sa.Float, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "module_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["module_id"], ["modules.id"]),
    )

    op.create_table(
        "zoom_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("zoom_meeting_id", sa.String(255)),
        sa.Column("topic", sa.String(500)),
        sa.Column("summary", sa.Text),
        sa.Column("transcript", sa.Text),
        sa.Column("recording_url", sa.Text),
        sa.Column("processed", sa.Boolean, server_default="false"),
        sa.Column("module_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["module_id"], ["modules.id"]),
    )

    op.create_table(
        "badges",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("icon_url", sa.Text),
        sa.Column("criteria", postgresql.JSONB),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "user_badges",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("badge_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("earned_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "badge_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["badge_id"], ["badges.id"]),
    )

    op.create_table(
        "assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("module_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("episode_id", postgresql.UUID(as_uuid=True)),
        sa.Column("title", sa.String(500)),
        sa.Column("questions", postgresql.JSONB, nullable=False),
        sa.Column("pass_threshold", sa.Integer, server_default="70"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["module_id"], ["modules.id"]),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes.id"]),
    )

    op.create_table(
        "assessment_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("score", sa.Integer),
        sa.Column("passed", sa.Boolean),
        sa.Column("answers", postgresql.JSONB),
        sa.Column("attempted_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessments.id"]),
    )

    op.create_table(
        "recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rows", postgresql.JSONB, nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )

    # Seed default badges
    op.execute("""
        INSERT INTO badges (name, description, criteria) VALUES
        ('First Watch', 'Completed your first episode', '{"type": "complete_episode", "count": 1}'),
        ('5-Day Streak', 'Watched for 5 days in a row', '{"type": "streak_days", "count": 5}'),
        ('Module Champion', 'Completed your first module', '{"type": "complete_module", "count": 1}'),
        ('Quiz Ace', 'Passed your first quiz', '{"type": "pass_quiz", "count": 1}')
    """)


def downgrade() -> None:
    op.drop_table("recommendations")
    op.drop_table("assessment_attempts")
    op.drop_table("assessments")
    op.drop_table("user_badges")
    op.drop_table("badges")
    op.drop_table("zoom_sessions")
    op.drop_table("enrollments")
    op.drop_table("watch_progress")
    op.drop_table("episodes")
    op.drop_table("modules")
    op.drop_table("users")
