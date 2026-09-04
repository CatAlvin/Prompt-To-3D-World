from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.config import Settings
from app.domain.scene_validator import load_scene_schema
from app.providers.kimi import KimiProvider
from tests.fakes import load_example_scene


class FakeCompletionStream:
    def __init__(self, chunks: list[SimpleNamespace]) -> None:
        self.chunks = chunks

    def __aiter__(self):
        self.iterator = iter(self.chunks)
        return self

    async def __anext__(self):
        try:
            return next(self.iterator)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


@pytest.mark.asyncio
async def test_kimi_adapter_requests_strict_json_schema() -> None:
    scene_json = json.dumps(load_example_scene(), ensure_ascii=False)
    create = AsyncMock(
        return_value=FakeCompletionStream(
            [
                SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(content=scene_json[:100]),
                            finish_reason=None,
                        )
                    ],
                    usage=None,
                ),
                SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(content=scene_json[100:]),
                            finish_reason="stop",
                        )
                    ],
                    usage=None,
                ),
                SimpleNamespace(
                    choices=[],
                    usage=SimpleNamespace(prompt_tokens=33, completion_tokens=77),
                ),
            ]
        )
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    settings = Settings(
        moonshot_api_key="test_key_not_real",
        kimi_model="kimi-k3",
        database_url_override="sqlite+aiosqlite:///:memory:",
    )
    provider = KimiProvider(settings, client=client)

    result = await provider.generate_scene("cyberpunk alley", load_scene_schema())

    assert result.model == "kimi-k3"
    kwargs = create.await_args.kwargs
    assert kwargs["response_format"]["type"] == "json_schema"
    assert kwargs["response_format"]["json_schema"]["strict"] is True
    assert kwargs["reasoning_effort"] == "low"
    assert kwargs["stream"] is True
    assert kwargs["stream_options"]["include_usage"] is True
    assert "test_key_not_real" not in json.dumps(kwargs)
    assert result.prompt_tokens == 33
    assert result.completion_tokens == 77
