from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError

from app.config import ROOT_DIR


SCHEMA_PATH = ROOT_DIR / "shared" / "scene.schema.json"


class SceneValidationError(ValueError):
    def __init__(self, details: list[str]) -> None:
        self.details = details[:24]
        super().__init__("; ".join(self.details))


def load_scene_schema(path: Path = SCHEMA_PATH) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        schema = json.load(handle)
    Draft202012Validator.check_schema(schema)
    return schema


class SceneValidator:
    def __init__(self, schema: dict[str, Any] | None = None) -> None:
        self.schema = schema or load_scene_schema()
        self.validator = Draft202012Validator(self.schema)

    @staticmethod
    def _leaf_error(error: JsonSchemaValidationError) -> JsonSchemaValidationError:
        if not error.context:
            return error
        leaves: list[JsonSchemaValidationError] = []
        stack = list(error.context)
        while stack:
            child = stack.pop()
            if child.context:
                stack.extend(child.context)
            else:
                leaves.append(child)
        if not leaves:
            return error
        return max(leaves, key=lambda item: len(item.absolute_path))

    @classmethod
    def _format_error(cls, error: JsonSchemaValidationError) -> str:
        leaf = cls._leaf_error(error)
        path = ".".join(str(part) for part in leaf.absolute_path) or "$"
        return f"{path}: {leaf.message}"

    def validate_structure(self, scene: dict[str, Any]) -> None:
        errors = sorted(self.validator.iter_errors(scene), key=lambda error: list(error.absolute_path))
        if errors:
            raise SceneValidationError([self._format_error(error) for error in errors])

    def validate_semantics(self, scene: dict[str, Any]) -> None:
        details: list[str] = []
        nodes = scene["nodes"]
        ids = [node["id"] for node in nodes]
        id_set = set(ids)

        if len(ids) != len(id_set):
            duplicates = sorted({node_id for node_id in ids if ids.count(node_id) > 1})
            details.append(f"Node ids must be unique: {', '.join(duplicates[:8])}")

        nodes_by_id = {node["id"]: node for node in nodes}
        parent_by_id: dict[str, str | None] = {}
        for node in nodes:
            node_id = node["id"]
            parent_id = node.get("parentId")
            parent_by_id[node_id] = parent_id
            if parent_id is None:
                continue
            if parent_id not in id_set:
                details.append(f"Node {node_id} references missing parent {parent_id}")
            elif nodes_by_id[parent_id]["kind"] != "group":
                details.append(f"Node {node_id} parent {parent_id} is not a group")
            elif parent_id == node_id:
                details.append(f"Node {node_id} cannot parent itself")

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visited:
                return
            if node_id in visiting:
                details.append(f"Parent cycle detected at {node_id}")
                return
            visiting.add(node_id)
            parent_id = parent_by_id.get(node_id)
            if parent_id in parent_by_id:
                visit(parent_id)
            visiting.discard(node_id)
            visited.add(node_id)

        for node_id in ids:
            visit(node_id)

        lights = [node for node in nodes if node["kind"] == "light"]
        shadow_lights = [node for node in lights if node["light"]["castShadow"]]
        if len(lights) > 12:
            details.append("A scene may contain at most 12 explicit lights")
        if len(shadow_lights) > 2:
            details.append("A scene may contain at most 2 shadow-casting lights")

        has_ground = any(
            node["kind"] == "primitive" and node["collision"]["mode"] == "ground"
            for node in nodes
        )
        if not has_ground:
            details.append("A first-person scene requires at least one ground collision node")

        fog = scene["environment"]["fog"]
        if fog["type"] == "linear" and fog["near"] >= fog["far"]:
            details.append("Linear fog near must be smaller than far")

        camera = scene["camera"]
        if camera["near"] >= camera["far"]:
            details.append("Camera near must be smaller than far")

        if details:
            raise SceneValidationError(details)

    @staticmethod
    def detect_prompt_language(prompt: str) -> str:
        has_cjk = bool(re.search(r"[\u3400-\u9fff]", prompt))
        has_latin = bool(re.search(r"[A-Za-z]", prompt))
        if has_cjk and has_latin:
            return "mixed"
        if has_cjk:
            return "zh"
        if has_latin:
            return "en"
        return "unknown"

    def normalize(self, scene: dict[str, Any], prompt: str) -> dict[str, Any]:
        normalized = copy.deepcopy(scene)
        normalized["schemaVersion"] = "1.0.0"
        normalized["units"] = "meters"
        normalized["metadata"] = {
            "generator": "prompt-compiler",
            "promptLanguage": self.detect_prompt_language(prompt),
        }
        normalized["extensions"] = {}
        return normalized

    def validate_and_normalize(self, scene: dict[str, Any], prompt: str) -> dict[str, Any]:
        self.validate_structure(scene)
        self.validate_semantics(scene)
        normalized = self.normalize(scene, prompt)
        self.validate_structure(normalized)
        self.validate_semantics(normalized)
        return normalized

