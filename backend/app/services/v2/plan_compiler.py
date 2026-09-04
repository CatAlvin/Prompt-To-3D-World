from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.compilers.procedural import build_local_plan, specialized_archetype
from app.domain.scene_validator import SceneValidationError
from app.domain.v2_validator import ScenePlanValidator
from app.providers.base import ProviderError, ProviderResult


@dataclass(slots=True)
class CompiledPlan:
    plan: dict[str, Any]
    provider: str
    model: str
    prompt_tokens: int | None
    completion_tokens: int | None
    retry_count: int


class ScenePlanCompiler:
    def __init__(self, provider: Any, validator: ScenePlanValidator | None = None, max_repairs: int = 1) -> None:
        self.provider = provider
        self.validator = validator or ScenePlanValidator()
        self.max_repairs = max_repairs

    @staticmethod
    def _apply_preferences(plan: dict[str, Any], preferences: dict[str, Any]) -> dict[str, Any]:
        for source, target in (
            ("styleKit", "styleKit"),
            ("time", "time"),
            ("weather", "weather"),
            ("density", "density"),
            ("scale", "scale"),
            ("seed", "seed"),
        ):
            value = preferences.get(source)
            if value is not None and value != "auto":
                plan[target] = value
        return plan

    @staticmethod
    def _align_specialized_plan(
        prompt: str,
        plan: dict[str, Any],
        preferences: dict[str, Any],
    ) -> dict[str, Any]:
        required_archetype = specialized_archetype(prompt)
        if required_archetype is None:
            return plan
        canonical = build_local_plan(prompt, preferences)
        for key in (
            "title",
            "archetype",
            "visualDirection",
            "seed",
            "styleKit",
            "time",
            "weather",
            "mainPath",
            "zones",
            "heroAnchors",
            "mustInclude",
            "avoid",
        ):
            plan[key] = canonical[key]
        return plan

    async def compile(self, prompt: str, preferences: dict[str, Any]) -> CompiledPlan:
        if not hasattr(self.provider, "generate_plan"):
            return CompiledPlan(
                plan=build_local_plan(prompt, preferences),
                provider=getattr(self.provider, "name", "local"),
                model=getattr(self.provider, "model", "local-plan"),
                prompt_tokens=None,
                completion_tokens=None,
                retry_count=0,
            )
        repair_context: dict[str, Any] | None = None
        prompt_tokens = 0
        completion_tokens = 0
        last_errors: list[str] = []
        latest: ProviderResult | None = None
        for attempt in range(self.max_repairs + 1):
            latest = await self.provider.generate_plan(prompt, preferences, self.validator.schema, repair_context)
            prompt_tokens += latest.prompt_tokens or 0
            completion_tokens += latest.completion_tokens or 0
            invalid: Any = latest.content
            try:
                if latest.finish_reason == "length":
                    raise SceneValidationError(["The provider plan was truncated"])
                parsed = json.loads(latest.content)
                if not isinstance(parsed, dict):
                    raise SceneValidationError(["The provider plan must be a JSON object"])
                invalid = parsed
                plan = self._apply_preferences(parsed, preferences)
                plan = self._align_specialized_plan(prompt, plan, preferences)
                self.validator.validate(plan)
                return CompiledPlan(
                    plan=plan,
                    provider=latest.provider,
                    model=latest.model,
                    prompt_tokens=prompt_tokens or None,
                    completion_tokens=completion_tokens or None,
                    retry_count=attempt,
                )
            except json.JSONDecodeError as exc:
                last_errors = [f"Invalid JSON at line {exc.lineno}, column {exc.colno}"]
            except SceneValidationError as exc:
                last_errors = exc.details
            repair_context = {"invalid_output": invalid, "errors": last_errors}
        raise ProviderError("PLAN_OUTPUT_INVALID", "Kimi 场景规划未通过校验，已保留可探索草稿。", True)
