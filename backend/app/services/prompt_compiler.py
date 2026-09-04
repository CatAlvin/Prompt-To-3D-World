from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from app.domain.scene_validator import SceneValidationError, SceneValidator
from app.providers.base import LLMProvider, ProviderError, ProviderResult


StatusCallback = Callable[[str], Awaitable[None]]


@dataclass(slots=True)
class CompiledScene:
    scene_json: dict[str, Any]
    provider: str
    model: str
    finish_reason: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    retry_count: int


class PromptCompiler:
    def __init__(
        self,
        provider: LLMProvider,
        validator: SceneValidator,
        max_repairs: int = 2,
    ) -> None:
        self.provider = provider
        self.validator = validator
        self.max_repairs = max_repairs

    async def compile(
        self,
        prompt: str,
        status_callback: StatusCallback | None = None,
    ) -> CompiledScene:
        repair_context: dict[str, Any] | None = None
        last_errors: list[str] = []
        prompt_tokens = 0
        completion_tokens = 0
        latest_result: ProviderResult | None = None

        for attempt in range(self.max_repairs + 1):
            if status_callback:
                await status_callback("generating")
            latest_result = await self.provider.generate_scene(
                prompt,
                self.validator.schema,
                repair_context,
            )
            prompt_tokens += latest_result.prompt_tokens or 0
            completion_tokens += latest_result.completion_tokens or 0

            if status_callback:
                await status_callback("validating")

            invalid_output: Any = latest_result.content
            try:
                if latest_result.finish_reason == "length":
                    raise SceneValidationError(["The provider response was truncated"])
                parsed = json.loads(latest_result.content)
                if not isinstance(parsed, dict):
                    raise SceneValidationError(["The provider response must be a JSON object"])
                invalid_output = parsed
                normalized = self.validator.validate_and_normalize(parsed, prompt)
                return CompiledScene(
                    scene_json=normalized,
                    provider=latest_result.provider,
                    model=latest_result.model,
                    finish_reason=latest_result.finish_reason,
                    prompt_tokens=prompt_tokens or None,
                    completion_tokens=completion_tokens or None,
                    retry_count=attempt,
                )
            except json.JSONDecodeError as exc:
                last_errors = [f"Invalid JSON at line {exc.lineno}, column {exc.colno}"]
            except SceneValidationError as exc:
                last_errors = exc.details

            if attempt < self.max_repairs:
                repair_context = {
                    "invalid_output": invalid_output,
                    "errors": last_errors,
                }

        raise ProviderError(
            "STRUCTURED_OUTPUT_INVALID",
            "生成结果未通过场景校验，请重新生成。",
            retryable=True,
        )

