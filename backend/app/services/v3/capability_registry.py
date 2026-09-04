from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.config import ROOT_DIR


CATALOG_PATH = ROOT_DIR / "shared" / "capabilities" / "catalog-v3.json"


def normalize_concept(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9\u3400-\u9fff]+", "_", value.strip().lower())
    return normalized.strip("_")


class CapabilityRegistry:
    def __init__(self, path: Path = CATALOG_PATH) -> None:
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.version: str = payload["version"]
        self._items: dict[str, dict[str, Any]] = {}
        self._aliases: dict[str, str] = {}
        self._compact_aliases: dict[str, str] = {}
        for item in payload["capabilities"]:
            self._items[item["id"]] = item
            for alias in [item["concept"], *item.get("aliases", [])]:
                normalized = normalize_concept(alias)
                if normalized:
                    self._aliases[normalized] = item["id"]
                    # LLMs commonly vary only separator style (for example
                    # starfield / star_field / star-field). Treat those forms
                    # as the same exact concept before fuzzy matching.
                    self._compact_aliases[normalized.replace("_", "")] = item["id"]

    def list_public(self) -> list[dict[str, Any]]:
        return [
            {
                "id": item["id"],
                "concept": item["concept"],
                "category": item["category"],
                "sceneModes": item["sceneModes"],
                "support": item["support"],
                "label": item["label"],
                "version": self.version,
            }
            for item in self._items.values()
        ]

    def resolve(self, entity: dict[str, Any], scene_mode: str) -> dict[str, Any]:
        concept = normalize_concept(entity["concept"])
        capability_id = self._aliases.get(concept)
        if capability_id is None:
            capability_id = self._compact_aliases.get(concept.replace("_", ""))
        if capability_id is None:
            candidates = [
                (len(alias), target)
                for alias, target in self._aliases.items()
                if len(alias) >= 3 and (alias in concept or concept in alias)
            ]
            if candidates:
                capability_id = max(candidates)[1]
        if capability_id is None:
            capability_id = "cap_abstract_marker_v1"
            support = "abstract"
            message = f"“{entity['concept']}”将使用可识别的抽象轮廓表现。"
            confidence = 0.42
        else:
            support = self._items[capability_id]["support"]
            message = None
            confidence = 1.0 if support == "exact" else 0.78

        capability = deepcopy(self._items[capability_id])
        if scene_mode not in capability["sceneModes"]:
            abstract = deepcopy(self._items["cap_abstract_marker_v1"])
            return {
                "entityId": entity["id"],
                "concept": entity["concept"],
                "category": entity["category"],
                "capabilityId": abstract["id"],
                "capabilityVersion": self.version,
                "recipe": abstract["recipe"],
                "support": "abstract",
                "confidence": 0.48,
                "label": entity.get("attributes", {}).get("label") or entity["concept"],
                "message": f"“{entity['concept']}”在当前场景模式中将使用抽象表现。",
            }
        if support == "abstract" and message is None:
            message = f"“{capability['label']}”将使用引擎内置的抽象视觉效果表现。"
        return {
            "entityId": entity["id"],
            "concept": capability["concept"],
            "category": capability["category"],
            "capabilityId": capability["id"],
            "capabilityVersion": self.version,
            "recipe": capability["recipe"],
            "support": support,
            "confidence": confidence,
            "label": capability["label"],
            "message": message,
        }

    def resolve_all(self, intent: dict[str, Any]) -> list[dict[str, Any]]:
        return [self.resolve(entity, intent["sceneMode"]) for entity in intent["entities"]]
