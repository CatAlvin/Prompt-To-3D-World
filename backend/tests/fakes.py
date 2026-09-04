from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import ROOT_DIR
from app.providers.base import ProviderResult


def load_example_scene() -> dict[str, Any]:
    path = ROOT_DIR / "shared" / "examples" / "cyberpunk-alley.json"
    return json.loads(path.read_text(encoding="utf-8"))


class FakeProvider:
    name = "fake"
    model = "fake-scene-model"

    def __init__(self, outputs: list[Any] | None = None) -> None:
        self.outputs = list(outputs or [load_example_scene()])
        self.calls: list[dict[str, Any] | None] = []

    async def generate_scene(
        self,
        prompt: str,
        schema: dict[str, Any],
        repair_context: dict[str, Any] | None = None,
    ) -> ProviderResult:
        self.calls.append(repair_context)
        output = self.outputs.pop(0)
        content = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
        return ProviderResult(
            content=content,
            provider=self.name,
            model=self.model,
            finish_reason="stop",
            prompt_tokens=120,
            completion_tokens=680,
        )


class InMemoryRepository:
    def __init__(self) -> None:
        self.jobs: dict[str, dict[str, Any]] = {}
        self.scenes: dict[str, dict[str, Any]] = {}
        self._job_count = 0
        self._scene_count = 0

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    async def create_job(
        self,
        *,
        owner_session_id: str,
        prompt: str,
        provider: str,
        model: str,
        prompt_template_version: str,
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        if idempotency_key:
            for job in self.jobs.values():
                if job["ownerSessionId"] == owner_session_id and job["idempotencyKey"] == idempotency_key:
                    return deepcopy(job)
        self._job_count += 1
        now = self._now()
        job = {
            "jobId": f"gen_test_{self._job_count}",
            "ownerSessionId": owner_session_id,
            "idempotencyKey": idempotency_key,
            "status": "queued",
            "prompt": prompt,
            "provider": provider,
            "model": model,
            "error": None,
            "durationMs": None,
            "usage": {"promptTokens": None, "completionTokens": None},
            "retryCount": 0,
            "sceneId": None,
            "sceneVersionId": None,
            "createdAt": now,
            "updatedAt": now,
            "completedAt": None,
        }
        self.jobs[job["jobId"]] = job
        return deepcopy(job)

    async def get_job(self, job_id: str, owner_session_id: str) -> dict[str, Any] | None:
        job = self.jobs.get(job_id)
        if not job or job["ownerSessionId"] != owner_session_id:
            return None
        public = deepcopy(job)
        public.pop("ownerSessionId", None)
        public.pop("idempotencyKey", None)
        return public

    async def update_job(self, job_id: str, **fields: Any) -> dict[str, Any] | None:
        job = self.jobs.get(job_id)
        if not job:
            return None
        mapping = {
            "error_code": ("error", "code"),
            "error_message": ("error", "message"),
            "duration_ms": ("durationMs", None),
            "prompt_tokens": ("usage", "promptTokens"),
            "completion_tokens": ("usage", "completionTokens"),
            "retry_count": ("retryCount", None),
            "scene_id": ("sceneId", None),
            "scene_version_id": ("sceneVersionId", None),
            "completed_at": ("completedAt", None),
            "status": ("status", None),
        }
        for key, value in fields.items():
            target, child = mapping[key]
            if target == "error":
                job["error"] = job.get("error") or {"code": None, "message": None}
                job["error"][child] = value
            elif child:
                job[target][child] = value
            else:
                job[target] = value.isoformat() if isinstance(value, datetime) else value
        job["updatedAt"] = self._now()
        return await self.get_job(job_id, job["ownerSessionId"])

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
        self._scene_count += 1
        scene_id = f"scene_test_{self._scene_count}"
        version_id = f"ver_test_{self._scene_count}"
        now = self._now()
        scene = {
            "sceneId": scene_id,
            "ownerSessionId": owner_session_id,
            "title": scene_json["title"],
            "currentVersionId": version_id,
            "prompt": prompt,
            "schemaVersion": scene_json["schemaVersion"],
            "nodeCount": len(scene_json["nodes"]),
            "createdAt": now,
            "updatedAt": now,
            "version": {
                "versionId": version_id,
                "versionNumber": 1,
                "schemaVersion": scene_json["schemaVersion"],
                "sceneJson": deepcopy(scene_json),
                "prompt": prompt,
                "seed": scene_json["seed"],
                "provider": provider,
                "model": model,
                "createdAt": now,
            },
        }
        self.scenes[scene_id] = scene
        job = self.jobs[job_id]
        job.update(
            {
                "status": "succeeded",
                "durationMs": duration_ms,
                "usage": {"promptTokens": prompt_tokens, "completionTokens": completion_tokens},
                "retryCount": retry_count,
                "sceneId": scene_id,
                "sceneVersionId": version_id,
                "completedAt": now,
                "updatedAt": now,
                "error": None,
            }
        )
        public = deepcopy(scene)
        public.pop("ownerSessionId", None)
        return public

    async def list_scenes(self, owner_session_id: str, limit: int = 30) -> list[dict[str, Any]]:
        items = []
        for scene in reversed(list(self.scenes.values())):
            if scene["ownerSessionId"] != owner_session_id:
                continue
            item = deepcopy(scene)
            item.pop("ownerSessionId", None)
            item.pop("version", None)
            items.append(item)
        return items[:limit]

    async def get_scene(self, scene_id: str, owner_session_id: str) -> dict[str, Any] | None:
        scene = self.scenes.get(scene_id)
        if not scene or scene["ownerSessionId"] != owner_session_id:
            return None
        public = deepcopy(scene)
        public.pop("ownerSessionId", None)
        return public

    async def get_scene_version(
        self,
        scene_id: str,
        version_id: str,
        owner_session_id: str,
    ) -> dict[str, Any] | None:
        scene = await self.get_scene(scene_id, owner_session_id)
        if not scene or scene["version"]["versionId"] != version_id:
            return None
        return scene

    async def health(self) -> bool:
        return True

