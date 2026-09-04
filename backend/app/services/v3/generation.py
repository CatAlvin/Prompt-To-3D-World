from __future__ import annotations

import asyncio
import hashlib
import logging
from copy import deepcopy
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from app.compilers.procedural import request_fingerprint
from app.domain.v3_validator import SceneV3Validator
from app.providers.base import ProviderError
from app.repositories.base import SceneRepository
from app.services.v3.capability_registry import CapabilityRegistry
from app.services.v3.fidelity import SemanticFidelityEvaluator
from app.services.v3.intent_compiler import (
    INTENT_TEMPLATE_VERSION,
    SceneIntentCompiler,
    build_local_intent,
    summarize_intent,
)
from app.services.v3.layout_solver import LayoutSolver
from app.services.v3.recipe_compiler import VisualRecipeCompiler


logger = logging.getLogger(__name__)


class FidelityGateError(RuntimeError):
    pass


class GenerationV3Service:
    def __init__(
        self,
        *,
        repository: SceneRepository,
        intent_compiler: SceneIntentCompiler,
        scene_compiler: VisualRecipeCompiler,
        provider_name: str,
        model: str,
        generation_timeout_seconds: float = 360,
        auto_start: bool = True,
    ) -> None:
        self.repository = repository
        self.intent_compiler = intent_compiler
        self.scene_compiler = scene_compiler
        self.provider_name = provider_name
        self.model = model
        self.generation_timeout_seconds = generation_timeout_seconds
        self.auto_start = auto_start
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.capabilities = CapabilityRegistry()
        self.layout_solver = LayoutSolver()
        self.evaluator = SemanticFidelityEvaluator()
        self.validator = SceneV3Validator()

    async def submit_job(
        self,
        *,
        owner_session_id: str,
        prompt: str,
        preferences: dict[str, Any],
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        fingerprint = request_fingerprint(prompt, preferences)
        local_intent = build_local_intent(prompt, preferences)
        job = await self.repository.create_job(
            owner_session_id=owner_session_id,
            prompt=prompt,
            provider=self.provider_name,
            model=self.model,
            prompt_template_version=INTENT_TEMPLATE_VERSION,
            idempotency_key=idempotency_key,
            api_version="v3",
            request_json={
                "prompt": prompt,
                "preferences": preferences,
                "intentPreview": summarize_intent(local_intent),
            },
            request_fingerprint=fingerprint,
        )
        job["intentPreview"] = (job.get("request") or {}).get("intentPreview")
        if self.auto_start and job["status"] == "queued":
            self._start_task(job["jobId"], owner_session_id, prompt, preferences, fingerprint)
        return job

    def _start_task(
        self,
        job_id: str,
        owner_session_id: str,
        prompt: str,
        preferences: dict[str, Any],
        fingerprint: str,
    ) -> None:
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
            name=f"generation-v3:{job_id}",
        )
        self.tasks[job_id] = task
        task.add_done_callback(lambda _task, key=job_id: self.tasks.pop(key, None))

    async def recover_pending_jobs(self) -> int:
        recovered = 0
        for job in await self.repository.list_recoverable_jobs():
            if job.get("apiVersion") != "v3":
                continue
            request = job.get("request") or {}
            preferences = request.get("preferences") or {}
            fingerprint = job.get("requestFingerprint") or request_fingerprint(job["prompt"], preferences)
            if job["jobId"] not in self.tasks:
                self._start_task(job["jobId"], job["ownerSessionId"], job["prompt"], preferences, fingerprint)
                recovered += 1
        return recovered

    async def _stage(
        self,
        job_id: str,
        name: str,
        status: str,
        started: float | None = None,
        **fields: Any,
    ) -> None:
        if started is not None and "duration_ms" not in fields:
            fields["duration_ms"] = int((perf_counter() - started) * 1000)
        await self.repository.record_stage(job_id, name, status, **fields)

    @staticmethod
    def _fidelity_failure_message(report: dict[str, Any]) -> str:
        problems: list[str] = []
        if report["requiredCoverage"] < 0.95:
            problems.append(f"关键内容覆盖率 {report['requiredCoverage']:.0%}（要求至少 95%）")
        if report["relationSatisfaction"] < 0.9:
            problems.append(f"空间关系满足率 {report['relationSatisfaction']:.0%}（要求至少 90%）")
        if report["forbiddenViolations"]:
            problems.append(f"出现 {report['forbiddenViolations']} 个明确禁止的内容")
        if report["unrelatedRatio"] > 0.1:
            problems.append(f"无关内容占比 {report['unrelatedRatio']:.0%}（上限 10%）")
        if not report["heroVisible"]:
            problems.append("主角物体不在初始镜头内")
        return "；".join(problems) or "未通过相关性核对"

    def _build_scene(
        self,
        intent: dict[str, Any],
        *,
        fingerprint: str,
        version_kind: str,
        quality: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        resolutions = self.capabilities.resolve_all(intent)
        layout = self.layout_solver.solve(intent)
        scene = self.scene_compiler.compile(
            intent,
            resolutions,
            layout,
            fingerprint=fingerprint,
            version_kind=version_kind,
            quality=quality,
        )
        fidelity = self.evaluator.evaluate(intent, scene, resolutions, layout)
        self.validator.validate(scene, intent)
        envelope = {
            "kind": "v3",
            "intent": intent,
            "intentPreview": summarize_intent(intent, resolutions),
            "resolutionTrace": resolutions,
            "layout": layout,
            "fidelityReport": fidelity.report,
            "unsupportedEntities": fidelity.unsupported_entities,
        }
        return scene, envelope

    async def run_job(
        self,
        *,
        job_id: str,
        owner_session_id: str,
        prompt: str,
        preferences: dict[str, Any],
        fingerprint: str,
    ) -> None:
        started = perf_counter()
        draft_ready = False
        try:
            async with asyncio.timeout(self.generation_timeout_seconds):
                stage_started = perf_counter()
                await self._stage(job_id, "interpreting", "running")
                local_intent = build_local_intent(prompt, preferences)
                await self._stage(
                    job_id,
                    "interpreting",
                    "completed",
                    stage_started,
                    metadata_json={"intentPreview": summarize_intent(local_intent)},
                )

                stage_started = perf_counter()
                await self._stage(job_id, "resolving", "running")
                draft_resolutions = self.capabilities.resolve_all(local_intent)
                await self._stage(
                    job_id,
                    "resolving",
                    "completed",
                    stage_started,
                    metadata_json={
                        "exact": sum(item["support"] == "exact" for item in draft_resolutions),
                        "abstract": sum(item["support"] == "abstract" for item in draft_resolutions),
                    },
                )

                stage_started = perf_counter()
                await self._stage(job_id, "composing_draft", "running")
                draft_scene, draft_envelope = self._build_scene(
                    local_intent,
                    fingerprint=fingerprint,
                    version_kind="draft",
                    quality="draft",
                )
                draft = await self.repository.create_draft_version(
                    job_id=job_id,
                    owner_session_id=owner_session_id,
                    prompt=prompt,
                    scene_json=draft_scene,
                    plan_json=draft_envelope,
                    provider="local-intent",
                    model="intent-blockout-v3",
                )
                draft_ready = True
                await self._stage(
                    job_id,
                    "composing_draft",
                    "completed",
                    stage_started,
                    checkpoint_version_id=draft["version"]["versionId"],
                )

                stage_started = perf_counter()
                await self._stage(job_id, "enhancing", "running")
                compiled_intent = await self.intent_compiler.compile(prompt, preferences)
                await self._stage(
                    job_id,
                    "enhancing",
                    "completed",
                    stage_started,
                    metadata_json={"intentPreview": summarize_intent(compiled_intent.intent)},
                )

                stage_started = perf_counter()
                await self._stage(job_id, "composing_final", "running")
                final_quality = preferences.get("quality", "balanced")
                if final_quality == "draft":
                    final_quality = "balanced"
                final_scene, final_envelope = self._build_scene(
                    compiled_intent.intent,
                    fingerprint=fingerprint,
                    version_kind="final",
                    quality=final_quality,
                )
                await self._stage(job_id, "composing_final", "completed", stage_started)

                stage_started = perf_counter()
                await self._stage(job_id, "checking_fidelity", "running")
                fidelity = final_envelope["fidelityReport"]
                fidelity_metadata = {
                    "fidelityReport": fidelity,
                    "intentPreview": final_envelope["intentPreview"],
                    "unsupportedEntities": final_envelope["unsupportedEntities"],
                }
                if fidelity["status"] != "passed":
                    await self._stage(
                        job_id,
                        "checking_fidelity",
                        "failed",
                        stage_started,
                        error_code="FIDELITY_GATE_FAILED",
                        metadata_json=fidelity_metadata,
                    )
                    raise FidelityGateError(self._fidelity_failure_message(fidelity))
                await self._stage(
                    job_id,
                    "checking_fidelity",
                    "completed",
                    stage_started,
                    metadata_json=fidelity_metadata,
                )

                final = await self.repository.complete_v2_job(
                    job_id=job_id,
                    owner_session_id=owner_session_id,
                    prompt=prompt,
                    scene_json=final_scene,
                    plan_json=final_envelope,
                    provider=compiled_intent.provider,
                    model=compiled_intent.model,
                    duration_ms=int((perf_counter() - started) * 1000),
                    prompt_tokens=compiled_intent.prompt_tokens,
                    completion_tokens=compiled_intent.completion_tokens,
                    retry_count=compiled_intent.retry_count,
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
        except FidelityGateError as exc:
            await self._preserve_or_fail(job_id, draft_ready, "FIDELITY_GATE_FAILED", f"{exc}。已保留可探索草稿。", started)
        except TimeoutError:
            await self._preserve_or_fail(job_id, draft_ready, "GENERATION_TIMEOUT", "视觉增强超时，已保留可探索草稿。", started)
        except ProviderError as exc:
            await self._preserve_or_fail(job_id, draft_ready, exc.code, exc.public_message, started)
        except Exception:
            logger.exception("V3 generation job %s failed", job_id)
            await self._preserve_or_fail(job_id, draft_ready, "INTERNAL_ERROR", "场景组合失败，已保留可探索草稿。", started)

    async def _preserve_or_fail(
        self,
        job_id: str,
        draft_ready: bool,
        code: str,
        message: str,
        started: float,
    ) -> None:
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

    @staticmethod
    def _metadata_from_detail(detail: dict[str, Any] | None) -> dict[str, Any] | None:
        if not detail:
            return None
        plan = detail.get("version", {}).get("planJson") or {}
        return plan if plan.get("kind") == "v3" else None

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
        scene_metadata = self._metadata_from_detail(job.get("scene"))
        draft_metadata = self._metadata_from_detail(job.get("draft"))
        stage_metadata = {
            stage["stage"]: stage.get("metadataJson") or {}
            for stage in job["stages"]
        }
        enhanced = stage_metadata.get("enhancing", {})
        fidelity_stage = stage_metadata.get("checking_fidelity", {})
        request = job.get("request") or {}
        job["intentPreview"] = (
            (scene_metadata or {}).get("intentPreview")
            or fidelity_stage.get("intentPreview")
            or enhanced.get("intentPreview")
            or (draft_metadata or {}).get("intentPreview")
            or request.get("intentPreview")
        )
        job["coverage"] = (
            (scene_metadata or {}).get("fidelityReport")
            or fidelity_stage.get("fidelityReport")
            or (draft_metadata or {}).get("fidelityReport")
        )
        job["unsupportedEntities"] = (
            (scene_metadata or {}).get("unsupportedEntities")
            or fidelity_stage.get("unsupportedEntities")
            or (draft_metadata or {}).get("unsupportedEntities")
            or []
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
        await self.repository.update_job(
            job_id,
            status="cancelled",
            current_stage="cancelled",
            completed_at=datetime.now(timezone.utc),
        )
        return True

    @staticmethod
    def _new_entity_id(concept: str, existing: set[str]) -> str:
        digest = hashlib.sha1(concept.encode("utf-8")).hexdigest()[:8]
        base = f"entity_user_{digest}"
        candidate = base
        index = 2
        while candidate in existing:
            candidate = f"{base}_{index}"
            index += 1
        return candidate

    def _apply_intent_command(
        self,
        intent: dict[str, Any],
        command_type: str,
        parameters: dict[str, Any],
    ) -> str:
        entities = intent["entities"]
        entity_ids = {entity["id"] for entity in entities}
        if command_type in {"remove_entity", "remove_by_semantics"}:
            entity_id = str(parameters.get("entityId", "")).strip()
            semantic = str(parameters.get("semantic", "")).strip().lower()
            removed = [
                entity
                for entity in entities
                if entity["id"] == entity_id
                or (semantic and (entity["concept"].lower() == semantic or entity["category"].lower() == semantic))
            ]
            if not removed:
                raise ValueError("没有找到要移除的实体")
            removed_ids = {entity["id"] for entity in removed}
            if len(removed_ids) == len(entities):
                raise ValueError("场景至少需要保留一个实体")
            intent["entities"] = [entity for entity in entities if entity["id"] not in removed_ids]
            intent["relations"] = [
                relation for relation in intent["relations"]
                if relation["sourceId"] not in removed_ids and relation["targetId"] not in removed_ids
            ]
            for key in ("requiredEntities", "optionalEntities"):
                intent["constraints"][key] = [
                    current for current in intent["constraints"][key] if current not in removed_ids
                ]
            if intent["cameraIntent"]["heroEntityId"] in removed_ids:
                intent["cameraIntent"]["heroEntityId"] = intent["entities"][0]["id"]
                intent["entities"][0]["role"] = "hero"
            return f"移除了 {len(removed_ids)} 个语义实体"
        if command_type == "replace_entity":
            entity_id = str(parameters.get("entityId", ""))
            concept = str(parameters.get("concept", "")).strip()
            if not concept:
                raise ValueError("concept 不能为空")
            entity = next((item for item in entities if item["id"] == entity_id), None)
            if entity is None:
                raise ValueError("没有找到要替换的实体")
            entity["concept"] = concept[:64]
            entity["sourceText"] = concept[:200]
            if parameters.get("category") in {"celestial", "environment", "architecture", "nature", "prop", "effect", "abstract"}:
                entity["category"] = parameters["category"]
            return f"将实体替换为 {concept}"
        if command_type == "add_entity":
            concept = str(parameters.get("concept", "")).strip()
            if not concept:
                raise ValueError("concept 不能为空")
            entity_id = self._new_entity_id(concept, entity_ids)
            category = parameters.get("category", "abstract")
            if category not in {"celestial", "environment", "architecture", "nature", "prop", "effect", "abstract"}:
                category = "abstract"
            intent["entities"].append(
                {
                    "id": entity_id,
                    "concept": concept[:64],
                    "category": category,
                    "role": "supporting",
                    "importance": 0.8,
                    "count": 1,
                    "attributes": {
                        "color": None,
                        "size": None,
                        "label": str(parameters.get("label"))[:40] if parameters.get("label") else None,
                        "state": None,
                        "brightness": None,
                    },
                    "sourceText": concept[:200],
                }
            )
            intent["constraints"]["requiredEntities"].append(entity_id)
            return f"添加了实体 {concept}"
        if command_type == "change_relation":
            source_id = str(parameters.get("sourceId", ""))
            target_id = str(parameters.get("targetId", ""))
            relation_type = str(parameters.get("relation", ""))
            allowed = {"left_of", "right_of", "in_front_of", "behind", "near", "far_from", "inside", "around", "orbiting", "above", "below", "facing", "connected_to"}
            if source_id not in entity_ids or target_id not in entity_ids or relation_type not in allowed:
                raise ValueError("关系参数无效")
            intent["relations"] = [
                relation for relation in intent["relations"]
                if not (relation["sourceId"] == source_id and relation["targetId"] == target_id)
            ]
            intent["relations"].append({"sourceId": source_id, "type": relation_type, "targetId": target_id, "strength": 1.0})
            return "更新了实体空间关系"
        if command_type == "change_scene_mode":
            mode = parameters.get("sceneMode")
            if mode not in {"walkable", "interior", "orbital", "flythrough", "diorama", "panorama"}:
                raise ValueError("场景模式无效")
            intent["sceneMode"] = mode
            intent["constraints"]["navigationRequired"] = mode in {"walkable", "interior"}
            return f"场景模式改为 {mode}"
        if command_type == "set_environment":
            if parameters.get("weather") in {"clear", "rain", "mist", "dust"}:
                intent["environment"]["weather"] = parameters["weather"]
            if parameters.get("time") in {"day", "sunrise", "sunset", "night", "indoor"}:
                intent["environment"]["time"] = parameters["time"]
            return "调整了环境与天气"
        if command_type == "set_style_kit":
            style = parameters.get("styleKit")
            if style not in {"cyberpunk_tokyo_v1", "cozy_lowpoly_v1", "misty_nature_v1", "lunar_research_v1"}:
                raise ValueError("Style Kit 无效")
            intent["styleIntent"]["styleKit"] = style
            return f"应用了 Style Kit {style}"
        if command_type == "set_density":
            density = max(0.2, min(1.0, float(parameters.get("density", 0.68))))
            for entity in entities:
                if entity["role"] in {"supporting", "background"} and entity["count"] > 1:
                    entity["count"] = max(1, round(entity["count"] * density))
            return f"细节密度调整为 {density:.2f}"
        raise ValueError("不支持的 V3 场景命令")

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
        source_plan = source["version"].get("planJson") or {}
        if source_plan.get("kind") != "v3":
            raise ValueError("V3 commands require a Scene JSON 3.0 source version")
        intent = deepcopy(source_plan["intent"])
        summary = self._apply_intent_command(intent, command_type, parameters)
        fingerprint = source["version"]["sceneJson"]["pipeline"]["requestFingerprint"]
        quality = source["version"]["sceneJson"]["pipeline"]["quality"]
        if quality == "draft":
            quality = "balanced"
        scene, envelope = self._build_scene(
            intent,
            fingerprint=fingerprint,
            version_kind="final",
            quality=quality,
        )
        if envelope["fidelityReport"]["status"] != "passed":
            raise ValueError("修改后关键内容未通过相关性核对")
        if command_type == "set_environment":
            if "exposure" in parameters:
                scene["environment"]["exposure"] = max(0.2, min(3, float(parameters["exposure"])))
            if "fogDensity" in parameters:
                scene["environment"]["fog"]["density"] = max(0, min(0.2, float(parameters["fogDensity"])))
        self.validator.validate(scene, intent)
        return await self.repository.append_scene_version(
            scene_id=scene_id,
            owner_session_id=owner_session_id,
            source_version_id=source_version_id,
            scene_json=scene,
            prompt=source["prompt"],
            provider="typed-command",
            model="scene-command-3.0",
            change_summary=summary,
            plan_json=envelope,
            command_type=command_type,
            command_json=parameters,
            idempotency_key=idempotency_key,
        )

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
            model="scene-versioning-3.0",
            change_summary=f"将版本 {source['version']['versionNumber']} 恢复为新版本",
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
