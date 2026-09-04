from __future__ import annotations

import asyncio

import httpx
import pytest

from app.config import Settings
from app.domain.scene_validator import SceneValidator
from app.main import create_app
from app.services.generation import GenerationService
from app.services.prompt_compiler import PromptCompiler
from tests.fakes import FakeProvider, InMemoryRepository, load_example_scene


def make_service(outputs: list[object] | None = None) -> tuple[GenerationService, InMemoryRepository, FakeProvider]:
    repository = InMemoryRepository()
    provider = FakeProvider(outputs)
    compiler = PromptCompiler(provider, SceneValidator(), max_repairs=2)
    service = GenerationService(
        repository=repository,
        compiler=compiler,
        provider_name=provider.name,
        model=provider.model,
        prompt_template_version="test-1",
    )
    return service, repository, provider


@pytest.mark.asyncio
async def test_compiler_repairs_invalid_output_once() -> None:
    provider = FakeProvider(["not json", load_example_scene()])
    compiler = PromptCompiler(provider, SceneValidator(), max_repairs=2)
    compiled = await compiler.compile("cyberpunk alley")
    assert compiled.retry_count == 1
    assert provider.calls[0] is None
    assert provider.calls[1] is not None


@pytest.mark.asyncio
async def test_generation_service_persists_an_immutable_scene_version() -> None:
    service, repository, _ = make_service()
    job = await repository.create_job(
        owner_session_id="session_test_123",
        prompt="cyberpunk alley",
        provider="fake",
        model="fake-scene-model",
        prompt_template_version="test-1",
        idempotency_key=None,
    )
    await service.run_job(
        job_id=job["jobId"],
        owner_session_id="session_test_123",
        prompt="cyberpunk alley",
    )
    completed = await service.get_job(job["jobId"], "session_test_123")
    assert completed is not None
    assert completed["status"] == "succeeded"
    assert completed["scene"]["version"]["versionNumber"] == 1
    assert completed["scene"]["version"]["sceneJson"]["schemaVersion"] == "1.0.0"


@pytest.mark.asyncio
async def test_generation_service_enforces_an_overall_timeout() -> None:
    class SlowProvider(FakeProvider):
        async def generate_scene(self, prompt, schema, repair_context=None):  # type: ignore[no-untyped-def]
            await asyncio.sleep(0.05)
            return await super().generate_scene(prompt, schema, repair_context)

    repository = InMemoryRepository()
    provider = SlowProvider()
    service = GenerationService(
        repository=repository,
        compiler=PromptCompiler(provider, SceneValidator(), max_repairs=0),
        provider_name=provider.name,
        model=provider.model,
        prompt_template_version="test-1",
        generation_timeout_seconds=0.001,
    )
    job = await repository.create_job(
        owner_session_id="session_test_123",
        prompt="cyberpunk alley",
        provider="fake",
        model="fake-scene-model",
        prompt_template_version="test-1",
        idempotency_key=None,
    )
    await service.run_job(
        job_id=job["jobId"],
        owner_session_id="session_test_123",
        prompt="cyberpunk alley",
    )
    completed = await service.get_job(job["jobId"], "session_test_123")
    assert completed is not None
    assert completed["status"] == "failed"
    assert completed["error"]["code"] == "GENERATION_TIMEOUT"


@pytest.mark.asyncio
async def test_api_covers_submit_poll_and_history_flow() -> None:
    service, _, _ = make_service()
    settings = Settings(
        moonshot_api_key="test_key_not_real",
        database_url_override="sqlite+aiosqlite:///:memory:",
        generation_rate_limit_per_minute=10,
    )
    app = create_app(service_override=service, bootstrap=False, settings_override=settings)
    headers = {"X-Session-ID": "session_test_123"}

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/generations",
                headers={**headers, "Idempotency-Key": "request-1"},
                json={"prompt": "A neon ramen alley", "preferences": {"quality": "balanced"}},
            )
            assert response.status_code == 202
            job_id = response.json()["jobId"]

            for _ in range(20):
                polled = await client.get(f"/api/v1/generations/{job_id}", headers=headers)
                if polled.json()["status"] == "succeeded":
                    break
                await asyncio.sleep(0.01)

            payload = polled.json()
            assert payload["status"] == "succeeded"
            assert payload["scene"]["version"]["sceneJson"]["nodes"]

            history = await client.get("/api/v1/scenes", headers=headers)
            assert history.status_code == 200
            assert len(history.json()["items"]) == 1
