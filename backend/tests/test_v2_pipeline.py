from __future__ import annotations

import asyncio
import json

import pytest

from app.compilers.procedural import ProceduralSceneCompiler, build_local_plan, migrate_v1_to_v2, request_fingerprint
from app.config import ROOT_DIR
from app.domain.scene_validator import SceneValidationError
from app.domain.v2_validator import ScenePlanValidator, SceneV2Validator
from app.providers.base import ProviderResult
from app.services.v2.plan_compiler import ScenePlanCompiler


PREFERENCES = {
    "styleKit": "auto",
    "time": "auto",
    "weather": "auto",
    "density": 0.68,
    "quality": "balanced",
    "scale": "compact",
    "seed": None,
}


def test_v2_benchmark_has_fifty_prompts_across_five_categories() -> None:
    benchmark = json.loads((ROOT_DIR / "shared" / "benchmarks" / "v2-prompts.json").read_text(encoding="utf-8"))
    assert len(benchmark["items"]) == 50
    assert {item["category"] for item in benchmark["items"]} == {
        "urban_alley", "misty_nature", "cozy_room", "desert_outpost", "historic_town"
    }


def test_local_plan_and_procedural_compiler_are_deterministic_for_benchmark() -> None:
    benchmark = json.loads((ROOT_DIR / "shared" / "benchmarks" / "v2-prompts.json").read_text(encoding="utf-8"))
    compiler = ProceduralSceneCompiler()
    for item in benchmark["items"]:
        plan = build_local_plan(item["prompt"], PREFERENCES)
        assert plan["archetype"] == item["category"]
        fingerprint = request_fingerprint(item["prompt"], PREFERENCES)
        first = compiler.compile(plan, fingerprint=fingerprint, version_kind="final", quality="balanced")
        second = compiler.compile(plan, fingerprint=fingerprint, version_kind="final", quality="balanced")
        assert first == second
        assert first["schemaVersion"] == "2.0.0"
        assert any(node["kind"] in {"procedural", "instances", "asset", "prefab"} for node in first["nodes"])


def test_v1_migrator_creates_valid_v2_without_mutating_source() -> None:
    source = json.loads((ROOT_DIR / "shared" / "examples" / "cyberpunk-alley.json").read_text(encoding="utf-8"))
    migrated = migrate_v1_to_v2(source)
    assert source["schemaVersion"] == "1.0.0"
    assert migrated["schemaVersion"] == "2.0.0"
    SceneV2Validator().validate(migrated)


def test_scene_plan_rejects_unregistered_archetype() -> None:
    plan = build_local_plan("A rainy alley", PREFERENCES)
    plan["archetype"] = "invented_world"
    with pytest.raises(SceneValidationError):
        ScenePlanValidator().validate(plan)


def test_lunar_example_uses_station_archetype_and_contains_no_forest_content() -> None:
    prompt = "A quiet lunar research station above a blue crater at sunrise."
    plan = build_local_plan(prompt, PREFERENCES)
    assert plan["archetype"] == "lunar_station"
    assert plan["styleKit"] == "lunar_research_v1"
    assert plan["time"] == "sunrise"
    assert plan["weather"] == "clear"
    assert {"research_habitat", "blue_crater", "sunrise_horizon"}.issubset(plan["mustInclude"])
    assert {"trees", "vegetation", "shrine_gate"}.issubset(plan["avoid"])

    scene = ProceduralSceneCompiler().compile(
        plan,
        fingerprint=request_fingerprint(prompt, PREFERENCES),
        version_kind="final",
        quality="balanced",
    )
    categories = {node["semantics"]["category"] for node in scene["nodes"]}
    assert scene["pipeline"]["archetype"] == "lunar_station"
    assert scene["pipeline"]["styleKit"] == "lunar_research_v1"
    assert scene["environment"]["sky"] == "sunrise"
    assert {"research_habitat", "blue_crater", "solar_array", "antenna"}.issubset(categories)
    assert categories.isdisjoint({"tree_trunk", "tree_canopy", "vegetation", "hero_anchor"})
    SceneV2Validator().validate(scene)


def test_lunar_intent_overrides_a_provider_misclassification() -> None:
    class MisclassifyingProvider:
        name = "fake-kimi"
        model = "fake-plan"

        async def generate_plan(self, _prompt, preferences, _schema, _repair_context):
            wrong_plan = build_local_plan(
                "A misty forest shrine with trees and a torii gate.",
                preferences,
            )
            return ProviderResult(
                content=json.dumps(wrong_plan),
                provider=self.name,
                model=self.model,
                finish_reason="stop",
                prompt_tokens=20,
                completion_tokens=40,
            )

    compiled = asyncio.run(
        ScenePlanCompiler(MisclassifyingProvider()).compile(
            "A quiet lunar research station above a blue crater at sunrise.",
            PREFERENCES,
        )
    )
    assert compiled.plan["archetype"] == "lunar_station"
    assert compiled.plan["styleKit"] == "lunar_research_v1"
    assert compiled.plan["time"] == "sunrise"
    assert "shrine_gate" in compiled.plan["avoid"]
