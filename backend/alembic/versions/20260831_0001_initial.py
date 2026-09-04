"""Create V1 scene and generation tables.

Revision ID: 20260831_0001
Revises:
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260831_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scenes",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("owner_session_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("current_version_id", sa.String(length=48), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scenes_owner_session_id", "scenes", ["owner_session_id"])
    op.create_index("ix_scenes_current_version_id", "scenes", ["current_version_id"])

    op.create_table(
        "scene_versions",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("scene_id", sa.String(length=48), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.String(length=24), nullable=False),
        sa.Column("scene_json", sa.JSON(), nullable=False),
        sa.Column("original_prompt", sa.Text(), nullable=False),
        sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["scene_id"], ["scenes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scene_id", "version_number", name="uq_scene_version_number"),
    )
    op.create_index("ix_scene_versions_scene_created", "scene_versions", ["scene_id", "created_at"])

    op.create_table(
        "generation_jobs",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("owner_session_id", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column("prompt_template_version", sa.String(length=24), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("scene_id", sa.String(length=48), nullable=True),
        sa.Column("scene_version_id", sa.String(length=48), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_session_id", "idempotency_key", name="uq_generation_idempotency"),
    )
    op.create_index("ix_generation_jobs_owner_session_id", "generation_jobs", ["owner_session_id"])
    op.create_index("ix_generation_jobs_status", "generation_jobs", ["status"])
    op.create_index("ix_generation_jobs_scene_id", "generation_jobs", ["scene_id"])
    op.create_index("ix_generation_jobs_owner_created", "generation_jobs", ["owner_session_id", "created_at"])


def downgrade() -> None:
    op.drop_table("generation_jobs")
    op.drop_table("scene_versions")
    op.drop_table("scenes")
