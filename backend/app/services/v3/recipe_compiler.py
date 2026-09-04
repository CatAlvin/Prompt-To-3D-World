from __future__ import annotations

import math
import random
import re
from typing import Any

from app.compilers.style_kits import StyleKitRegistry


COMPILER_VERSION = "visual-recipes-3.0.0"

NAMED_COLORS = {
    "blue": "#3aa7ff",
    "red": "#ff5a6f",
    "green": "#67d59a",
    "cyan": "#45e6ff",
    "purple": "#a579ff",
    "orange": "#ff9c52",
    "yellow": "#ffe28a",
    "white": "#f5f7ff",
    "black": "#030407",
    "蓝": "#3aa7ff",
    "红": "#ff5a6f",
    "绿": "#67d59a",
}


def _color(value: str | None, fallback: str) -> str:
    if not value:
        return fallback
    if re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        return value
    return NAMED_COLORS.get(value.lower(), fallback)


def _transform(position: list[float], scale: list[float], rotation: list[float] | None = None) -> dict[str, Any]:
    return {"position": position, "rotation": rotation or [0, 0, 0], "scale": scale}


def _material(
    color: str,
    *,
    emissive: str | None = None,
    intensity: float = 0,
    roughness: float = 0.72,
    metalness: float = 0.04,
    opacity: float = 1,
) -> dict[str, Any]:
    return {
        "type": "standard",
        "color": color,
        "roughness": roughness,
        "metalness": metalness,
        "opacity": opacity,
        "transparent": opacity < 1,
        "emissive": emissive,
        "emissiveIntensity": intensity,
    }


def _semantics(category: str, *tags: str) -> dict[str, Any]:
    return {"category": category[:48], "tags": list(dict.fromkeys(tags))[:8]}


def _provenance(
    entity_id: str | None,
    capability_id: str,
    reason: str,
    confidence: float,
    *,
    origin: str = "prompt",
    removable: bool = True,
) -> dict[str, Any]:
    return {
        "entityId": entity_id,
        "origin": origin,
        "capabilityId": capability_id[:64],
        "reason": reason[:160],
        "confidence": max(0, min(1, confidence)),
        "userRemovable": removable,
    }


def _primitive(
    node_id: str,
    subtype: str,
    position: list[float],
    scale: list[float],
    material: dict[str, Any],
    category: str,
    provenance: dict[str, Any],
    *,
    collision: str = "none",
    rotation: list[float] | None = None,
    tags: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "id": node_id,
        "kind": "primitive",
        "subtype": subtype,
        "parentId": None,
        "transform": _transform(position, scale, rotation),
        "material": material,
        "semantics": _semantics(category, *tags),
        "collision": {"mode": collision},
        "provenance": provenance,
    }


def _text(
    node_id: str,
    value: str,
    position: list[float],
    scale: list[float],
    color: str,
    category: str,
    provenance: dict[str, Any],
    *,
    rotation: list[float] | None = None,
) -> dict[str, Any]:
    return {
        "id": node_id,
        "kind": "text",
        "subtype": "label",
        "parentId": None,
        "transform": _transform(position, scale, rotation),
        "text": {"value": value[:40], "fontSize": 0.6, "align": "center"},
        "material": _material(color, emissive=color, intensity=4.5, roughness=0.25),
        "semantics": _semantics(category, "readable"),
        "provenance": provenance,
    }


def _light(
    node_id: str,
    subtype: str,
    position: list[float],
    color: str,
    intensity: float,
    provenance: dict[str, Any],
    *,
    cast_shadow: bool = False,
    light_range: float = 24,
) -> dict[str, Any]:
    return {
        "id": node_id,
        "kind": "light",
        "subtype": subtype,
        "parentId": None,
        "transform": _transform(position, [1, 1, 1]),
        "light": {
            "color": color,
            "intensity": intensity,
            "range": light_range,
            "decay": 2,
            "castShadow": cast_shadow,
        },
        "semantics": _semantics("lighting", "rig"),
        "provenance": provenance,
    }


def _effect(
    node_id: str,
    subtype: str,
    position: list[float],
    scale: list[float],
    category: str,
    provenance: dict[str, Any],
    *,
    count: int,
    color: str,
    secondary: str,
    size: float,
    intensity: float,
    radius: float,
    spread: float,
    rotation_speed: float = 0,
) -> dict[str, Any]:
    return {
        "id": node_id,
        "kind": "effect",
        "subtype": subtype,
        "parentId": None,
        "transform": _transform(position, scale),
        "parameters": {
            "count": count,
            "color": color,
            "secondaryColor": secondary,
            "size": size,
            "intensity": intensity,
            "radius": radius,
            "spread": spread,
            "rotationSpeed": rotation_speed,
        },
        "semantics": _semantics(category, "engine_effect", subtype),
        "provenance": provenance,
    }


class VisualRecipeCompiler:
    def __init__(self, style_registry: StyleKitRegistry | None = None) -> None:
        self.styles = style_registry or StyleKitRegistry()

    def compile(
        self,
        intent: dict[str, Any],
        resolutions: list[dict[str, Any]],
        layout: dict[str, Any],
        *,
        fingerprint: str,
        version_kind: str,
        quality: str,
    ) -> dict[str, Any]:
        style_id = intent["styleIntent"]["styleKit"]
        if style_id == "auto":
            style_id = "lunar_research_v1" if intent["sceneMode"] in {"orbital", "panorama"} else "misty_nature_v1"
        style = self.styles.get(style_id)
        palette = style["palette"]
        rng = random.Random(intent["seed"])
        entity_by_id = {entity["id"]: entity for entity in intent["entities"]}
        nodes: list[dict[str, Any]] = []
        for resolution in resolutions:
            entity = entity_by_id[resolution["entityId"]]
            slot = layout["entities"][entity["id"]]
            nodes.extend(
                self._compile_entity(
                    entity,
                    resolution,
                    slot,
                    palette,
                    rng,
                    quality,
                )
            )

        if intent["sceneMode"] in {"walkable", "interior"} and not any(
            node["kind"] == "primitive" and node["collision"]["mode"] == "ground"
            for node in nodes
        ):
            provenance = _provenance(
                None,
                "structural_ground_v1",
                "为当前可行走模式提供安全地面。",
                1,
                origin="structural",
                removable=False,
            )
            nodes.insert(
                0,
                _primitive(
                    "structural_ground",
                    "plane",
                    [0, 0, -10],
                    [26, 64, 1],
                    _material(palette["ground"], roughness=0.92),
                    "ground",
                    provenance,
                    collision="ground",
                    rotation=[-math.pi / 2, 0, 0],
                    tags=("navigation",),
                ),
            )

        lighting_provenance = _provenance(
            None,
            "lighting_rig_v3",
            "提供全场景可读性，不引入新的语义物体。",
            1,
            origin="structural",
            removable=False,
        )
        if intent["sceneMode"] in {"orbital", "panorama"}:
            nodes.append(
                _light(
                    "structural_key_light",
                    "directional",
                    [18, 30, 18],
                    palette["warm"],
                    1.8 if quality != "draft" else 1.1,
                    lighting_provenance,
                )
            )
        else:
            nodes.append(
                _light(
                    "structural_key_light",
                    "directional",
                    [8, 16, 10],
                    palette["warm"],
                    2.2 if quality != "draft" else 1.3,
                    lighting_provenance,
                    cast_shadow=quality != "draft",
                    light_range=60,
                )
            )

        time = intent["environment"]["time"]
        weather = intent["environment"]["weather"]
        if weather == "auto":
            weather = "rain" if style_id == "cyberpunk_tokyo_v1" else "clear" if intent["sceneMode"] in {"orbital", "panorama"} else "mist"
        if intent["sceneMode"] in {"orbital", "panorama"}:
            sky = "custom"
            background = "#02030a"
            fog_type = "none"
            fog_density = 0
            fog_near = 80
            fog_far = 1000
        elif intent["sceneMode"] == "interior":
            sky = "indoor"
            background = palette["background"]
            fog_type = "linear"
            fog_density = 0
            fog_near = 20
            fog_far = 80
        else:
            sky = time if time in {"day", "sunrise", "sunset", "night"} else ("night" if style_id == "cyberpunk_tokyo_v1" else "overcast")
            background = palette["background"]
            fog_type = "linear" if quality == "draft" else "exponential"
            fog_density = 0 if quality == "draft" else 0.028 if weather == "mist" else 0.012
            fog_near = 12
            fog_far = 120

        capability_versions = {
            resolution["capabilityId"]: resolution["capabilityVersion"]
            for resolution in resolutions
        }
        return {
            "schemaVersion": "3.0.0",
            "id": f"world_{fingerprint[:16]}",
            "title": intent["title"],
            "seed": intent["seed"],
            "units": "meters",
            "environment": {
                "sky": sky,
                "background": background,
                "fog": {
                    "type": fog_type,
                    "color": palette["fog"],
                    "density": fog_density,
                    "near": fog_near,
                    "far": fog_far,
                },
                "ambientLight": {
                    "color": palette["accentAlt"],
                    "intensity": 0.3 if intent["sceneMode"] in {"orbital", "panorama"} else 0.78 if quality == "draft" else 1.0,
                },
                "toneMapping": "acesFilmic",
                "exposure": 1.16 if quality == "draft" else 1.3,
                "postprocessing": {
                    "bloom": {
                        "enabled": quality != "draft" and style["quality"][quality]["bloom"],
                        "intensity": 0 if quality == "draft" else 0.78 if intent["sceneMode"] in {"orbital", "panorama"} else 0.52,
                        "threshold": 0.58 if intent["sceneMode"] in {"orbital", "panorama"} else 0.72,
                    }
                },
            },
            "camera": layout["camera"],
            "nodes": nodes,
            "metadata": {"generator": "visual-recipe-compiler", "promptLanguage": "unknown"},
            "pipeline": {
                "versionKind": version_kind,
                "intentVersion": "2.0.0",
                "compilerVersion": COMPILER_VERSION,
                "styleKit": style_id,
                "quality": quality,
                "sceneMode": intent["sceneMode"],
                "requestFingerprint": fingerprint,
                "capabilityVersions": capability_versions,
            },
            "semanticReport": {
                "status": "pending",
                "requiredCoverage": 0,
                "relationSatisfaction": 0,
                "forbiddenViolations": 0,
                "unrelatedRatio": 0,
                "heroVisible": False,
                "coveredEntityIds": [],
                "missingEntityIds": intent["constraints"]["requiredEntities"],
            },
            "extensions": {"weather": weather, "wetness": 0.86 if weather == "rain" else 0.05},
        }

    def _compile_entity(
        self,
        entity: dict[str, Any],
        resolution: dict[str, Any],
        slot: dict[str, Any],
        palette: dict[str, str],
        rng: random.Random,
        quality: str,
    ) -> list[dict[str, Any]]:
        recipe = resolution["recipe"]
        position = slot["position"]
        multiplier = slot["scaleMultiplier"]
        attributes = entity["attributes"]
        base = f"v3_{entity['id']}"[:30]
        provenance = _provenance(
            entity["id"],
            resolution["capabilityId"],
            f"根据“{entity['sourceText']}”表现 {resolution['label']}。",
            resolution["confidence"],
        )
        primary = _color(attributes.get("color"), palette["primary"])
        accent = _color(attributes.get("color"), palette["accent"])
        count = max(1, entity.get("count", 1))

        if recipe == "starfield":
            star_count = 180 if quality == "draft" else 620 if quality == "balanced" else 1000
            return [_effect(base, "starfield", position, [1, 1, 1], "starfield", provenance, count=star_count, color="#f5f7ff", secondary="#78b7ff", size=0.26, intensity=1.7, radius=120, spread=260)]
        if recipe == "star":
            radius = 4.4 * multiplier
            return [_effect(base, "star", position, [1, 1, 1], "star", provenance, count=1, color="#fff4c7", secondary="#ff9b45", size=radius, intensity=attributes.get("brightness") or 7, radius=radius, spread=24)]
        if recipe == "pulsar":
            radius = 1.7 * multiplier
            return [_effect(base, "pulsar", position, [1, 1, 1], "pulsar", provenance, count=1, color="#e9fbff", secondary="#45bfff", size=radius, intensity=8, radius=radius, spread=22, rotation_speed=0.42)]
        if recipe == "black_hole":
            radius = 4.6 * multiplier
            return [_effect(base, "black_hole", position, [1, 1, 1], "black_hole", provenance, count=1, color="#020208", secondary="#ff8e42", size=radius, intensity=6, radius=radius, spread=30, rotation_speed=0.08)]
        if recipe == "planet":
            radius = 4.2 * multiplier
            return [_effect(base, "planet", position, [1, 1, 1], entity["concept"], provenance, count=1, color=primary, secondary=palette["accentAlt"], size=radius, intensity=1.2, radius=radius, spread=16, rotation_speed=0.025)]
        if recipe == "crater":
            radius = 5.2 * multiplier
            return [_effect(base, "crater", position, [1, 1, 1], "crater", provenance, count=1, color=_color(attributes.get("color"), "#318dd1"), secondary=palette["secondary"], size=radius, intensity=1, radius=radius, spread=10)]
        if recipe == "cloud":
            return [_effect(base, "cloud_field", position, [1, 1, 1], "cloud", provenance, count=22 if quality == "draft" else 38, color="#dcecff", secondary="#8eb4d0", size=1.55, intensity=0.64, radius=10, spread=24, rotation_speed=0.004)]

        if recipe == "street":
            return [_primitive(base, "plane", [position[0], 0, position[2]], [7 * multiplier, 50, 1], _material(palette["ground"], roughness=0.86, metalness=0.12), "street", provenance, collision="ground", rotation=[-math.pi / 2, 0, 0], tags=("navigation",))]
        if recipe == "wet_road":
            return [_primitive(base, "plane", [position[0], 0.018, position[2]], [6.5 * multiplier, 34, 1], _material("#132638", emissive="#143b52", intensity=0.18, roughness=0.18, metalness=0.3, opacity=0.9), "wet_road", provenance, rotation=[-math.pi / 2, 0, 0], tags=("reflective",))]
        if recipe == "walkway":
            x, y, z = position
            return [
                _primitive(f"{base}_deck", "box", [x, y, z], [3.4 * multiplier, 0.22, 8 * multiplier], _material("#26343c", emissive="#18313d", intensity=0.12, roughness=0.2, metalness=0.72), "walkway", provenance, collision="solid", tags=("wet", "navigation")),
                _primitive(f"{base}_edge_l", "box", [x - 1.65 * multiplier, y + 0.32, z], [0.12, 0.65, 8 * multiplier], _material("#53616a", metalness=0.76, roughness=0.34), "walkway", provenance),
                _primitive(f"{base}_edge_r", "box", [x + 1.65 * multiplier, y + 0.32, z], [0.12, 0.65, 8 * multiplier], _material("#53616a", metalness=0.76, roughness=0.34), "walkway", provenance),
            ]
        if recipe == "warning_light":
            x, y, z = position
            nodes: list[dict[str, Any]] = []
            for index, offset in enumerate((-2.4, -0.8, 0.8, 2.4)):
                side = -1 if index % 2 == 0 else 1
                nodes.append(_primitive(f"{base}_{index}", "sphere", [x + side * 1.9, y + 0.55, z + offset], [0.28, 0.28, 0.28], _material("#ff9a3d", emissive="#ff7a24", intensity=4.8, roughness=0.18), "warning_light", provenance))
            return nodes
        if recipe == "lightning":
            x, y, z = position
            return [
                _primitive(f"{base}_a", "box", [x, y + 2.2, z], [0.16, 4.8 * multiplier, 0.16], _material("#d9f6ff", emissive="#72d9ff", intensity=6.5, roughness=0.12), "lightning", provenance, rotation=[0, 0, 0.38]),
                _primitive(f"{base}_b", "box", [x + 1.2, y - 0.4, z], [0.14, 3.2 * multiplier, 0.14], _material("#d9f6ff", emissive="#72d9ff", intensity=6.5, roughness=0.12), "lightning", provenance, rotation=[0, 0, -0.52]),
            ]
        if recipe == "waterfall":
            return [_primitive(base, "plane", position, [1.2 * multiplier, 5.5 * multiplier, 1], _material("#8bdcf4", emissive="#4ea9cf", intensity=0.72, roughness=0.12, metalness=0.08, opacity=0.72), "waterfall", provenance, tags=("water", "flow"))]
        if recipe in {"shop", "ramen_shop"}:
            label = attributes.get("label") or ("RAMEN" if recipe == "ramen_shop" else resolution["label"].upper())
            x, y, z = position
            return [
                _primitive(f"{base}_body", "box", [x, 2.4, z], [5.2 * multiplier, 4.8, 5], _material(palette["secondary"], roughness=0.78), entity["concept"], provenance, collision="solid"),
                _primitive(f"{base}_front", "box", [x, 1.8, z + 2.55], [4.4 * multiplier, 2.6, 0.18], _material(palette["primary"], emissive=palette["warm"], intensity=0.32, roughness=0.5), entity["concept"], provenance),
                _text(f"{base}_label", label, [x, 3.8, z + 2.75], [1, 1, 1], palette["accent"], "sign", provenance),
            ]
        if recipe == "neon_sign":
            label = attributes.get("label") or resolution["label"]
            return [_text(base, label, position, [1.1 * multiplier, 1.1, 1.1], accent, "neon_sign", provenance)]
        if recipe == "street_light":
            x, _, z = position
            return [
                _primitive(f"{base}_post", "cylinder", [x, 2.8, z], [0.18, 5.6, 0.18], _material("#384654", roughness=0.5, metalness=0.66), "street_light", provenance),
                _primitive(f"{base}_lamp", "sphere", [x, 5.65, z], [0.72, 0.45, 0.72], _material(palette["accentAlt"], emissive=palette["accentAlt"], intensity=5, roughness=0.18), "street_light", provenance),
                _light(f"{base}_light", "point", [x, 5.45, z], palette["accentAlt"], 12, provenance, light_range=16),
            ]
        if recipe == "station":
            x, y, z = position
            shell = palette["primary"]
            return [
                _primitive(f"{base}_body", "cylinder", [x, y + 1.8, z], [2.4 * multiplier, 7.4 * multiplier, 2.4 * multiplier], _material(shell, roughness=0.42, metalness=0.48), entity["concept"], provenance, collision="solid", rotation=[0, 0, math.pi / 2]),
                _primitive(f"{base}_cap_l", "sphere", [x - 3.65 * multiplier, y + 1.8, z], [2.3 * multiplier, 2.3 * multiplier, 2.3 * multiplier], _material(palette["secondary"], roughness=0.5, metalness=0.42), entity["concept"], provenance),
                _primitive(f"{base}_cap_r", "sphere", [x + 3.65 * multiplier, y + 1.8, z], [2.3 * multiplier, 2.3 * multiplier, 2.3 * multiplier], _material(palette["secondary"], roughness=0.5, metalness=0.42), entity["concept"], provenance),
                _primitive(f"{base}_window", "box", [x, y + 2.1, z + 2.12 * multiplier], [3.8 * multiplier, 0.7, 0.12], _material(palette["accent"], emissive=palette["accent"], intensity=2.4, roughness=0.18, metalness=0.2), entity["concept"], provenance),
                _text(f"{base}_label", attributes.get("label") or "RESEARCH", [x, y + 4.3, z + 1.4], [0.9, 0.9, 0.9], palette["accentAlt"], "station_label", provenance),
            ]
        if recipe == "solar_panel":
            x, y, z = position
            return [
                _primitive(f"{base}_mast", "cylinder", [x, y + 1, z], [0.15, 2, 0.15], _material("#67798c", metalness=0.7), "solar_panel", provenance),
                _primitive(f"{base}_panel", "box", [x, y + 2.1, z], [5 * multiplier, 0.12, 2.4 * multiplier], _material("#173f78", emissive="#1f5fa0", intensity=0.18, roughness=0.3, metalness=0.55), "solar_panel", provenance, rotation=[0.18, 0, 0]),
            ]
        if recipe == "antenna":
            x, y, z = position
            return [
                _primitive(f"{base}_mast", "cylinder", [x, y + 2.2, z], [0.22, 4.4, 0.22], _material("#aebbc8", metalness=0.72), "antenna", provenance),
                _primitive(f"{base}_dish", "sphere", [x, y + 4.7, z], [2.2 * multiplier, 0.35, 2.2 * multiplier], _material(palette["primary"], metalness=0.52, roughness=0.36), "antenna", provenance, rotation=[0.3, 0, 0]),
            ]
        if recipe == "room":
            x, _, z = position
            return [
                _primitive(f"{base}_floor", "plane", [x, 0, z], [14, 12, 1], _material(palette["ground"], roughness=0.86), "floor", provenance, collision="ground", rotation=[-math.pi / 2, 0, 0]),
                _primitive(f"{base}_back", "box", [x, 3.2, z - 6], [14, 6.4, 0.25], _material(palette["secondary"], roughness=0.82), "wall", provenance, collision="solid"),
                _primitive(f"{base}_left", "box", [x - 7, 3.2, z], [0.25, 6.4, 12], _material(palette["primary"], roughness=0.82), "wall", provenance, collision="solid"),
                _primitive(f"{base}_right", "box", [x + 7, 3.2, z], [0.25, 6.4, 12], _material(palette["primary"], roughness=0.82), "wall", provenance, collision="solid"),
            ]
        if recipe in {"library", "bookshelf"}:
            x, y, z = position
            shelves = 3 if recipe == "library" else 1
            return [
                _primitive(f"{base}_{index}", "box", [x + (index - (shelves - 1) / 2) * 3.2, y + 1.8, z], [2.7, 3.8, 0.65], _material("#5f4232", roughness=0.84), "bookshelf", provenance, collision="solid", tags=("books",))
                for index in range(shelves)
            ]
        if recipe == "table":
            x, y, z = position
            return [
                _primitive(f"{base}_top", "box", [x, y + 1.05, z], [3.4, 0.24, 1.8], _material(palette["primary"], roughness=0.78), "table", provenance, collision="solid"),
                _primitive(f"{base}_leg", "box", [x, y + 0.5, z], [0.38, 1.1, 0.38], _material(palette["secondary"], roughness=0.84), "table", provenance),
            ]
        if recipe == "lamp":
            x, y, z = position
            return [
                _primitive(f"{base}_body", "cylinder", [x, y + 1.1, z], [0.25, 2.2, 0.25], _material(palette["secondary"], metalness=0.4), "lamp", provenance),
                _primitive(f"{base}_shade", "sphere", [x, y + 2.4, z], [1.1, 0.65, 1.1], _material(palette["warm"], emissive=palette["warm"], intensity=2.6, opacity=0.92), "lamp", provenance),
                _light(f"{base}_light", "point", [x, y + 2.2, z], palette["warm"], 10, provenance, light_range=10),
            ]
        if recipe == "window":
            return [_primitive(base, "plane", position, [3.6 * multiplier, 2.4 * multiplier, 1], _material("#75b8d1", emissive="#6ea7ba", intensity=0.55, roughness=0.18, metalness=0.22), "window", provenance)]
        if recipe in {"tree", "forest"}:
            x, y, z = position
            tree_count = min(9 if quality == "quality" else 6 if quality == "balanced" else 3, max(count, 1) * (4 if recipe == "forest" else 1))
            result: list[dict[str, Any]] = []
            for index in range(tree_count):
                dx = (index % 3 - 1) * 2.6 + rng.uniform(-0.5, 0.5)
                dz = (index // 3) * -3 + rng.uniform(-0.5, 0.5)
                height = 2.7 + rng.random() * 1.8
                result.extend([
                    _primitive(f"{base}_trunk_{index}", "cylinder", [x + dx, y + height * 0.5, z + dz], [0.32, height, 0.32], _material("#584638", roughness=0.96), "tree", provenance),
                    _primitive(f"{base}_crown_{index}", "sphere", [x + dx, y + height + 1.1, z + dz], [1.7, 2.1, 1.7], _material(palette["primary"], roughness=0.94), "tree", provenance),
                ])
            return result
        if recipe == "rock":
            return [_primitive(base, "sphere", position, [2.1 * multiplier, 1.3 * multiplier, 1.8 * multiplier], _material(palette["secondary"], roughness=0.98), "rock", provenance)]
        if recipe in {"gateway", "historic_town"}:
            x, y, z = position
            width = 5.5 * multiplier
            result = [
                _primitive(f"{base}_left", "box", [x - width / 2, y + 2.5, z], [0.45, 5, 0.55], _material(palette["secondary"], roughness=0.7), entity["concept"], provenance, collision="solid"),
                _primitive(f"{base}_right", "box", [x + width / 2, y + 2.5, z], [0.45, 5, 0.55], _material(palette["secondary"], roughness=0.7), entity["concept"], provenance, collision="solid"),
                _primitive(f"{base}_beam", "box", [x, y + 4.8, z], [width + 1.2, 0.5, 0.7], _material(palette["warm"], roughness=0.64), entity["concept"], provenance),
            ]
            if recipe == "historic_town":
                result.extend([
                    _primitive(f"{base}_house_l", "box", [x - 6.2, y + 2.4, z - 4], [5.2, 4.8, 6], _material(palette["primary"], roughness=0.82), "historic_building", provenance, collision="solid"),
                    _primitive(f"{base}_house_r", "box", [x + 6.2, y + 2.4, z - 7], [5.2, 4.8, 6], _material(palette["primary"], roughness=0.82), "historic_building", provenance, collision="solid"),
                ])
            return result
        if recipe == "stone_path":
            return [_primitive(base, "plane", [position[0], 0.01, position[2]], [4.2, 32, 1], _material("#68706a", roughness=0.96), "stone_path", provenance, collision="ground", rotation=[-math.pi / 2, 0, 0])]
        if recipe == "desert":
            return [_primitive(base, "plane", [position[0], 0, position[2]], [54, 70, 1], _material("#a17b4b", roughness=1), "desert", provenance, collision="ground", rotation=[-math.pi / 2, 0, 0])]
        if recipe == "dune":
            x, y, z = position
            return [_primitive(f"{base}_{index}", "sphere", [x + index * 3.4, y, z - index * 2], [5.2, 0.9, 3.4], _material("#b68a55", roughness=1), "dune", provenance) for index in range(3)]
        if recipe == "outpost":
            x, y, z = position
            return [
                _primitive(f"{base}_body", "box", [x, y + 2.2, z], [6.2, 4.4, 5.4], _material(palette["primary"], roughness=0.76, metalness=0.18), "outpost", provenance, collision="solid"),
                _primitive(f"{base}_beacon", "cylinder", [x, y + 5.6, z], [0.18, 3.2, 0.18], _material("#5c6570", metalness=0.64), "outpost", provenance),
                _light(f"{base}_light", "point", [x, y + 7.2, z], palette["warm"], 14, provenance, light_range=22),
            ]
        if recipe == "lantern":
            x, y, z = position
            return [
                _primitive(base, "sphere", [x, y + 1.8, z], [0.72, 1.0, 0.72], _material(palette["warm"], emissive=palette["warm"], intensity=3.4, opacity=0.92), "lantern", provenance),
                _light(f"{base}_light", "point", [x, y + 1.8, z], palette["warm"], 8, provenance, light_range=9),
            ]
        if recipe == "water":
            reflective_surface = attributes.get("state") == "reflective_surface"
            water_scale = [8 * multiplier, 4 * multiplier, 1] if reflective_surface else [50, 50, 1]
            return [_primitive(base, "plane", [position[0], position[1], position[2]], water_scale, _material("#174d70", emissive="#123d5a", intensity=0.16, roughness=0.16, metalness=0.28, opacity=0.82), "water", provenance, rotation=[-math.pi / 2, 0, 0])]
        if recipe == "floating_island":
            x, y, z = position
            return [
                _primitive(f"{base}_rock", "sphere", [x, y, z], [6.8 * multiplier, 2.4 * multiplier, 5.8 * multiplier], _material("#4e5556", roughness=0.96), "floating_island", provenance),
                _primitive(f"{base}_top", "cylinder", [x, y + 1.3 * multiplier, z], [6.1 * multiplier, 0.7, 5.2 * multiplier], _material("#50725a", roughness=0.94), "floating_island", provenance),
            ]
        if recipe == "abstract_marker":
            x, y, z = position
            return [
                _primitive(f"{base}_core", "sphere", [x, y, z], [2.4 * multiplier, 2.4 * multiplier, 2.4 * multiplier], _material(accent, emissive=accent, intensity=1.4, roughness=0.28, metalness=0.6), "abstract", provenance),
                _primitive(f"{base}_axis", "cylinder", [x, y, z], [0.28, 6 * multiplier, 0.28], _material(palette["accentAlt"], emissive=palette["accentAlt"], intensity=1.2, metalness=0.5), "abstract", provenance, rotation=[math.pi / 2, 0, 0]),
                _text(f"{base}_label", entity["concept"].replace("_", " "), [x, y + 3.6 * multiplier, z], [0.8, 0.8, 0.8], palette["accentAlt"], "abstract_label", provenance),
            ]
        return []
