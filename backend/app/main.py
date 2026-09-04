from __future__ import annotations

import asyncio
import json
import re
import time
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from app.api_schemas import (
    GenerationCreate,
    GenerationCreateV2,
    GenerationCreateV3,
    SceneCommandPayload,
    SceneCommandPayloadV3,
)
from app.compilers.procedural import ProceduralSceneCompiler
from app.compilers.style_kits import StyleKitRegistry
from app.bootstrap import bootstrap_database
from app.config import Settings, get_settings
from app.database import dispose_engine, get_session_factory
from app.domain.scene_validator import SceneValidator
from app.providers.kimi import (
    INTENT_PROMPT_TEMPLATE_VERSION,
    KimiProvider,
    PLAN_PROMPT_TEMPLATE_VERSION,
    PROMPT_TEMPLATE_VERSION,
)
from app.repositories.sqlalchemy import SqlAlchemySceneRepository
from app.services.generation import GenerationService
from app.services.prompt_compiler import PromptCompiler
from app.services.v2.generation import GenerationV2Service
from app.services.v2.plan_compiler import ScenePlanCompiler
from app.services.v3.generation import GenerationV3Service
from app.services.v3.intent_compiler import SceneIntentCompiler
from app.services.v3.recipe_compiler import VisualRecipeCompiler


SESSION_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


class SlidingWindowRateLimiter:
    def __init__(self, limit: int, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.events: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        bucket = self.events[key]
        while bucket and bucket[0] <= now - self.window_seconds:
            bucket.popleft()
        if len(bucket) >= self.limit:
            return False
        bucket.append(now)
        return True


def _session_id(value: str | None) -> str:
    if not value or not SESSION_PATTERN.fullmatch(value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_SESSION", "message": "缺少有效的匿名会话标识。"},
        )
    return value


def build_service(settings: Settings) -> GenerationService:
    validator = SceneValidator()
    provider = KimiProvider(settings)
    compiler = PromptCompiler(provider, validator, max_repairs=2)
    repository = SqlAlchemySceneRepository(get_session_factory())
    return GenerationService(
        repository=repository,
        compiler=compiler,
        provider_name=provider.name,
        model=provider.model,
        prompt_template_version=PROMPT_TEMPLATE_VERSION,
        generation_timeout_seconds=settings.generation_timeout_seconds,
    )


def build_v2_service(settings: Settings, *, auto_start: bool | None = None) -> GenerationV2Service:
    provider = KimiProvider(settings)
    repository = SqlAlchemySceneRepository(get_session_factory())
    return GenerationV2Service(
        repository=repository,
        plan_compiler=ScenePlanCompiler(provider),
        scene_compiler=ProceduralSceneCompiler(),
        provider_name=provider.name,
        model=provider.model,
        generation_timeout_seconds=settings.generation_timeout_seconds,
        auto_start=settings.v2_inline_worker if auto_start is None else auto_start,
    )


def build_v3_service(settings: Settings, *, auto_start: bool | None = None) -> GenerationV3Service:
    provider = KimiProvider(settings)
    repository = SqlAlchemySceneRepository(get_session_factory())
    return GenerationV3Service(
        repository=repository,
        intent_compiler=SceneIntentCompiler(provider),
        scene_compiler=VisualRecipeCompiler(),
        provider_name=provider.name,
        model=provider.model,
        generation_timeout_seconds=settings.generation_timeout_seconds,
        auto_start=settings.v2_inline_worker if auto_start is None else auto_start,
    )


def create_app(
    service_override: GenerationService | Any | None = None,
    *,
    v2_service_override: GenerationV2Service | Any | None = None,
    v3_service_override: GenerationV3Service | Any | None = None,
    bootstrap: bool = True,
    settings_override: Settings | None = None,
) -> FastAPI:
    settings = settings_override or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        if bootstrap:
            bootstrap_database()
        application.state.service = service_override or build_service(settings)
        application.state.v2_service = (
            v2_service_override
            if v2_service_override is not None
            else (None if service_override is not None else build_v2_service(settings))
        )
        application.state.v3_service = (
            v3_service_override
            if v3_service_override is not None
            else (None if service_override is not None else build_v3_service(settings))
        )
        if application.state.v2_service is not None and getattr(application.state.v2_service, "auto_start", False):
            await application.state.v2_service.recover_pending_jobs()
        if application.state.v3_service is not None and getattr(application.state.v3_service, "auto_start", False):
            await application.state.v3_service.recover_pending_jobs()
        application.state.style_registry = StyleKitRegistry()
        application.state.rate_limiter = SlidingWindowRateLimiter(
            settings.generation_rate_limit_per_minute
        )
        yield
        await application.state.service.shutdown()
        if application.state.v2_service is not None:
            await application.state.v2_service.shutdown()
        if application.state.v3_service is not None:
            await application.state.v3_service.shutdown()
        if bootstrap:
            await dispose_engine()

    application = FastAPI(
        title="Prompt-To-3D-World API",
        version="3.0.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Session-ID", "Idempotency-Key", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    @application.middleware("http")
    async def request_context(request: Request, call_next: Any) -> JSONResponse:
        request_id = request.headers.get("X-Request-ID") or f"req_{uuid4().hex}"
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > 300_000:
            return JSONResponse(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                content={"detail": {"code": "REQUEST_TOO_LARGE", "message": "请求内容过大。"}},
                headers={"X-Request-ID": request_id},
            )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @application.get("/api/v1/health")
    async def health(request: Request) -> dict[str, Any]:
        database_ok = await request.app.state.service.repository.health()
        return {
            "status": "ok" if database_ok else "degraded",
            "database": "connected" if database_ok else "unavailable",
            "provider": settings.llm_provider,
            "model": settings.kimi_model,
            "providerConfigured": bool(settings.moonshot_api_key),
        }

    @application.post("/api/v1/generations", status_code=status.HTTP_202_ACCEPTED)
    async def create_generation(
        payload: GenerationCreate,
        request: Request,
        x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        session_id = _session_id(x_session_id)
        if not request.app.state.rate_limiter.allow(session_id):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"code": "RATE_LIMITED", "message": "生成请求过于频繁，请稍后再试。"},
            )
        if idempotency_key and len(idempotency_key) > 80:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_IDEMPOTENCY_KEY", "message": "幂等标识过长。"},
            )
        return await request.app.state.service.submit_job(
            owner_session_id=session_id,
            prompt=payload.prompt,
            idempotency_key=idempotency_key,
        )

    @application.get("/api/v1/generations/{job_id}")
    async def get_generation(
        job_id: str,
        request: Request,
        x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
    ) -> dict[str, Any]:
        job = await request.app.state.service.get_job(job_id, _session_id(x_session_id))
        if not job:
            raise HTTPException(status_code=404, detail={"code": "JOB_NOT_FOUND", "message": "生成任务不存在。"})
        return job

    @application.post("/api/v1/generations/{job_id}/cancel")
    async def cancel_generation(
        job_id: str,
        request: Request,
        x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
    ) -> dict[str, bool]:
        cancelled = await request.app.state.service.cancel_job(job_id, _session_id(x_session_id))
        return {"cancelled": cancelled}

    @application.get("/api/v1/scenes")
    async def list_scenes(
        request: Request,
        limit: int = Query(default=30, ge=1, le=100),
        x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
    ) -> dict[str, Any]:
        scenes = await request.app.state.service.list_scenes(_session_id(x_session_id), limit)
        return {"items": scenes, "nextCursor": None}

    @application.get("/api/v1/scenes/{scene_id}")
    async def get_scene(
        scene_id: str,
        request: Request,
        x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
    ) -> dict[str, Any]:
        scene = await request.app.state.service.get_scene(scene_id, _session_id(x_session_id))
        if not scene:
            raise HTTPException(status_code=404, detail={"code": "SCENE_NOT_FOUND", "message": "场景不存在。"})
        return scene

    @application.get("/api/v1/scenes/{scene_id}/versions/{version_id}")
    async def get_scene_version(
        scene_id: str,
        version_id: str,
        request: Request,
        x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
    ) -> dict[str, Any]:
        scene = await request.app.state.service.get_scene_version(
            scene_id,
            version_id,
            _session_id(x_session_id),
        )
        if not scene:
            raise HTTPException(status_code=404, detail={"code": "VERSION_NOT_FOUND", "message": "场景版本不存在。"})
        return scene

    def v2_service(request: Request) -> GenerationV2Service:
        service = request.app.state.v2_service
        if service is None:
            raise HTTPException(status_code=503, detail={"code": "V2_UNAVAILABLE", "message": "V2 服务未配置。"})
        return service

    @application.get("/api/v2/health")
    async def health_v2(request: Request) -> dict[str, Any]:
        database_ok = await request.app.state.service.repository.health()
        return {
            "status": "ok" if database_ok else "degraded",
            "database": "connected" if database_ok else "unavailable",
            "provider": settings.llm_provider,
            "model": settings.kimi_model,
            "providerConfigured": bool(settings.moonshot_api_key),
            "pipeline": "scene-plan-1.0.0",
            "runtime": "scene-2.0.0",
        }

    @application.post("/api/v2/generations", status_code=status.HTTP_202_ACCEPTED)
    async def create_generation_v2(
        payload: GenerationCreateV2,
        request: Request,
        x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        session_id = _session_id(x_session_id)
        if not request.app.state.rate_limiter.allow(f"v2:{session_id}"):
            raise HTTPException(status_code=429, detail={"code": "RATE_LIMITED", "message": "生成请求过于频繁，请稍后再试。"})
        return await v2_service(request).submit_job(
            owner_session_id=session_id,
            prompt=payload.prompt,
            preferences=payload.preferences.model_dump(),
            idempotency_key=idempotency_key,
        )

    @application.get("/api/v2/generations/{job_id}")
    async def get_generation_v2(
        job_id: str,
        request: Request,
        x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
    ) -> dict[str, Any]:
        job = await v2_service(request).get_job(job_id, _session_id(x_session_id))
        if not job:
            raise HTTPException(status_code=404, detail={"code": "JOB_NOT_FOUND", "message": "生成任务不存在。"})
        return job

    @application.post("/api/v2/generations/{job_id}/cancel")
    async def cancel_generation_v2(
        job_id: str,
        request: Request,
        x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
    ) -> dict[str, bool]:
        return {"cancelled": await v2_service(request).cancel_job(job_id, _session_id(x_session_id))}

    @application.get("/api/v2/generations/{job_id}/events")
    async def generation_events_v2(
        job_id: str,
        request: Request,
        session: str | None = Query(default=None),
        x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
    ) -> StreamingResponse:
        owner = _session_id(x_session_id or session)

        async def event_stream() -> AsyncIterator[str]:
            last_status: str | None = None
            stage_state: dict[str, str] = {}
            draft_sent = False
            while True:
                if await request.is_disconnected():
                    return
                job = await v2_service(request).get_job(job_id, owner)
                if not job:
                    yield "event: job.failed\ndata: {\"code\":\"JOB_NOT_FOUND\"}\n\n"
                    return
                if job["status"] != last_status:
                    yield f"event: job.status\ndata: {json.dumps({'status': job['status'], 'currentStage': job.get('currentStage')})}\n\n"
                    last_status = job["status"]
                for stage in job.get("stages", []):
                    prior = stage_state.get(stage["stage"])
                    if prior == stage["status"]:
                        continue
                    event_name = "stage.started" if stage["status"] == "running" else "stage.completed"
                    yield f"event: {event_name}\ndata: {json.dumps(stage)}\n\n"
                    stage_state[stage["stage"]] = stage["status"]
                if job.get("draft") and not draft_sent:
                    yield f"event: draft.ready\ndata: {json.dumps(job['draft'])}\n\n"
                    draft_sent = True
                if job["status"] == "succeeded":
                    yield f"event: final.ready\ndata: {json.dumps(job.get('scene'))}\n\n"
                    return
                if job["status"] in {"partial", "failed", "cancelled"}:
                    yield f"event: job.failed\ndata: {json.dumps({'status': job['status'], 'error': job.get('error'), 'draftPreserved': bool(job.get('draft'))})}\n\n"
                    return
                yield ": keepalive\n\n"
                await asyncio.sleep(0.55)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @application.get("/api/v2/scenes")
    async def list_scenes_v2(
        request: Request,
        limit: int = Query(default=30, ge=1, le=100),
        x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
    ) -> dict[str, Any]:
        return {"items": await request.app.state.service.list_scenes(_session_id(x_session_id), limit), "nextCursor": None}

    @application.get("/api/v2/scenes/{scene_id}")
    async def get_scene_v2(
        scene_id: str,
        request: Request,
        x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
    ) -> dict[str, Any]:
        scene = await request.app.state.service.get_scene(scene_id, _session_id(x_session_id))
        if not scene:
            raise HTTPException(status_code=404, detail={"code": "SCENE_NOT_FOUND", "message": "场景不存在。"})
        return scene

    @application.get("/api/v2/scenes/{scene_id}/versions")
    async def list_versions_v2(
        scene_id: str,
        request: Request,
        x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
    ) -> dict[str, Any]:
        return {"items": await v2_service(request).list_versions(scene_id, _session_id(x_session_id))}

    @application.post("/api/v2/scenes/{scene_id}/versions/{version_id}/restore")
    async def restore_version_v2(
        scene_id: str,
        version_id: str,
        request: Request,
        x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
    ) -> dict[str, Any]:
        try:
            return await v2_service(request).restore_version(scene_id, version_id, _session_id(x_session_id))
        except LookupError:
            raise HTTPException(status_code=404, detail={"code": "VERSION_NOT_FOUND", "message": "场景版本不存在。"})

    @application.post("/api/v2/scenes/{scene_id}/commands")
    async def apply_scene_command_v2(
        scene_id: str,
        payload: SceneCommandPayload,
        request: Request,
        x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        if not idempotency_key:
            raise HTTPException(status_code=400, detail={"code": "IDEMPOTENCY_REQUIRED", "message": "局部修改需要幂等标识。"})
        try:
            return await v2_service(request).apply_command(
                scene_id=scene_id,
                owner_session_id=_session_id(x_session_id),
                source_version_id=payload.sourceVersionId,
                command_type=payload.type,
                parameters=payload.parameters,
                idempotency_key=idempotency_key,
            )
        except LookupError:
            raise HTTPException(status_code=404, detail={"code": "VERSION_NOT_FOUND", "message": "来源版本不存在。"})
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"code": "COMMAND_INVALID", "message": str(exc)})

    @application.post("/api/v2/scenes/{scene_id}/duplicate", status_code=status.HTTP_201_CREATED)
    async def duplicate_scene_v2(
        scene_id: str,
        request: Request,
        x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
    ) -> dict[str, Any]:
        duplicate = await v2_service(request).duplicate_scene(scene_id, _session_id(x_session_id))
        if not duplicate:
            raise HTTPException(status_code=404, detail={"code": "SCENE_NOT_FOUND", "message": "场景不存在。"})
        return duplicate

    @application.delete("/api/v2/scenes/{scene_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_scene_v2(
        scene_id: str,
        request: Request,
        x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
    ) -> None:
        deleted = await v2_service(request).delete_scene(scene_id, _session_id(x_session_id))
        if not deleted:
            raise HTTPException(status_code=404, detail={"code": "SCENE_NOT_FOUND", "message": "场景不存在。"})

    @application.get("/api/v2/style-kits")
    async def list_style_kits_v2(request: Request) -> dict[str, Any]:
        return {"items": request.app.state.style_registry.list_public()}

    @application.get("/api/v2/assets/{asset_id}/metadata")
    async def asset_metadata_v2(asset_id: str, request: Request) -> dict[str, Any]:
        asset = request.app.state.style_registry.asset(asset_id)
        if not asset:
            raise HTTPException(status_code=404, detail={"code": "ASSET_NOT_FOUND", "message": "资产不存在。"})
        return asset

    def v3_service(request: Request) -> GenerationV3Service:
        service = request.app.state.v3_service
        if service is None:
            raise HTTPException(status_code=503, detail={"code": "V3_UNAVAILABLE", "message": "V3 服务未配置。"})
        return service

    @application.get("/api/v3/health")
    async def health_v3(request: Request) -> dict[str, Any]:
        service = v3_service(request)
        database_ok = await service.repository.health()
        return {
            "status": "ok" if database_ok else "degraded",
            "database": "connected" if database_ok else "unavailable",
            "provider": settings.llm_provider,
            "model": settings.kimi_model,
            "providerConfigured": bool(settings.moonshot_api_key),
            "pipeline": INTENT_PROMPT_TEMPLATE_VERSION,
            "runtime": "scene-3.0.0",
            "capabilities": service.capabilities.version,
        }

    @application.post("/api/v3/generations", status_code=status.HTTP_202_ACCEPTED)
    async def create_generation_v3(
        payload: GenerationCreateV3,
        request: Request,
        x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        session_id = _session_id(x_session_id)
        if not request.app.state.rate_limiter.allow(f"v3:{session_id}"):
            raise HTTPException(status_code=429, detail={"code": "RATE_LIMITED", "message": "生成请求过于频繁，请稍后再试。"})
        if idempotency_key and len(idempotency_key) > 80:
            raise HTTPException(status_code=400, detail={"code": "INVALID_IDEMPOTENCY_KEY", "message": "幂等标识过长。"})
        return await v3_service(request).submit_job(
            owner_session_id=session_id,
            prompt=payload.prompt,
            preferences=payload.preferences.model_dump(),
            idempotency_key=idempotency_key,
        )

    @application.get("/api/v3/generations/{job_id}")
    async def get_generation_v3(
        job_id: str,
        request: Request,
        x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
    ) -> dict[str, Any]:
        job = await v3_service(request).get_job(job_id, _session_id(x_session_id))
        if not job:
            raise HTTPException(status_code=404, detail={"code": "JOB_NOT_FOUND", "message": "生成任务不存在。"})
        return job

    @application.post("/api/v3/generations/{job_id}/cancel")
    async def cancel_generation_v3(
        job_id: str,
        request: Request,
        x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
    ) -> dict[str, bool]:
        return {"cancelled": await v3_service(request).cancel_job(job_id, _session_id(x_session_id))}

    @application.get("/api/v3/generations/{job_id}/events")
    async def generation_events_v3(
        job_id: str,
        request: Request,
        session: str | None = Query(default=None),
        x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
    ) -> StreamingResponse:
        owner = _session_id(x_session_id or session)

        async def event_stream() -> AsyncIterator[str]:
            last_status: str | None = None
            stage_state: dict[str, str] = {}
            last_intent: str | None = None
            draft_sent = False
            while True:
                if await request.is_disconnected():
                    return
                job = await v3_service(request).get_job(job_id, owner)
                if not job:
                    yield "event: job.failed\ndata: {\"code\":\"JOB_NOT_FOUND\"}\n\n"
                    return
                if job["status"] != last_status:
                    yield f"event: job.status\ndata: {json.dumps({'status': job['status'], 'currentStage': job.get('currentStage')})}\n\n"
                    last_status = job["status"]
                if job.get("intentPreview"):
                    intent_payload = json.dumps(job["intentPreview"], ensure_ascii=False, sort_keys=True)
                    if intent_payload != last_intent:
                        yield f"event: intent.ready\ndata: {intent_payload}\n\n"
                        last_intent = intent_payload
                for stage in job.get("stages", []):
                    prior = stage_state.get(stage["stage"])
                    if prior == stage["status"]:
                        continue
                    event_name = "stage.started" if stage["status"] == "running" else "stage.completed"
                    yield f"event: {event_name}\ndata: {json.dumps(stage, ensure_ascii=False)}\n\n"
                    stage_state[stage["stage"]] = stage["status"]
                if job.get("draft") and not draft_sent:
                    yield f"event: draft.ready\ndata: {json.dumps(job['draft'], ensure_ascii=False)}\n\n"
                    draft_sent = True
                if job["status"] == "succeeded":
                    yield f"event: final.ready\ndata: {json.dumps(job.get('scene'), ensure_ascii=False)}\n\n"
                    return
                if job["status"] in {"partial", "failed", "cancelled"}:
                    yield f"event: job.failed\ndata: {json.dumps({'status': job['status'], 'error': job.get('error'), 'draftPreserved': bool(job.get('draft'))}, ensure_ascii=False)}\n\n"
                    return
                yield ": keepalive\n\n"
                await asyncio.sleep(0.55)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @application.get("/api/v3/scenes")
    async def list_scenes_v3(
        request: Request,
        limit: int = Query(default=30, ge=1, le=100),
        x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
    ) -> dict[str, Any]:
        return {
            "items": await v3_service(request).repository.list_scenes(_session_id(x_session_id), limit),
            "nextCursor": None,
        }

    @application.get("/api/v3/scenes/{scene_id}")
    async def get_scene_v3(
        scene_id: str,
        request: Request,
        x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
    ) -> dict[str, Any]:
        scene = await v3_service(request).repository.get_scene(scene_id, _session_id(x_session_id))
        if not scene:
            raise HTTPException(status_code=404, detail={"code": "SCENE_NOT_FOUND", "message": "场景不存在。"})
        return scene

    @application.get("/api/v3/scenes/{scene_id}/versions")
    async def list_versions_v3(
        scene_id: str,
        request: Request,
        x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
    ) -> dict[str, Any]:
        return {"items": await v3_service(request).list_versions(scene_id, _session_id(x_session_id))}

    @application.post("/api/v3/scenes/{scene_id}/versions/{version_id}/restore")
    async def restore_version_v3(
        scene_id: str,
        version_id: str,
        request: Request,
        x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
    ) -> dict[str, Any]:
        try:
            return await v3_service(request).restore_version(scene_id, version_id, _session_id(x_session_id))
        except LookupError:
            raise HTTPException(status_code=404, detail={"code": "VERSION_NOT_FOUND", "message": "场景版本不存在。"})

    @application.post("/api/v3/scenes/{scene_id}/commands")
    async def apply_scene_command_v3(
        scene_id: str,
        payload: SceneCommandPayloadV3,
        request: Request,
        x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        if not idempotency_key:
            raise HTTPException(status_code=400, detail={"code": "IDEMPOTENCY_REQUIRED", "message": "局部修改需要幂等标识。"})
        try:
            return await v3_service(request).apply_command(
                scene_id=scene_id,
                owner_session_id=_session_id(x_session_id),
                source_version_id=payload.sourceVersionId,
                command_type=payload.type,
                parameters=payload.parameters,
                idempotency_key=idempotency_key,
            )
        except LookupError:
            raise HTTPException(status_code=404, detail={"code": "VERSION_NOT_FOUND", "message": "来源版本不存在。"})
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"code": "COMMAND_INVALID", "message": str(exc)})

    @application.post("/api/v3/scenes/{scene_id}/duplicate", status_code=status.HTTP_201_CREATED)
    async def duplicate_scene_v3(
        scene_id: str,
        request: Request,
        x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
    ) -> dict[str, Any]:
        duplicate = await v3_service(request).duplicate_scene(scene_id, _session_id(x_session_id))
        if not duplicate:
            raise HTTPException(status_code=404, detail={"code": "SCENE_NOT_FOUND", "message": "场景不存在。"})
        return duplicate

    @application.delete("/api/v3/scenes/{scene_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_scene_v3(
        scene_id: str,
        request: Request,
        x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
    ) -> None:
        deleted = await v3_service(request).delete_scene(scene_id, _session_id(x_session_id))
        if not deleted:
            raise HTTPException(status_code=404, detail={"code": "SCENE_NOT_FOUND", "message": "场景不存在。"})

    @application.get("/api/v3/style-kits")
    async def list_style_kits_v3(request: Request) -> dict[str, Any]:
        return {"items": request.app.state.style_registry.list_public()}

    @application.get("/api/v3/capabilities")
    async def list_capabilities_v3(request: Request) -> dict[str, Any]:
        service = v3_service(request)
        return {"version": service.capabilities.version, "items": service.capabilities.list_public()}

    return application


app = create_app()
