from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from app.config import ROOT_DIR
from app.domain.scene_validator import SceneValidationError, SceneValidator


PLAN_SCHEMA_PATH = ROOT_DIR / "shared" / "scene-plan.schema.json"
SCENE_V1_SCHEMA_PATH = ROOT_DIR / "shared" / "scene.schema.json"
SCENE_V2_SCHEMA_PATH = ROOT_DIR / "shared" / "scene-v2.schema.json"


def _load(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        schema = json.load(handle)
    Draft202012Validator.check_schema(schema)
    return schema


def _details(validator: Draft202012Validator, document: dict[str, Any]) -> list[str]:
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.absolute_path))
    return [SceneValidator._format_error(error) for error in errors[:24]]


class ScenePlanValidator:
    def __init__(self, schema: dict[str, Any] | None = None) -> None:
        self.schema = schema or _load(PLAN_SCHEMA_PATH)
        self.validator = Draft202012Validator(self.schema)

    def validate(self, plan: dict[str, Any]) -> dict[str, Any]:
        if errors := _details(self.validator, plan):
            raise SceneValidationError(errors)
        zone_ids = [zone["id"] for zone in plan["zones"]]
        if len(zone_ids) != len(set(zone_ids)):
            raise SceneValidationError(["Scene Plan zone ids must be unique"])
        return plan


class SceneV2Validator:
    def __init__(self) -> None:
        self.schema = _load(SCENE_V2_SCHEMA_PATH)
        v1_schema = _load(SCENE_V1_SCHEMA_PATH)
        registry = Registry().with_resource(v1_schema["$id"], Resource.from_contents(v1_schema))
        self.validator = Draft202012Validator(self.schema, registry=registry)

    def validate(self, scene: dict[str, Any]) -> dict[str, Any]:
        if errors := _details(self.validator, scene):
            raise SceneValidationError(errors)
        ids = [node["id"] for node in scene["nodes"]]
        if len(ids) != len(set(ids)):
            raise SceneValidationError(["Scene node ids must be unique"])
        groups = {node["id"] for node in scene["nodes"] if node["kind"] == "group"}
        invalid_parents = [
            node["id"]
            for node in scene["nodes"]
            if node.get("parentId") is not None and node["parentId"] not in groups
        ]
        if invalid_parents:
            raise SceneValidationError([f"Nodes reference invalid groups: {', '.join(invalid_parents[:8])}"])
        ground = any(
            node["kind"] == "primitive" and node["collision"]["mode"] == "ground"
            for node in scene["nodes"]
        )
        if not ground:
            raise SceneValidationError(["A V2 scene requires a ground collision primitive"])
        shadow_lights = [
            node for node in scene["nodes"] if node["kind"] == "light" and node["light"]["castShadow"]
        ]
        budget = 0 if scene["pipeline"]["quality"] == "draft" else 2
        if len(shadow_lights) > budget:
            raise SceneValidationError([f"Quality profile permits at most {budget} shadow lights"])
        return scene

