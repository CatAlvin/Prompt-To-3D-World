from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import GenerationJob, GenerationStage, Scene, SceneCommand, SceneVersion


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _job_dict(job: GenerationJob) -> dict[str, Any]:
    return {
        "jobId": job.id,
        "status": job.status,
        "prompt": job.prompt,
        "provider": job.provider,
        "model": job.model,
        "error": (
            {"code": job.error_code, "message": job.error_message}
            if job.error_code
            else None
        ),
        "durationMs": job.duration_ms,
        "usage": {
            "promptTokens": job.prompt_tokens,
            "completionTokens": job.completion_tokens,
        },
        "retryCount": job.retry_count,
        "sceneId": job.scene_id,
        "sceneVersionId": job.scene_version_id,
        "apiVersion": job.api_version,
        "currentStage": job.current_stage,
        "request": job.request_json,
        "requestFingerprint": job.request_fingerprint,
        "draftVersionId": job.draft_version_id,
        "finalVersionId": job.final_version_id,
        "lastHeartbeat": _iso(job.last_heartbeat),
        "createdAt": _iso(job.created_at),
        "updatedAt": _iso(job.updated_at),
        "completedAt": _iso(job.completed_at),
    }


def _scene_summary(scene: Scene, version: SceneVersion | None) -> dict[str, Any]:
    pipeline = version.scene_json.get("pipeline", {}) if version else {}
    background = version.scene_json.get("environment", {}).get("background", "#11121a") if version else "#11121a"
    accent = next(
        (
            node.get("material", {}).get("emissive") or node.get("material", {}).get("color")
            for node in version.scene_json.get("nodes", [])
            if node.get("kind") in {"text", "decal"} and node.get("material")
        ),
        "#c92f63",
    ) if version else "#c92f63"
    return {
        "sceneId": scene.id,
        "title": scene.title,
        "currentVersionId": scene.current_version_id,
        "prompt": version.original_prompt if version else "",
        "schemaVersion": version.schema_version if version else None,
        "nodeCount": len(version.scene_json.get("nodes", [])) if version else 0,
        "versionKind": version.version_kind if version else None,
        "styleKit": pipeline.get("styleKit"),
        "quality": pipeline.get("quality"),
        "changeSummary": version.change_summary if version else None,
        "thumbnail": {"background": background, "accent": accent},
        "createdAt": _iso(scene.created_at),
        "updatedAt": _iso(scene.updated_at),
    }


def _scene_detail(scene: Scene, version: SceneVersion) -> dict[str, Any]:
    detail = {
        **_scene_summary(scene, version),
        "version": {
            "versionId": version.id,
            "versionNumber": version.version_number,
            "schemaVersion": version.schema_version,
            "sceneJson": version.scene_json,
            "prompt": version.original_prompt,
            "seed": version.seed,
            "provider": version.provider,
            "model": version.model,
            "parentVersionId": version.parent_version_id,
            "versionKind": version.version_kind,
            "changeSummary": version.change_summary,
            "planJson": version.plan_json,
            "compilerVersion": version.compiler_version,
            "styleKit": version.style_kit_version,
            "quality": version.quality_profile,
            "createdAt": _iso(version.created_at),
        },
    }
    plan = version.plan_json or {}
    if plan.get("kind") == "v3":
        detail["intentPreview"] = plan.get("intentPreview")
        detail["coverage"] = plan.get("fidelityReport")
        detail["unsupportedEntities"] = plan.get("unsupportedEntities", [])
        detail["resolutionTrace"] = plan.get("resolutionTrace", [])
    return detail


class SqlAlchemySceneRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def create_job(
        self,
        *,
        owner_session_id: str,
        prompt: str,
        provider: str,
        model: str,
        prompt_template_version: str,
        idempotency_key: str | None,
        api_version: str = "v1",
        request_json: dict[str, Any] | None = None,
        request_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        async with self.session_factory() as session:
            if idempotency_key:
                existing = await session.scalar(
                    select(GenerationJob).where(
                        GenerationJob.owner_session_id == owner_session_id,
                        GenerationJob.idempotency_key == idempotency_key,
                    )
                )
                if existing:
                    return _job_dict(existing)

            job = GenerationJob(
                id=f"gen_{uuid4().hex}",
                owner_session_id=owner_session_id,
                idempotency_key=idempotency_key,
                status="queued",
                prompt=prompt,
                provider=provider,
                model=model,
                prompt_template_version=prompt_template_version,
                api_version=api_version,
                current_stage="queued" if api_version in {"v2", "v3"} else None,
                request_json=request_json,
                request_fingerprint=request_fingerprint,
            )
            session.add(job)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                if not idempotency_key:
                    raise
                existing = await session.scalar(
                    select(GenerationJob).where(
                        GenerationJob.owner_session_id == owner_session_id,
                        GenerationJob.idempotency_key == idempotency_key,
                    )
                )
                if not existing:
                    raise
                return _job_dict(existing)
            await session.refresh(job)
            return _job_dict(job)

    async def get_job(self, job_id: str, owner_session_id: str) -> dict[str, Any] | None:
        async with self.session_factory() as session:
            job = await session.scalar(
                select(GenerationJob).where(
                    GenerationJob.id == job_id,
                    GenerationJob.owner_session_id == owner_session_id,
                )
            )
            return _job_dict(job) if job else None

    async def update_job(self, job_id: str, **fields: Any) -> dict[str, Any] | None:
        allowed = {
            "status",
            "error_code",
            "error_message",
            "duration_ms",
            "prompt_tokens",
            "completion_tokens",
            "retry_count",
            "scene_id",
            "scene_version_id",
            "current_stage",
            "request_json",
            "request_fingerprint",
            "draft_version_id",
            "final_version_id",
            "last_heartbeat",
            "lease_owner",
            "lease_expires_at",
            "completed_at",
        }
        async with self.session_factory() as session:
            job = await session.get(GenerationJob, job_id)
            if not job:
                return None
            for key, value in fields.items():
                if key not in allowed:
                    raise ValueError(f"Unsupported job field: {key}")
                setattr(job, key, value)
            job.updated_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(job)
            return _job_dict(job)

    async def complete_job(
        self,
        *,
        job_id: str,
        owner_session_id: str,
        prompt: str,
        scene_json: dict[str, Any],
        provider: str,
        model: str,
        duration_ms: int,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        retry_count: int,
    ) -> dict[str, Any]:
        scene_id = f"scene_{uuid4().hex}"
        version_id = f"ver_{uuid4().hex}"
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            async with session.begin():
                job = await session.scalar(
                    select(GenerationJob)
                    .where(
                        GenerationJob.id == job_id,
                        GenerationJob.owner_session_id == owner_session_id,
                    )
                    .with_for_update()
                )
                if not job:
                    raise LookupError("Generation job not found")

                scene = Scene(
                    id=scene_id,
                    owner_session_id=owner_session_id,
                    title=scene_json["title"],
                    current_version_id=version_id,
                    current_final_version_id=version_id,
                    created_at=now,
                    updated_at=now,
                )
                version = SceneVersion(
                    id=version_id,
                    scene_id=scene_id,
                    version_number=1,
                    schema_version=scene_json["schemaVersion"],
                    scene_json=scene_json,
                    original_prompt=prompt,
                    seed=scene_json["seed"],
                    provider=provider,
                    model=model,
                    version_kind="final",
                    change_summary="V1 generation",
                    created_at=now,
                )
                session.add(scene)
                session.add(version)

                job.status = "succeeded"
                job.scene_id = scene_id
                job.scene_version_id = version_id
                job.duration_ms = duration_ms
                job.prompt_tokens = prompt_tokens
                job.completion_tokens = completion_tokens
                job.retry_count = retry_count
                job.completed_at = now
                job.updated_at = now
                job.error_code = None
                job.error_message = None

            return _scene_detail(scene, version)

    async def record_stage(
        self,
        job_id: str,
        stage_name: str,
        status: str,
        *,
        attempt: int = 1,
        error_code: str | None = None,
        duration_ms: int | None = None,
        checkpoint_version_id: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            stage = await session.scalar(
                select(GenerationStage).where(
                    GenerationStage.job_id == job_id,
                    GenerationStage.stage_name == stage_name,
                    GenerationStage.attempt == attempt,
                )
            )
            if not stage:
                stage = GenerationStage(
                    id=f"gst_{uuid4().hex}",
                    job_id=job_id,
                    stage_name=stage_name,
                    status=status,
                    attempt=attempt,
                    started_at=now,
                )
                session.add(stage)
            stage.status = status
            stage.error_code = error_code
            stage.duration_ms = duration_ms
            stage.checkpoint_version_id = checkpoint_version_id
            stage.metadata_json = metadata_json
            if status in {"completed", "failed", "skipped"}:
                stage.completed_at = now
            job = await session.get(GenerationJob, job_id)
            if job:
                job.current_stage = stage_name
                job.last_heartbeat = now
                job.updated_at = now
            await session.commit()
            return {
                "stage": stage.stage_name,
                "status": stage.status,
                "attempt": stage.attempt,
                "durationMs": stage.duration_ms,
                "checkpointVersionId": stage.checkpoint_version_id,
                "errorCode": stage.error_code,
                "startedAt": _iso(stage.started_at),
                "completedAt": _iso(stage.completed_at),
            }

    async def list_stages(self, job_id: str) -> list[dict[str, Any]]:
        async with self.session_factory() as session:
            stages = (
                await session.scalars(
                    select(GenerationStage)
                    .where(GenerationStage.job_id == job_id)
                    .order_by(GenerationStage.started_at, GenerationStage.id)
                )
            ).all()
            return [
                {
                    "stage": stage.stage_name,
                    "status": stage.status,
                    "attempt": stage.attempt,
                    "durationMs": stage.duration_ms,
                    "checkpointVersionId": stage.checkpoint_version_id,
                    "errorCode": stage.error_code,
                    "metadataJson": stage.metadata_json,
                    "startedAt": _iso(stage.started_at),
                    "completedAt": _iso(stage.completed_at),
                }
                for stage in stages
            ]

    async def create_draft_version(
        self,
        *,
        job_id: str,
        owner_session_id: str,
        prompt: str,
        scene_json: dict[str, Any],
        plan_json: dict[str, Any],
        provider: str,
        model: str,
    ) -> dict[str, Any]:
        scene_id = f"scene_{uuid4().hex}"
        version_id = f"ver_{uuid4().hex}"
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            async with session.begin():
                job = await session.scalar(
                    select(GenerationJob).where(
                        GenerationJob.id == job_id,
                        GenerationJob.owner_session_id == owner_session_id,
                    ).with_for_update()
                )
                if not job:
                    raise LookupError("Generation job not found")
                if job.draft_version_id and job.scene_id:
                    existing_scene_id = job.scene_id
                    existing_version_id = job.draft_version_id
                else:
                    existing_scene_id = None
                    existing_version_id = None
                    pipeline = scene_json["pipeline"]
                    scene = Scene(
                        id=scene_id,
                        owner_session_id=owner_session_id,
                        title=scene_json["title"],
                        current_version_id=version_id,
                        latest_draft_version_id=version_id,
                        created_at=now,
                        updated_at=now,
                    )
                    version = SceneVersion(
                        id=version_id,
                        scene_id=scene_id,
                        version_number=1,
                        schema_version=scene_json["schemaVersion"],
                        scene_json=scene_json,
                        original_prompt=prompt,
                        seed=scene_json["seed"],
                        provider=provider,
                        model=model,
                        version_kind="draft",
                        change_summary=(
                            "即时意图草稿"
                            if scene_json["schemaVersion"] == "3.0.0"
                            else "Instant procedural blockout"
                        ),
                        plan_json=plan_json,
                        compiler_version=pipeline["compilerVersion"],
                        style_kit_version=pipeline["styleKit"],
                        quality_profile="draft",
                        created_at=now,
                    )
                    session.add_all([scene, version])
                    job.status = "enhancing"
                    job.current_stage = "draft_ready"
                    job.scene_id = scene_id
                    job.scene_version_id = version_id
                    job.draft_version_id = version_id
                    job.last_heartbeat = now
                    job.updated_at = now
            if existing_scene_id and existing_version_id:
                row = (
                    await session.execute(
                        select(Scene, SceneVersion).join(SceneVersion, SceneVersion.id == existing_version_id).where(Scene.id == existing_scene_id)
                    )
                ).first()
                if not row:
                    raise LookupError("Draft version not found")
                return _scene_detail(row[0], row[1])
            return _scene_detail(scene, version)

    async def complete_v2_job(
        self,
        *,
        job_id: str,
        owner_session_id: str,
        prompt: str,
        scene_json: dict[str, Any],
        plan_json: dict[str, Any],
        provider: str,
        model: str,
        duration_ms: int,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        retry_count: int,
    ) -> dict[str, Any]:
        version_id = f"ver_{uuid4().hex}"
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            async with session.begin():
                job = await session.scalar(
                    select(GenerationJob).where(
                        GenerationJob.id == job_id,
                        GenerationJob.owner_session_id == owner_session_id,
                    ).with_for_update()
                )
                if not job or not job.scene_id:
                    raise LookupError("V2 generation draft not found")
                scene = await session.get(Scene, job.scene_id)
                if not scene:
                    raise LookupError("Scene not found")
                version_number = int(
                    await session.scalar(select(func.max(SceneVersion.version_number)).where(SceneVersion.scene_id == scene.id)) or 0
                ) + 1
                pipeline = scene_json["pipeline"]
                version = SceneVersion(
                    id=version_id,
                    scene_id=scene.id,
                    version_number=version_number,
                    schema_version=scene_json["schemaVersion"],
                    scene_json=scene_json,
                    original_prompt=prompt,
                    seed=scene_json["seed"],
                    provider=provider,
                    model=model,
                    parent_version_id=job.draft_version_id,
                    version_kind="final",
                    change_summary=(
                        "V3 意图已解析、构图并通过相关性核对"
                        if scene_json["schemaVersion"] == "3.0.0"
                        else "Kimi plan applied with resolved style and detail"
                    ),
                    plan_json=plan_json,
                    compiler_version=pipeline["compilerVersion"],
                    style_kit_version=pipeline["styleKit"],
                    quality_profile=pipeline["quality"],
                    created_at=now,
                )
                session.add(version)
                scene.title = scene_json["title"]
                scene.current_version_id = version_id
                scene.current_final_version_id = version_id
                scene.updated_at = now
                job.status = "succeeded"
                job.current_stage = "completed"
                job.scene_version_id = version_id
                job.final_version_id = version_id
                job.duration_ms = duration_ms
                job.prompt_tokens = prompt_tokens
                job.completion_tokens = completion_tokens
                job.retry_count = retry_count
                job.completed_at = now
                job.last_heartbeat = now
                job.updated_at = now
                job.error_code = None
                job.error_message = None
            return _scene_detail(scene, version)

    async def append_scene_version(
        self,
        *,
        scene_id: str,
        owner_session_id: str,
        source_version_id: str,
        scene_json: dict[str, Any],
        prompt: str,
        provider: str,
        model: str,
        change_summary: str,
        plan_json: dict[str, Any] | None = None,
        command_type: str | None = None,
        command_json: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            scene = await session.scalar(
                select(Scene).where(
                    Scene.id == scene_id,
                    Scene.owner_session_id == owner_session_id,
                    Scene.deleted_at.is_(None),
                ).with_for_update()
            )
            if not scene:
                raise LookupError("Scene not found")
            if idempotency_key:
                existing_command = await session.scalar(
                    select(SceneCommand).where(
                        SceneCommand.scene_id == scene_id,
                        SceneCommand.idempotency_key == idempotency_key,
                    )
                )
                if existing_command and existing_command.result_version_id:
                    existing_version = await session.get(SceneVersion, existing_command.result_version_id)
                    if existing_version:
                        return _scene_detail(scene, existing_version)
            source = await session.get(SceneVersion, source_version_id)
            if not source or source.scene_id != scene_id:
                raise LookupError("Source version not found")
            version_number = int(
                await session.scalar(select(func.max(SceneVersion.version_number)).where(SceneVersion.scene_id == scene_id)) or 0
            ) + 1
            version_id = f"ver_{uuid4().hex}"
            pipeline = scene_json.get("pipeline", {})
            version = SceneVersion(
                id=version_id,
                scene_id=scene_id,
                version_number=version_number,
                schema_version=scene_json["schemaVersion"],
                scene_json=scene_json,
                original_prompt=prompt,
                seed=scene_json["seed"],
                provider=provider,
                model=model,
                parent_version_id=source_version_id,
                version_kind="final",
                change_summary=change_summary,
                plan_json=plan_json,
                compiler_version=pipeline.get("compilerVersion"),
                style_kit_version=pipeline.get("styleKit"),
                quality_profile=pipeline.get("quality"),
                created_at=now,
            )
            session.add(version)
            scene.current_version_id = version_id
            scene.current_final_version_id = version_id
            scene.updated_at = now
            if idempotency_key and command_type and command_json is not None:
                session.add(
                    SceneCommand(
                        id=f"cmd_{uuid4().hex}",
                        scene_id=scene_id,
                        source_version_id=source_version_id,
                        result_version_id=version_id,
                        command_type=command_type,
                        command_json=command_json,
                        idempotency_key=idempotency_key,
                        status="succeeded",
                        created_at=now,
                    )
                )
            await session.commit()
            return _scene_detail(scene, version)

    async def list_scene_versions(self, scene_id: str, owner_session_id: str) -> list[dict[str, Any]]:
        async with self.session_factory() as session:
            scene = await session.scalar(
                select(Scene).where(
                    Scene.id == scene_id,
                    Scene.owner_session_id == owner_session_id,
                    Scene.deleted_at.is_(None),
                )
            )
            if not scene:
                return []
            versions = (
                await session.scalars(
                    select(SceneVersion).where(SceneVersion.scene_id == scene_id).order_by(SceneVersion.version_number.desc())
                )
            ).all()
            return [_scene_detail(scene, version) for version in versions]

    async def list_recoverable_jobs(self, limit: int = 20) -> list[dict[str, Any]]:
        async with self.session_factory() as session:
            jobs = (
                await session.scalars(
                    select(GenerationJob)
                    .where(
                        GenerationJob.api_version == "v2",
                        GenerationJob.status.in_(["queued", "enhancing"]),
                    )
                    .order_by(GenerationJob.created_at)
                    .limit(min(max(limit, 1), 100))
                )
            ).all()
            return [
                {
                    "jobId": job.id,
                    "ownerSessionId": job.owner_session_id,
                    "prompt": job.prompt,
                    "request": job.request_json or {},
                    "requestFingerprint": job.request_fingerprint,
                }
                for job in jobs
            ]

    async def duplicate_scene(self, scene_id: str, owner_session_id: str) -> dict[str, Any] | None:
        source = await self.get_scene(scene_id, owner_session_id)
        if not source:
            return None
        now = datetime.now(timezone.utc)
        new_scene_id = f"scene_{uuid4().hex}"
        new_version_id = f"ver_{uuid4().hex}"
        source_version = source["version"]
        scene_json = source_version["sceneJson"]
        async with self.session_factory() as session:
            scene = Scene(
                id=new_scene_id,
                owner_session_id=owner_session_id,
                title=f"{source['title']} 副本"[:120],
                current_version_id=new_version_id,
                current_final_version_id=new_version_id if source_version.get("versionKind") == "final" else None,
                latest_draft_version_id=new_version_id if source_version.get("versionKind") == "draft" else None,
                created_at=now,
                updated_at=now,
            )
            version = SceneVersion(
                id=new_version_id,
                scene_id=new_scene_id,
                version_number=1,
                schema_version=source_version["schemaVersion"],
                scene_json=scene_json,
                original_prompt=source["prompt"],
                seed=source_version["seed"],
                provider="scene-duplicate",
                model="scene-versioning-1.0",
                parent_version_id=source_version["versionId"],
                version_kind=source_version.get("versionKind") or "final",
                change_summary=f"Derived from {source['title']}",
                plan_json=source_version.get("planJson"),
                compiler_version=source_version.get("compilerVersion"),
                style_kit_version=source_version.get("styleKit"),
                quality_profile=source_version.get("quality"),
                created_at=now,
            )
            session.add_all([scene, version])
            await session.commit()
            return _scene_detail(scene, version)

    async def soft_delete_scene(self, scene_id: str, owner_session_id: str) -> bool:
        async with self.session_factory() as session:
            scene = await session.scalar(
                select(Scene).where(
                    Scene.id == scene_id,
                    Scene.owner_session_id == owner_session_id,
                    Scene.deleted_at.is_(None),
                )
            )
            if not scene:
                return False
            scene.deleted_at = datetime.now(timezone.utc)
            scene.updated_at = scene.deleted_at
            await session.commit()
            return True

    async def list_scenes(self, owner_session_id: str, limit: int = 30) -> list[dict[str, Any]]:
        async with self.session_factory() as session:
            rows = (
                await session.execute(
                    select(Scene, SceneVersion)
                    .join(SceneVersion, Scene.current_version_id == SceneVersion.id)
                    .where(
                        Scene.owner_session_id == owner_session_id,
                        Scene.deleted_at.is_(None),
                    )
                    .order_by(Scene.created_at.desc())
                    .limit(min(max(limit, 1), 100))
                )
            ).all()
            return [_scene_summary(scene, version) for scene, version in rows]

    async def get_scene(self, scene_id: str, owner_session_id: str) -> dict[str, Any] | None:
        async with self.session_factory() as session:
            row = (
                await session.execute(
                    select(Scene, SceneVersion)
                    .join(SceneVersion, Scene.current_version_id == SceneVersion.id)
                    .where(
                        Scene.id == scene_id,
                        Scene.owner_session_id == owner_session_id,
                        Scene.deleted_at.is_(None),
                    )
                )
            ).first()
            if not row:
                return None
            scene, version = row
            return _scene_detail(scene, version)

    async def get_scene_version(
        self,
        scene_id: str,
        version_id: str,
        owner_session_id: str,
    ) -> dict[str, Any] | None:
        async with self.session_factory() as session:
            row = (
                await session.execute(
                    select(Scene, SceneVersion)
                    .join(SceneVersion, SceneVersion.scene_id == Scene.id)
                    .where(
                        Scene.id == scene_id,
                        Scene.owner_session_id == owner_session_id,
                        SceneVersion.id == version_id,
                        Scene.deleted_at.is_(None),
                    )
                )
            ).first()
            if not row:
                return None
            scene, version = row
            return _scene_detail(scene, version)

    async def health(self) -> bool:
        try:
            async with self.session_factory() as session:
                await session.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
