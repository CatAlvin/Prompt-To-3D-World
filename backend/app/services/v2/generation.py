from __future__ import annotations

import asyncio
import logging
from copy import deepcopy
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from app.compilers.procedural import ProceduralSceneCompiler, build_local_plan, request_fingerprint
from app.compilers.style_kits import StyleKitRegistry
from app.domain.v2_validator import SceneV2Validator
from app.providers.base import ProviderError
from app.repositories.base import SceneRepository
from app.services.v2.plan_compiler import ScenePlanCompiler


logger = logging.getLogger(__name__)


class GenerationV2Service:
    def __init__(
        self,
        *,
        repository: SceneRepository,
        plan_compiler: ScenePlanCompiler,
        scene_compiler: ProceduralSceneCompiler,
        provider_name: str,
        model: str,
        generation_timeout_seconds: float = 360,
        auto_start: bool = True,
    ) -> None:
        self.repository = repository
        self.plan_compiler = plan_compiler
        self.scene_compiler = scene_compiler
        self.provider_name = provider_name
        self.model = model
        self.generation_timeout_seconds = generation_timeout_seconds
        self.auto_start = auto_start
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.registry = StyleKitRegistry()
        self.validator = SceneV2Validator()

    async def submit_job(self, *, owner_session_id: str, prompt: str, preferences: dict[str, Any], idempotency_key: str | None) -> dict[str, Any]:
        fingerprint = request_fingerprint(prompt, preferences)
        job = await self.repository.create_job(
            owner_session_id=owner_session_id,
            prompt=prompt,
            provider=self.provider_name,
            model=self.model,
            prompt_template_version="scene-plan-1.0.0",
            idempotency_key=idempotency_key,
            api_version="v2",
            request_json={"prompt": prompt, "preferences": preferences},
            request_fingerprint=fingerprint,
        )
        job_id = job["jobId"]
        if self.auto_start and job["status"] == "queued":
            self._start_task(job_id, owner_session_id, prompt, preferences, fingerprint)
        return job

    def _start_task(self, job_id: str, owner_session_id: str, prompt: str, preferences: dict[str, Any], fingerprint: str) -> None:
        if job_id in self.tasks:
            return
        task = asyncio.create_task(
            self.run_job(
                job_id=job_id,
                owner_session_id=owner_session_id,
                prompt=prompt,
                preferences=preferences,
                fingerprint=fingerprint,
            ),
            name=f"generation-v2:{job_id}",
        )
        self.tasks[job_id] = task
        task.add_done_callback(lambda _task, key=job_id: self.tasks.pop(key, None))

    async def recover_pending_jobs(self) -> int:
        recovered = 0
        for job in await self.repository.list_recoverable_jobs():
            if job.get("apiVersion") != "v2":
                continue
            request = job.get("request") or {}
            preferences = request.get("preferences") or {}
            fingerprint = job.get("requestFingerprint") or request_fingerprint(job["prompt"], preferences)
            if job["jobId"] not in self.tasks:
                self._start_task(job["jobId"], job["ownerSessionId"], job["prompt"], preferences, fingerprint)
                recovered += 1
        return recovered

    async def _stage(self, job_id: str, name: str, status: str, started: float | None = None, **fields: Any) -> None:
        if started is not None and "duration_ms" not in fields:
            fields["duration_ms"] = int((perf_counter() - started) * 1000)
        await self.repository.record_stage(job_id, name, status, **fields)

    async def run_job(self, *, job_id: str, owner_session_id: str, prompt: str, preferences: dict[str, Any], fingerprint: str) -> None:
        started = perf_counter()
        draft_ready = False
        local_plan: dict[str, Any] | None = None
        try:
            async with asyncio.timeout(self.generation_timeout_seconds):
                stage_started = perf_counter()
                await self._stage(job_id, "analyzing", "running")
                local_plan = build_local_plan(prompt, preferences)
                await self._stage(job_id, "analyzing", "completed", stage_started)

                stage_started = perf_counter()
                await self._stage(job_id, "building_draft", "running")
                draft_scene = self.scene_compiler.compile(
                    local_plan,
                    fingerprint=fingerprint,
                    version_kind="draft",
                    quality="draft",
                )
                draft = await self.repository.create_draft_version(
                    job_id=job_id,
                    owner_session_id=owner_session_id,
                    prompt=prompt,
                    scene_json=draft_scene,
                    plan_json=local_plan,
                    provider="local-procedural",
                    model="blockout-v2",
                )
                draft_ready = True
                await self._stage(
                    job_id,
                    "building_draft",
                    "completed",
                    stage_started,
                    checkpoint_version_id=draft["version"]["versionId"],
                )

                stage_started = perf_counter()
                await self._stage(job_id, "applying_style", "running")
                compiled_plan = await self.plan_compiler.compile(prompt, preferences)
                final_quality = preferences.get("quality", "balanced")
                if final_quality == "draft":
                    final_quality = "balanced"
                final_scene = self.scene_compiler.compile(
                    compiled_plan.plan,
                    fingerprint=fingerprint,
                    version_kind="final",
                    quality=final_quality,
                )
                await self._stage(job_id, "applying_style", "completed", stage_started)

                stage_started = perf_counter()
                await self._stage(job_id, "resolving_assets", "running")
                asset_refs = [node["assetRef"] for node in final_scene["nodes"] if node["kind"] == "asset"]
                known_assets = {item["id"] for item in self.registry.assets()}
                if any(asset_ref not in known_assets for asset_ref in asset_refs):
                    raise ValueError("Scene references an asset outside the curated catalog")
                await self._stage(
                    job_id,
                    "resolving_assets",
                    "completed",
                    stage_started,
                    metadata_json={"resolvedAssets": len(asset_refs), "fallbacksAvailable": len(asset_refs)},
                )

                final = await self.repository.complete_v2_job(
                    job_id=job_id,
                    owner_session_id=owner_session_id,
                    prompt=prompt,
                    scene_json=final_scene,
                    plan_json=compiled_plan.plan,
                    provider=compiled_plan.provider,
                    model=compiled_plan.model,
                    duration_ms=int((perf_counter() - started) * 1000),
                    prompt_tokens=compiled_plan.prompt_tokens,
                    completion_tokens=compiled_plan.completion_tokens,
                    retry_count=compiled_plan.retry_count,
                )
                await self._stage(
                    job_id,
                    "completed",
                    "completed",
                    checkpoint_version_id=final["version"]["versionId"],
                )
        except asyncio.CancelledError:
            await self.repository.update_job(
                job_id,
                status="partial" if draft_ready else "cancelled",
                current_stage="completed" if draft_ready else "cancelled",
                error_code="ENHANCEMENT_CANCELLED" if draft_ready else "GENERATION_CANCELLED",
                error_message="已停止增强，保留当前可探索草稿。" if draft_ready else "生成已取消。",
                duration_ms=int((perf_counter() - started) * 1000),
                completed_at=datetime.now(timezone.utc),
            )
            raise
        except TimeoutError:
            await self._preserve_or_fail(job_id, draft_ready, "GENERATION_TIMEOUT", "最终增强超时，已保留可探索草稿。", started)
        except ProviderError as exc:
            await self._preserve_or_fail(job_id, draft_ready, exc.code, exc.public_message, started)
        except Exception:
            logger.exception("V2 generation job %s failed", job_id)
            await self._preserve_or_fail(job_id, draft_ready, "INTERNAL_ERROR", "最终增强失败，已保留可探索草稿。", started)

    async def _preserve_or_fail(self, job_id: str, draft_ready: bool, code: str, message: str, started: float) -> None:
        await self.repository.update_job(
            job_id,
            status="partial" if draft_ready else "failed",
            current_stage="completed" if draft_ready else "failed",
            error_code=code,
            error_message=message,
            duration_ms=int((perf_counter() - started) * 1000),
            completed_at=datetime.now(timezone.utc),
        )
        await self.repository.record_stage(job_id, "completed", "failed", error_code=code)

    async def get_job(self, job_id: str, owner_session_id: str) -> dict[str, Any] | None:
        job = await self.repository.get_job(job_id, owner_session_id)
        if not job:
            return None
        job["stages"] = await self.repository.list_stages(job_id)
        if job.get("sceneId"):
            job["scene"] = await self.repository.get_scene(job["sceneId"], owner_session_id)
        if job.get("draftVersionId") and job.get("sceneId"):
            job["draft"] = await self.repository.get_scene_version(
                job["sceneId"], job["draftVersionId"], owner_session_id
            )
        return job

    async def cancel_job(self, job_id: str, owner_session_id: str) -> bool:
        job = await self.repository.get_job(job_id, owner_session_id)
        if not job or job["status"] in {"succeeded", "partial", "failed", "cancelled"}:
            return False
        task = self.tasks.get(job_id)
        if task:
            task.cancel()
            return True
        await self.repository.update_job(job_id, status="cancelled", current_stage="cancelled", completed_at=datetime.now(timezone.utc))
        return True

    async def apply_command(
        self,
        *,
        scene_id: str,
        owner_session_id: str,
        source_version_id: str,
        command_type: str,
        parameters: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        source = await self.repository.get_scene_version(scene_id, source_version_id, owner_session_id)
        if not source:
            raise LookupError("Source version not found")
        scene = deepcopy(source["version"]["sceneJson"])
        if scene.get("schemaVersion") != "2.0.0":
            raise ValueError("V2 commands require a Scene JSON 2.0 source version")
        summary = self._apply_typed_command(scene, command_type, parameters)
        self.validator.validate(scene)
        return await self.repository.append_scene_version(
            scene_id=scene_id,
            owner_session_id=owner_session_id,
            source_version_id=source_version_id,
            scene_json=scene,
            prompt=source["prompt"],
            provider="typed-command",
            model="scene-command-1.0",
            change_summary=summary,
            plan_json=source["version"].get("planJson"),
            command_type=command_type,
            command_json=parameters,
            idempotency_key=idempotency_key,
        )

    def _apply_typed_command(self, scene: dict[str, Any], command_type: str, parameters: dict[str, Any]) -> str:
        if command_type == "set_environment":
            exposure = float(parameters.get("exposure", scene["environment"]["exposure"]))
            fog_density = float(parameters.get("fogDensity", scene["environment"]["fog"]["density"]))
            scene["environment"]["exposure"] = max(0.2, min(3, exposure))
            scene["environment"]["fog"]["density"] = max(0, min(0.2, fog_density))
            weather = parameters.get("weather")
            if weather in {"clear", "rain", "mist", "dust"}:
                scene["extensions"]["weather"] = weather
                scene["extensions"]["wetness"] = 0.88 if weather == "rain" else 0.08
            return "Adjusted environment, weather and exposure"
        if command_type == "set_style_kit":
            style_id = str(parameters.get("styleKit", ""))
            style = self.registry.get(style_id)
            palette = style["palette"]
            scene["pipeline"]["styleKit"] = style_id
            scene["environment"]["background"] = palette["background"]
            scene["environment"]["fog"]["color"] = palette["fog"]
            for node in scene["nodes"]:
                material = node.get("material") or node.get("source", {}).get("material")
                if not material:
                    continue
                category = node["semantics"]["category"]
                material["color"] = palette["ground"] if category in {"ground", "floor", "path"} else palette["primary"]
                if node["kind"] == "text":
                    material["color"] = palette["accent"]
                    material["emissive"] = palette["accent"]
            return f"Applied Style Kit {style_id} while preserving layout"
        if command_type == "set_density":
            density = max(0.2, min(1.0, float(parameters.get("density", 0.68))))
            for node in scene["nodes"]:
                if node["kind"] == "instances":
                    keep = max(1, round(len(node["instances"]) * density))
                    node["instances"] = node["instances"][:keep]
                if node["kind"] == "procedural":
                    node["parameters"]["count"] = max(1, round(node["parameters"]["count"] * density))
            return f"Set procedural detail density to {density:.2f}"
        if command_type == "remove_by_semantics":
            target = str(parameters.get("semantic", "")).strip().lower()
            if not target:
                raise ValueError("semantic is required")
            scene["nodes"] = [
                node
                for node in scene["nodes"]
                if node["semantics"]["category"].lower() != target
                and target not in {tag.lower() for tag in node["semantics"]["tags"]}
                or (node["kind"] == "primitive" and node.get("collision", {}).get("mode") == "ground")
            ]
            return f"Removed objects matching semantic {target}"
        raise ValueError("Unsupported Scene Command")

    async def list_versions(self, scene_id: str, owner_session_id: str) -> list[dict[str, Any]]:
        return await self.repository.list_scene_versions(scene_id, owner_session_id)

    async def restore_version(self, scene_id: str, version_id: str, owner_session_id: str) -> dict[str, Any]:
        source = await self.repository.get_scene_version(scene_id, version_id, owner_session_id)
        if not source:
            raise LookupError("Version not found")
        return await self.repository.append_scene_version(
            scene_id=scene_id,
            owner_session_id=owner_session_id,
            source_version_id=version_id,
            scene_json=deepcopy(source["version"]["sceneJson"]),
            prompt=source["prompt"],
            provider="version-restore",
            model="scene-versioning-1.0",
            change_summary=f"Restored version {source['version']['versionNumber']} as a new version",
            plan_json=source["version"].get("planJson"),
        )

    async def duplicate_scene(self, scene_id: str, owner_session_id: str) -> dict[str, Any] | None:
        return await self.repository.duplicate_scene(scene_id, owner_session_id)

    async def delete_scene(self, scene_id: str, owner_session_id: str) -> bool:
        return await self.repository.soft_delete_scene(scene_id, owner_session_id)

    async def shutdown(self) -> None:
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
