from __future__ import annotations

from typing import Any, Protocol


class SceneRepository(Protocol):
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
    ) -> dict[str, Any]: ...

    async def get_job(self, job_id: str, owner_session_id: str) -> dict[str, Any] | None: ...

    async def update_job(self, job_id: str, **fields: Any) -> dict[str, Any] | None: ...

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
    ) -> dict[str, Any]: ...

    async def list_scenes(self, owner_session_id: str, limit: int = 30) -> list[dict[str, Any]]: ...

    async def get_scene(self, scene_id: str, owner_session_id: str) -> dict[str, Any] | None: ...

    async def get_scene_version(
        self,
        scene_id: str,
        version_id: str,
        owner_session_id: str,
    ) -> dict[str, Any] | None: ...

    async def health(self) -> bool: ...

    async def create_draft_version(self, **fields: Any) -> dict[str, Any]: ...

    async def complete_v2_job(self, **fields: Any) -> dict[str, Any]: ...

    async def record_stage(self, job_id: str, stage_name: str, status: str, **fields: Any) -> dict[str, Any]: ...

    async def list_stages(self, job_id: str) -> list[dict[str, Any]]: ...

    async def append_scene_version(self, **fields: Any) -> dict[str, Any]: ...

    async def list_scene_versions(self, scene_id: str, owner_session_id: str) -> list[dict[str, Any]]: ...

    async def list_recoverable_jobs(self, limit: int = 20) -> list[dict[str, Any]]: ...

    async def duplicate_scene(self, scene_id: str, owner_session_id: str) -> dict[str, Any] | None: ...

    async def soft_delete_scene(self, scene_id: str, owner_session_id: str) -> bool: ...
