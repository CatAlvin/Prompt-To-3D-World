"""V2 scene planning, persistent stages, version metadata and catalog tables.

Revision ID: 20260831_0002
Revises: 20260831_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260831_0002"
down_revision: str | None = "20260831_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("scenes", sa.Column("current_final_version_id", sa.String(48), nullable=True))
    op.add_column("scenes", sa.Column("latest_draft_version_id", sa.String(48), nullable=True))
    op.add_column("scenes", sa.Column("thumbnail_ref", sa.String(255), nullable=True))
    op.add_column("scenes", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_scenes_current_final_version_id", "scenes", ["current_final_version_id"])
    op.create_index("ix_scenes_latest_draft_version_id", "scenes", ["latest_draft_version_id"])

    op.add_column("scene_versions", sa.Column("parent_version_id", sa.String(48), nullable=True))
    op.add_column("scene_versions", sa.Column("version_kind", sa.String(16), nullable=False, server_default="final"))
    op.add_column("scene_versions", sa.Column("change_summary", sa.String(240), nullable=True))
    op.add_column("scene_versions", sa.Column("plan_json", sa.JSON(), nullable=True))
    op.add_column("scene_versions", sa.Column("compiler_version", sa.String(40), nullable=True))
    op.add_column("scene_versions", sa.Column("style_kit_version", sa.String(48), nullable=True))
    op.add_column("scene_versions", sa.Column("quality_profile", sa.String(16), nullable=True))
    op.add_column("scene_versions", sa.Column("thumbnail_ref", sa.String(255), nullable=True))
    op.create_index("ix_scene_versions_parent_version_id", "scene_versions", ["parent_version_id"])

    op.add_column("generation_jobs", sa.Column("api_version", sa.String(8), nullable=False, server_default="v1"))
    op.add_column("generation_jobs", sa.Column("current_stage", sa.String(32), nullable=True))
    op.add_column("generation_jobs", sa.Column("request_json", sa.JSON(), nullable=True))
    op.add_column("generation_jobs", sa.Column("request_fingerprint", sa.String(64), nullable=True))
    op.add_column("generation_jobs", sa.Column("draft_version_id", sa.String(48), nullable=True))
    op.add_column("generation_jobs", sa.Column("final_version_id", sa.String(48), nullable=True))
    op.add_column("generation_jobs", sa.Column("last_heartbeat", sa.DateTime(timezone=True), nullable=True))
    op.add_column("generation_jobs", sa.Column("lease_owner", sa.String(64), nullable=True))
    op.add_column("generation_jobs", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_generation_jobs_request_fingerprint", "generation_jobs", ["request_fingerprint"])

    op.create_table(
        "generation_stages",
        sa.Column("id", sa.String(48), primary_key=True),
        sa.Column("job_id", sa.String(48), sa.ForeignKey("generation_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage_name", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("checkpoint_version_id", sa.String(48), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("job_id", "stage_name", "attempt", name="uq_generation_stage_attempt"),
    )
    op.create_index("ix_generation_stages_job_started", "generation_stages", ["job_id", "started_at"])

    op.create_table(
        "scene_commands",
        sa.Column("id", sa.String(48), primary_key=True),
        sa.Column("scene_id", sa.String(48), sa.ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_version_id", sa.String(48), nullable=False),
        sa.Column("result_version_id", sa.String(48), nullable=True),
        sa.Column("command_type", sa.String(40), nullable=False),
        sa.Column("command_json", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(80), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("scene_id", "idempotency_key", name="uq_scene_command_idempotency"),
    )
    op.create_index("ix_scene_commands_scene_id", "scene_commands", ["scene_id"])

    op.create_table(
        "style_kits",
        sa.Column("id", sa.String(48), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("version", sa.String(24), nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("active", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "asset_catalog",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("category", sa.String(48), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("active", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_asset_catalog_category", "asset_catalog", ["category"])


def downgrade() -> None:
    op.drop_index("ix_asset_catalog_category", table_name="asset_catalog")
    op.drop_table("asset_catalog")
    op.drop_table("style_kits")
    op.drop_index("ix_scene_commands_scene_id", table_name="scene_commands")
    op.drop_table("scene_commands")
    op.drop_index("ix_generation_stages_job_started", table_name="generation_stages")
    op.drop_table("generation_stages")
    op.drop_index("ix_generation_jobs_request_fingerprint", table_name="generation_jobs")
    for column in ("lease_expires_at", "lease_owner", "last_heartbeat", "final_version_id", "draft_version_id", "request_fingerprint", "request_json", "current_stage", "api_version"):
        op.drop_column("generation_jobs", column)
    op.drop_index("ix_scene_versions_parent_version_id", table_name="scene_versions")
    for column in ("thumbnail_ref", "quality_profile", "style_kit_version", "compiler_version", "plan_json", "change_summary", "version_kind", "parent_version_id"):
        op.drop_column("scene_versions", column)
    op.drop_index("ix_scenes_latest_draft_version_id", table_name="scenes")
    op.drop_index("ix_scenes_current_final_version_id", table_name="scenes")
    for column in ("archived_at", "thumbnail_ref", "latest_draft_version_id", "current_final_version_id"):
        op.drop_column("scenes", column)
