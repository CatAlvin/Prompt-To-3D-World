from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from app.config import ROOT_DIR


CATALOG_PATH = ROOT_DIR / "shared" / "style-kits" / "catalog.json"
ASSET_CATALOG_PATH = ROOT_DIR / "shared" / "assets" / "catalog.json"


class StyleKitRegistry:
    def __init__(self) -> None:
        self._catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        self._items = {item["id"]: item for item in self._catalog["items"]}
        self._assets = json.loads(ASSET_CATALOG_PATH.read_text(encoding="utf-8"))

    def get(self, style_kit_id: str) -> dict[str, Any]:
        if style_kit_id not in self._items:
            raise ValueError(f"Unknown Style Kit: {style_kit_id}")
        return deepcopy(self._items[style_kit_id])

    def list_public(self) -> list[dict[str, Any]]:
        return [deepcopy(item) for item in self._catalog["items"]]

    def assets(self) -> list[dict[str, Any]]:
        return deepcopy(self._assets["items"])

    def asset(self, asset_id: str) -> dict[str, Any] | None:
        return next((deepcopy(item) for item in self._assets["items"] if item["id"] == asset_id), None)

