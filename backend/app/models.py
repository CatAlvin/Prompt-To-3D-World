from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Scene(Base):
    __tablename__ = "scenes"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    owner_session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    current_version_id: Mapped[str | None] = mapped_column(String(48), nullable=True, index=True)
    current_final_version_id: Mapped[str | None] = mapped_column(String(48), nullable=True, index=True)
    latest_draft_version_id: Mapped[str | None] = mapped_column(String(48), nullable=True, index=True)
    thumbnail_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    versions: Mapped[list["SceneVersion"]] = relationship(
        back_populates="scene",
        cascade="all, delete-orphan",
        foreign_keys="SceneVersion.scene_id",
    )


class SceneVersion(Base):
    __tablename__ = "scene_versions"
    __table_args__ = (
        UniqueConstraint("scene_id", "version_number", name="uq_scene_version_number"),
        Index("ix_scene_versions_scene_created", "scene_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    scene_id: Mapped[str] = mapped_column(ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(24), nullable=False)
    scene_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    original_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    parent_version_id: Mapped[str | None] = mapped_column(String(48), nullable=True, index=True)
    version_kind: Mapped[str] = mapped_column(String(16), default="final", nullable=False)
    change_summary: Mapped[str | None] = mapped_column(String(240), nullable=True)
    plan_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    compiler_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    style_kit_version: Mapped[str | None] = mapped_column(String(48), nullable=True)
    quality_profile: Mapped[str | None] = mapped_column(String(16), nullable=True)
    thumbnail_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    scene: Mapped[Scene] = relationship(back_populates="versions", foreign_keys=[scene_id])


class GenerationJob(Base):
    __tablename__ = "generation_jobs"
    __table_args__ = (
        UniqueConstraint("owner_session_id", "idempotency_key", name="uq_generation_idempotency"),
        Index("ix_generation_jobs_owner_created", "owner_session_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    owner_session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_template_version: Mapped[str] = mapped_column(String(24), nullable=False)
    api_version: Mapped[str] = mapped_column(String(8), default="v1", nullable=False)
    current_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    request_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    request_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    draft_version_id: Mapped[str | None] = mapped_column(String(48), nullable=True)
    final_version_id: Mapped[str | None] = mapped_column(String(48), nullable=True)
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    scene_id: Mapped[str | None] = mapped_column(String(48), nullable=True, index=True)
    scene_version_id: Mapped[str | None] = mapped_column(String(48), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GenerationStage(Base):
    __tablename__ = "generation_stages"
    __table_args__ = (
        UniqueConstraint("job_id", "stage_name", "attempt", name="uq_generation_stage_attempt"),
        Index("ix_generation_stages_job_started", "job_id", "started_at"),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("generation_jobs.id", ondelete="CASCADE"), nullable=False)
    stage_name: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checkpoint_version_id: Mapped[str | None] = mapped_column(String(48), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SceneCommand(Base):
    __tablename__ = "scene_commands"
    __table_args__ = (UniqueConstraint("scene_id", "idempotency_key", name="uq_scene_command_idempotency"),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    scene_id: Mapped[str] = mapped_column(ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False, index=True)
    source_version_id: Mapped[str] = mapped_column(String(48), nullable=False)
    result_version_id: Mapped[str | None] = mapped_column(String(48), nullable=True)
    command_type: Mapped[str] = mapped_column(String(40), nullable=False)
    command_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class StyleKitRecord(Base):
    __tablename__ = "style_kits"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    version: Mapped[str] = mapped_column(String(24), nullable=False)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    active: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AssetCatalogRecord(Base):
    __tablename__ = "asset_catalog"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    category: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    active: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
