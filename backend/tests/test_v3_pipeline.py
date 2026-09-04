from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import asyncio
import json
import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.compilers.procedural import request_fingerprint
from app.config import ROOT_DIR, Settings
from app.domain.v3_validator import SceneIntentValidator, SceneV3Validator
from app.main import create_app
from app.models import Base
from app.providers.base import ProviderResult
from app.repositories.sqlalchemy import SqlAlchemySceneRepository
from app.services.v3.capability_registry import CapabilityRegistry
from app.services.v3.fidelity import SemanticFidelityEvaluator
from app.services.v3.generation import GenerationV3Service
from app.services.v3.intent_compiler import SceneIntentCompiler, build_local_intent, summarize_intent
from app.services.v3.layout_solver import LayoutSolver
from app.services.v3.recipe_compiler import VisualRecipeCompiler


PREFERENCES = {
    "styleKit": "auto",
    "time": "auto",
    "weather": "auto",
    "density": 0.68,
    "quality": "balanced",
    "scale": "compact",
    "seed": None,
}

FLOATING_WEATHER_PROMPT = (
    "暴风雨刚刚停歇的蓝调时刻，一座面积有限的黑色玄武岩浮岛悬在厚重云海之上。"
    "浮岛中央偏左是一座单层模块化气象研究站，建筑有暖黄色玻璃窗，室内灯光清晰可见；"
    "右侧矗立着白色雷达天线。研究站前方是湿润金属栈道，岛边有岩石、水面与云层。"
    "不要出现城市、树木、月球地貌、宇宙飞船、人物、车辆、商铺或赛博朋克霓虹招牌。"
)


def compile_local(prompt: str, quality: str = "balanced") -> tuple[dict, dict, list[dict]]:
    preferences = {**PREFERENCES, "quality": quality}
    intent = build_local_intent(prompt, preferences)
    registry = CapabilityRegistry()
    resolutions = registry.resolve_all(intent)
    layout = LayoutSolver().solve(intent)
    scene = VisualRecipeCompiler().compile(
        intent,
        resolutions,
        layout,
        fingerprint=request_fingerprint(prompt, preferences),
        version_kind="final",
        quality=quality,
    )
    result = SemanticFidelityEvaluator().evaluate(intent, scene, resolutions, layout)
    SceneV3Validator().validate(scene, intent)
    assert result.passed
    return intent, scene, resolutions


def test_deep_space_intent_stays_open_and_does_not_use_a_lunar_template() -> None:
    prompt = "在浩瀚宇宙中，前方是一颗耀眼恒星，旁边是一颗脉冲星，远处有一个黑洞，远处群星点点"
    intent, scene, resolutions = compile_local(prompt)
    concepts = {entity["concept"] for entity in intent["entities"]}
    categories = {node["semantics"]["category"] for node in scene["nodes"]}
    assert intent["sceneMode"] == "orbital"
    assert {"star", "pulsar", "black_hole", "starfield"}.issubset(concepts)
    assert {"star", "pulsar", "black_hole", "starfield"}.issubset(categories)
    assert categories.isdisjoint({"research_station", "crater", "street", "tree", "shop"})
    assert not any(
        node["kind"] == "primitive" and node["collision"]["mode"] == "ground"
        for node in scene["nodes"]
    )
    assert scene["camera"]["mode"] == "orbit"
    assert scene["semanticReport"]["requiredCoverage"] == 1
    assert any(item["concept"] == "black_hole" and item["support"] == "abstract" for item in resolutions)


def test_complex_floating_prompt_respects_negation_modifiers_and_mode() -> None:
    intent = build_local_intent(FLOATING_WEATHER_PROMPT, PREFERENCES)
    concepts = {entity["concept"] for entity in intent["entities"]}
    forbidden = set(intent["constraints"]["forbiddenConcepts"])

    assert intent["sceneMode"] == "flythrough"
    assert intent["environment"]["time"] == "sunset"
    assert intent["styleIntent"]["styleKit"] == "misty_nature_v1"
    assert {"research_station", "antenna", "walkway", "rock", "water", "floating_island", "cloud"}.issubset(concepts)
    assert concepts.isdisjoint({"moon", "tree", "neon_sign", "room"})
    assert {"moon", "tree", "neon_sign", "city", "spacecraft", "person", "vehicle", "shop"}.issubset(forbidden)
    resolutions = CapabilityRegistry().resolve_all(intent)
    assert all(item["support"] == "exact" for item in resolutions)
    relation_types = {relation["type"] for relation in intent["relations"]}
    assert {"above", "right_of", "in_front_of", "around"}.issubset(relation_types)

    layout = LayoutSolver().solve(intent)
    entity_ids = {entity["concept"]: entity["id"] for entity in intent["entities"]}
    station = layout["entities"][entity_ids["research_station"]]["position"]
    antenna = layout["entities"][entity_ids["antenna"]]["position"]
    walkway = layout["entities"][entity_ids["walkway"]]["position"]
    assert abs(station[1] - antenna[1]) <= 0.001
    assert abs(station[1] - walkway[1]) <= 0.001
    assert abs(station[2] - antenna[2]) <= 0.001
    assert 0 < walkway[2] - station[2] <= 3


def test_compound_floating_weather_concepts_use_specific_capabilities() -> None:
    registry = CapabilityRegistry()
    cases = {
        "floating_black_basalt_island": "cap_floating_island_v1",
        "wet_metal_walkway": "cap_walkway_v1",
        "low_orange_warning_lights": "cap_warning_light_v1",
        "thin_waterfall_into_clouds": "cap_waterfall_v1",
        "faint_residual_lightning": "cap_lightning_v1",
        "light_reflections_on_wet_surface": "cap_water_v1",
        "cyan_equipment_status_lights": "cap_status_light_v1",
        "blue_status_leds": "cap_status_light_v1",
        "modular_weather_station": "cap_research_station_v1",
        "sharp_basalt_spires": "cap_rock_v1",
    }
    for concept, expected in cases.items():
        resolution = registry.resolve(
            {
                "id": f"entity_{concept}",
                "concept": concept,
                "category": "environment",
            },
            "flythrough",
        )
        assert resolution["capabilityId"] == expected
        assert resolution["support"] == "exact"


@pytest.mark.asyncio
async def test_intent_compiler_sends_dynamic_canonical_capabilities_to_provider() -> None:
    class CapturingProvider:
        name = "capture"
        model = "capture-model"

        def __init__(self) -> None:
            self.preferences: dict | None = None

        async def generate_intent(
            self,
            prompt: str,
            preferences: dict,
            _schema: dict,
            _repair_context: dict | None = None,
        ) -> ProviderResult:
            self.preferences = preferences
            return ProviderResult(
                content=json.dumps(build_local_intent(prompt, preferences), ensure_ascii=False),
                provider=self.name,
                model=self.model,
                finish_reason="stop",
                prompt_tokens=1,
                completion_tokens=1,
            )

    provider = CapturingProvider()
    await SceneIntentCompiler(provider).compile("A research station with status lights.", PREFERENCES)

    assert provider.preferences is not None
    capabilities = provider.preferences["engineCapabilities"]
    assert "research_station" in capabilities
    assert "status_light" in capabilities
    assert "abstract_marker" not in capabilities


def test_provider_merge_removes_forbidden_entities_and_incompatible_style() -> None:
    provider_intent = build_local_intent(FLOATING_WEATHER_PROMPT, PREFERENCES)
    forbidden_candidates = build_local_intent("A moon with a neon sign.", PREFERENCES)["entities"]
    for entity in forbidden_candidates:
        candidate = deepcopy(entity)
        candidate["id"] = f"provider_{candidate['concept']}"
        provider_intent["entities"].append(candidate)
        provider_intent["constraints"]["requiredEntities"].append(candidate["id"])
    provider_intent["sceneMode"] = "interior"
    provider_intent["constraints"]["navigationRequired"] = True
    provider_intent["styleIntent"]["styleKit"] = "cyberpunk_tokyo_v1"

    merged = SceneIntentCompiler._merge_explicit_entities(
        FLOATING_WEATHER_PROMPT, provider_intent, PREFERENCES
    )
    concepts = {entity["concept"] for entity in merged["entities"]}
    assert concepts.isdisjoint({"moon", "neon_sign", "room", "tree"})
    assert merged["sceneMode"] == "flythrough"
    assert merged["styleIntent"]["styleKit"] == "misty_nature_v1"
    assert not {
        "provider_moon",
        "provider_neon_sign",
    }.intersection(merged["constraints"]["requiredEntities"])


def test_layout_solver_preserves_multiple_relations_on_the_same_entities() -> None:
    entities = [
        {"id": "island", "role": "structural", "attributes": {"size": None}},
        {"id": "station", "role": "hero", "attributes": {"size": None}},
        {"id": "antenna", "role": "supporting", "attributes": {"size": None}},
        {"id": "cloud", "role": "background", "attributes": {"size": None}},
        {"id": "lightning", "role": "background", "attributes": {"size": None}},
        {"id": "sky", "role": "background", "attributes": {"size": None}},
    ]
    relations = [
        {"sourceId": "island", "type": "above", "targetId": "cloud", "strength": 1.0},
        {"sourceId": "station", "type": "left_of", "targetId": "antenna", "strength": 0.9},
        {"sourceId": "lightning", "type": "far_from", "targetId": "station", "strength": 0.9},
        {"sourceId": "antenna", "type": "facing", "targetId": "sky", "strength": 0.8},
        {"sourceId": "station", "type": "above", "targetId": "island", "strength": 0.7},
        {"sourceId": "antenna", "type": "above", "targetId": "island", "strength": 0.7},
        {"sourceId": "lightning", "type": "inside", "targetId": "cloud", "strength": 0.55},
    ]
    layout = LayoutSolver().solve(
        {
            "sceneMode": "diorama",
            "entities": entities,
            "relations": relations,
            "cameraIntent": {
                "heroEntityId": "station",
                "framing": "medium",
            },
        }
    )
    assert all(relation["satisfied"] for relation in layout["relations"])


def test_fidelity_failure_message_reports_the_actual_failed_metric() -> None:
    message = GenerationV3Service._fidelity_failure_message(
        {
            "requiredCoverage": 1.0,
            "relationSatisfaction": 0.7272,
            "forbiddenViolations": 0,
            "unrelatedRatio": 0.0,
            "heroVisible": True,
        }
    )
    assert "空间关系满足率 73%" in message
    assert "关键内容覆盖率" not in message


def test_v3_benchmark_contains_one_hundred_prompts_across_ten_modesafe_categories() -> None:
    import json

    benchmark = json.loads(
        (ROOT_DIR / "shared" / "benchmarks" / "v3-prompts.json").read_text(encoding="utf-8")
    )
    assert len(benchmark["categories"]) == 10
    assert sum(len(category["prompts"]) for category in benchmark["categories"]) == 100
    validator = SceneIntentValidator()
    for category in benchmark["categories"]:
        assert len(category["prompts"]) == 10
        for prompt in category["prompts"]:
            intent = build_local_intent(prompt, PREFERENCES)
            assert intent["sceneMode"] == category["expectedMode"]
            validator.validate(intent)


def test_lunar_station_contains_only_requested_semantic_entities() -> None:
    prompt = "A quiet lunar research station above a blue crater at sunrise."
    intent, scene, _ = compile_local(prompt)
    concepts = {entity["concept"] for entity in intent["entities"]}
    categories = {node["semantics"]["category"] for node in scene["nodes"]}
    assert intent["sceneMode"] == "orbital"
    assert {"research_station", "crater", "moon"}.issubset(concepts)
    assert {"research_station", "crater", "moon"}.issubset(categories)
    assert categories.isdisjoint({"tree", "forest", "shrine_gate", "ramen_shop"})
    assert scene["environment"]["sky"] == "custom"
    assert scene["semanticReport"]["status"] == "passed"


def test_unknown_concept_uses_disclosed_abstract_fallback() -> None:
    intent = build_local_intent("A bioluminescent biomechanical whale sanctuary.", PREFERENCES)
    resolutions = CapabilityRegistry().resolve_all(intent)
    assert len(resolutions) == 1
    assert resolutions[0]["capabilityId"] == "cap_abstract_marker_v1"
    assert resolutions[0]["support"] == "abstract"
    assert resolutions[0]["message"]
    preview = summarize_intent(intent, resolutions)
    assert preview["entities"][0]["support"] == "abstract"


def test_separator_variants_resolve_exactly_and_do_not_duplicate_entities() -> None:
    prompt = "A bright star beside a pulsar, a distant black hole, and a starfield."
    provider_intent = build_local_intent(prompt, PREFERENCES)
    provider_starfield = next(
        entity for entity in provider_intent["entities"] if entity["concept"] == "starfield"
    )
    provider_starfield["concept"] = "star_field"

    registry = CapabilityRegistry()
    assert registry.resolve(provider_starfield, "orbital")["capabilityId"] == "cap_starfield_v1"

    merged = SceneIntentCompiler._merge_explicit_entities(
        prompt, provider_intent, PREFERENCES
    )
    capability_ids = [
        registry.resolve(entity, merged["sceneMode"])["capabilityId"]
        for entity in merged["entities"]
    ]
    assert capability_ids.count("cap_starfield_v1") == 1


def test_quality_changes_visual_budget_without_changing_entity_coverage() -> None:
    prompt = "A misty forest path with trees and rocks."
    fast_intent, fast_scene, _ = compile_local(prompt, "draft")
    quality_intent, quality_scene, _ = compile_local(prompt, "quality")
    assert {entity["concept"] for entity in fast_intent["entities"]} == {
        entity["concept"] for entity in quality_intent["entities"]
    }
    assert set(fast_scene["semanticReport"]["coveredEntityIds"]) == set(
        quality_scene["semanticReport"]["coveredEntityIds"]
    )
    assert len(quality_scene["nodes"]) >= len(fast_scene["nodes"])


def test_intent_validator_rejects_unknown_relation_references() -> None:
    intent = build_local_intent("A star beside a pulsar.", PREFERENCES)
    broken = deepcopy(intent)
    broken["relations"][0]["targetId"] = "entity_missing"
    try:
        SceneIntentValidator().validate(broken)
    except Exception as exc:
        assert "unknown" in str(exc).lower()
    else:
        raise AssertionError("Unknown relation reference was accepted")


@pytest.mark.asyncio
async def test_v3_api_persists_draft_and_fidelity_checked_final() -> None:
    database_path = Path(__file__).resolve().parent / ".v3-api-test.db"
    database_path.unlink(missing_ok=True)
    database_url = f"sqlite+aiosqlite:///{database_path.as_posix()}"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    repository = SqlAlchemySceneRepository(async_sessionmaker(engine, expire_on_commit=False))

    class LocalProvider:
        name = "local-test"
        model = "local-intent"

    service = GenerationV3Service(
        repository=repository,
        intent_compiler=SceneIntentCompiler(LocalProvider()),
        scene_compiler=VisualRecipeCompiler(),
        provider_name="local-test",
        model="local-intent",
        auto_start=True,
    )

    class RootService:
        def __init__(self) -> None:
            self.repository = repository

        async def shutdown(self) -> None:
            return None

    settings = Settings(
        moonshot_api_key="test_key_not_real",
        database_url_override=database_url,
        generation_rate_limit_per_minute=10,
    )
    app = create_app(
        service_override=RootService(),
        v3_service_override=service,
        bootstrap=False,
        settings_override=settings,
    )
    headers = {"X-Session-ID": "session_v3_test_123"}
    prompt = "A bright star beside a pulsar, with a distant black hole and a field of stars."
    try:
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                created = await client.post(
                    "/api/v3/generations",
                    headers={**headers, "Idempotency-Key": "v3-request-1"},
                    json={"prompt": prompt, "preferences": PREFERENCES},
                )
                assert created.status_code == 202
                assert created.json()["intentPreview"]["sceneMode"] == "orbital"
                job_id = created.json()["jobId"]
                payload = created.json()
                for _ in range(80):
                    response = await client.get(f"/api/v3/generations/{job_id}", headers=headers)
                    payload = response.json()
                    if payload["status"] in {"succeeded", "partial", "failed"}:
                        break
                    await asyncio.sleep(0.01)

                assert payload["status"] == "succeeded"
                assert payload["draft"]["version"]["versionKind"] == "draft"
                assert payload["scene"]["version"]["sceneJson"]["schemaVersion"] == "3.0.0"
                assert payload["coverage"]["status"] == "passed"
                assert payload["coverage"]["requiredCoverage"] == 1
                categories = {
                    node["semantics"]["category"]
                    for node in payload["scene"]["version"]["sceneJson"]["nodes"]
                }
                assert {"star", "pulsar", "black_hole", "starfield"}.issubset(categories)
                assert "research_station" not in categories
                assert any(item["concept"] == "black_hole" for item in payload["unsupportedEntities"])
    finally:
        await service.shutdown()
        await engine.dispose()
        database_path.unlink(missing_ok=True)
