from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from app.providers.base import ProviderError
from app.repositories.base import SceneRepository
from app.services.prompt_compiler import PromptCompiler


logger = logging.getLogger(__name__)


class GenerationService:
    def __init__(
        self,
        repository: SceneRepository,
        compiler: PromptCompiler,
        provider_name: str,
        model: str,
        prompt_template_version: str,
        generation_timeout_seconds: float = 360,
    ) -> None:
        self.repository = repository
        self.compiler = compiler
        self.provider_name = provider_name
        self.model = model
        self.prompt_template_version = prompt_template_version
        self.generation_timeout_seconds = generation_timeout_seconds
        self.tasks: dict[str, asyncio.Task[None]] = {}

    async def submit_job(
        self,
        *,
        owner_session_id: str,
        prompt: str,
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        job = await self.repository.create_job(
            owner_session_id=owner_session_id,
            prompt=prompt,
            provider=self.provider_name,
            model=self.model,
            prompt_template_version=self.prompt_template_version,
            idempotency_key=idempotency_key,
        )
        job_id = job["jobId"]
        if job["status"] == "queued" and job_id not in self.tasks:
            task = asyncio.create_task(
                self.run_job(job_id=job_id, owner_session_id=owner_session_id, prompt=prompt),
                name=f"generation:{job_id}",
            )
            self.tasks[job_id] = task
            task.add_done_callback(lambda _task, key=job_id: self.tasks.pop(key, None))
        return job

    async def run_job(self, *, job_id: str, owner_session_id: str, prompt: str) -> None:
        started = perf_counter()

        async def update_status(status: str) -> None:
            await self.repository.update_job(job_id, status=status)

        try:
            async with asyncio.timeout(self.generation_timeout_seconds):
                compiled = await self.compiler.compile(prompt, update_status)
            duration_ms = int((perf_counter() - started) * 1000)
            await self.repository.complete_job(
                job_id=job_id,
                owner_session_id=owner_session_id,
                prompt=prompt,
                scene_json=compiled.scene_json,
                provider=compiled.provider,
                model=compiled.model,
                duration_ms=duration_ms,
                prompt_tokens=compiled.prompt_tokens,
                completion_tokens=compiled.completion_tokens,
                retry_count=compiled.retry_count,
            )
        except asyncio.CancelledError:
            await self.repository.update_job(
                job_id,
                status="cancelled",
                error_code="GENERATION_CANCELLED",
                error_message="生成已取消。",
                duration_ms=int((perf_counter() - started) * 1000),
                completed_at=datetime.now(timezone.utc),
            )
            raise
        except ProviderError as exc:
            await self.repository.update_job(
                job_id,
                status="failed",
                error_code=exc.code,
                error_message=exc.public_message,
                duration_ms=int((perf_counter() - started) * 1000),
                completed_at=datetime.now(timezone.utc),
            )
        except TimeoutError:
            await self.repository.update_job(
                job_id,
                status="failed",
                error_code="GENERATION_TIMEOUT",
                error_message="Kimi 长时间未完成本次生成，请重新生成。",
                duration_ms=int((perf_counter() - started) * 1000),
                completed_at=datetime.now(timezone.utc),
            )
        except Exception:
            logger.exception("Generation job %s failed", job_id)
            await self.repository.update_job(
                job_id,
                status="failed",
                error_code="INTERNAL_ERROR",
                error_message="场景生成失败，请稍后重试。",
                duration_ms=int((perf_counter() - started) * 1000),
                completed_at=datetime.now(timezone.utc),
            )

    async def get_job(self, job_id: str, owner_session_id: str) -> dict[str, Any] | None:
        job = await self.repository.get_job(job_id, owner_session_id)
        if job and job.get("status") == "succeeded" and job.get("sceneId"):
            job["scene"] = await self.repository.get_scene(job["sceneId"], owner_session_id)
        return job

    async def cancel_job(self, job_id: str, owner_session_id: str) -> bool:
        job = await self.repository.get_job(job_id, owner_session_id)
        if not job or job["status"] in {"succeeded", "failed", "cancelled"}:
            return False
        task = self.tasks.get(job_id)
        if task:
            task.cancel()
            return True
        await self.repository.update_job(
            job_id,
            status="cancelled",
            error_code="GENERATION_CANCELLED",
            error_message="生成已取消。",
            completed_at=datetime.now(timezone.utc),
        )
        return True

    async def list_scenes(self, owner_session_id: str, limit: int = 30) -> list[dict[str, Any]]:
        return await self.repository.list_scenes(owner_session_id, limit)

    async def get_scene(self, scene_id: str, owner_session_id: str) -> dict[str, Any] | None:
        return await self.repository.get_scene(scene_id, owner_session_id)

    async def get_scene_version(
        self,
        scene_id: str,
        version_id: str,
        owner_session_id: str,
    ) -> dict[str, Any] | None:
        return await self.repository.get_scene_version(scene_id, version_id, owner_session_id)

    async def shutdown(self) -> None:
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
