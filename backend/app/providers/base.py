from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(slots=True)
class ProviderResult:
    content: str
    provider: str
    model: str
    finish_reason: str | None
    prompt_tokens: int | None
    completion_tokens: int | None


class ProviderError(RuntimeError):
    def __init__(
        self,
        code: str,
        public_message: str,
        retryable: bool = False,
        debug_detail: str | None = None,
    ) -> None:
        self.code = code
        self.public_message = public_message
        self.retryable = retryable
        self.debug_detail = debug_detail
        super().__init__(public_message)


class LLMProvider(Protocol):
    name: str
    model: str

    async def generate_scene(
        self,
        prompt: str,
        schema: dict[str, Any],
        repair_context: dict[str, Any] | None = None,
    ) -> ProviderResult: ...
