from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from app.config import ROOT_DIR
from app.domain.scene_validator import SceneValidationError, SceneValidator


INTENT_SCHEMA_PATH = ROOT_DIR / "shared" / "scene-intent-v2.schema.json"
SCENE_V1_SCHEMA_PATH = ROOT_DIR / "shared" / "scene.schema.json"
SCENE_V3_SCHEMA_PATH = ROOT_DIR / "shared" / "scene-v3.schema.json"


def _load(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        schema = json.load(handle)
    Draft202012Validator.check_schema(schema)
    return schema


def _details(validator: Draft202012Validator, document: dict[str, Any]) -> list[str]:
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.absolute_path))
    return [SceneValidator._format_error(error) for error in errors[:32]]


class SceneIntentValidator:
    def __init__(self, schema: dict[str, Any] | None = None) -> None:
        self.schema = schema or _load(INTENT_SCHEMA_PATH)
        self.validator = Draft202012Validator(self.schema)

    def validate(self, intent: dict[str, Any]) -> dict[str, Any]:
        if errors := _details(self.validator, intent):
            raise SceneValidationError(errors)
        entity_ids = [entity["id"] for entity in intent["entities"]]
        if len(entity_ids) != len(set(entity_ids)):
            raise SceneValidationError(["Scene Intent entity ids must be unique"])
        known_ids = set(entity_ids)
        references = set(intent["constraints"]["requiredEntities"])
        references.update(intent["constraints"]["optionalEntities"])
        if unknown := sorted(references - known_ids):
            raise SceneValidationError([f"Constraints reference unknown entities: {', '.join(unknown[:8])}"])
        relation_ids = {
            entity_id
            for relation in intent["relations"]
            for entity_id in (relation["sourceId"], relation["targetId"])
        }
        if unknown := sorted(relation_ids - known_ids):
            raise SceneValidationError([f"Relations reference unknown entities: {', '.join(unknown[:8])}"])
        hero_id = intent["cameraIntent"]["heroEntityId"]
        if hero_id is not None and hero_id not in known_ids:
            raise SceneValidationError([f"Camera hero references unknown entity: {hero_id}"])
        if intent["sceneMode"] in {"orbital", "panorama"} and intent["constraints"]["navigationRequired"]:
            raise SceneValidationError(["Orbital and panorama scenes cannot require ground navigation"])
        return intent


class SceneV3Validator:
    def __init__(self) -> None:
        self.schema = _load(SCENE_V3_SCHEMA_PATH)
        v1_schema = _load(SCENE_V1_SCHEMA_PATH)
        registry = Registry().with_resource(v1_schema["$id"], Resource.from_contents(v1_schema))
        self.validator = Draft202012Validator(self.schema, registry=registry)

    def validate(self, scene: dict[str, Any], intent: dict[str, Any] | None = None) -> dict[str, Any]:
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
        if scene["pipeline"]["sceneMode"] in {"walkable", "interior"}:
            ground = any(
                node["kind"] == "primitive" and node["collision"]["mode"] == "ground"
                for node in scene["nodes"]
            )
            if not ground:
                raise SceneValidationError(["Walkable and interior V3 scenes require a ground collision primitive"])
        shadow_lights = [
            node for node in scene["nodes"] if node["kind"] == "light" and node["light"]["castShadow"]
        ]
        budget = 0 if scene["pipeline"]["quality"] == "draft" else 2
        if len(shadow_lights) > budget:
            raise SceneValidationError([f"Quality profile permits at most {budget} shadow lights"])
        if intent is not None:
            entity_ids = {entity["id"] for entity in intent["entities"]}
            invalid_sources = sorted(
                {
                    provenance["entityId"]
                    for node in scene["nodes"]
                    if (provenance := node["provenance"])["entityId"] is not None
                    and provenance["entityId"] not in entity_ids
                }
            )
            if invalid_sources:
                raise SceneValidationError([f"Nodes reference unknown intent entities: {', '.join(invalid_sources[:8])}"])
        return scene
