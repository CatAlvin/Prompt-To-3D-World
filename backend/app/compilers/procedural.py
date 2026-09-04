from __future__ import annotations

import hashlib
import math
import random
import re
from copy import deepcopy
from typing import Any

from app.compilers.style_kits import StyleKitRegistry
from app.domain.scene_validator import SceneValidator
from app.domain.v2_validator import ScenePlanValidator, SceneV2Validator


COMPILER_VERSION = "procedural-2.0.1"


def request_fingerprint(prompt: str, preferences: dict[str, Any]) -> str:
    normalized = " ".join(prompt.strip().split()).lower()
    options = "|".join(f"{key}={preferences[key]}" for key in sorted(preferences))
    return hashlib.sha256(f"{normalized}|{options}".encode("utf-8")).hexdigest()


def _default_seed(prompt: str) -> int:
    return int(hashlib.sha256(prompt.strip().encode("utf-8")).hexdigest()[:8], 16) % 2147483647


def specialized_archetype(prompt: str) -> str | None:
    value = prompt.lower()
    tokens = set(re.findall("[a-z0-9]+", value))
    if tokens.intersection({"lunar", "moon", "moonbase"}) or any(
        term in value for term in ("月球", "月面", "月坑", "环形山", "陨石坑")
    ):
        return "lunar_station"
    if "crater" in tokens and tokens.intersection(
        {"station", "base", "research", "laboratory", "lab", "outpost", "habitat"}
    ):
        return "lunar_station"
    return None


def choose_archetype(prompt: str) -> str:
    value = prompt.lower()
    if forced := specialized_archetype(prompt):
        return forced
    if re.search(r"room|interior|bedroom|cabin|cafe|studio|室内|房间|卧室|咖啡馆|客厅|小屋", value):
        return "cozy_room"
    if re.search(r"desert|dune|outpost|mars|荒漠|沙漠|驿站|前哨|风沙|补给站", value):
        return "desert_outpost"
    if re.search(r"ancient|old town|riverside town|historic|古镇|古城|老街|古街|古村|水镇", value):
        return "historic_town"
    if re.search(r"\b(?:forest|nature|natural|shrine|mountain|mist|temple|garden|ravine|pine|pines|tree|trees|woodland)\b|森林|自然|神社|山|雾|寺|庭园", value):
        return "misty_nature"
    return "urban_alley"


def _default_style(archetype: str) -> str:
    if archetype == "lunar_station":
        return "lunar_research_v1"
    if archetype in {"cozy_room"}:
        return "cozy_lowpoly_v1"
    if archetype in {"misty_nature", "desert_outpost"}:
        return "misty_nature_v1"
    return "cyberpunk_tokyo_v1"


def build_local_plan(prompt: str, preferences: dict[str, Any]) -> dict[str, Any]:
    archetype = choose_archetype(prompt)
    style_kit = preferences.get("styleKit") or "auto"
    if style_kit == "auto":
        style_kit = _default_style(archetype)
    seed_value = preferences.get("seed")
    seed = int(seed_value) if seed_value is not None else _default_seed(prompt)
    density = float(preferences.get("density", 0.68))
    time = preferences.get("time", "auto")
    weather = preferences.get("weather", "auto")
    prompt_value = prompt.lower()
    if preferences.get("time", "auto") == "auto":
        prompt_tokens = set(re.findall("[a-z0-9]+", prompt_value))
        if prompt_tokens.intersection({"sunrise", "dawn", "morning"}) or any(term in prompt_value for term in ("日出", "黎明", "清晨")):
            time = "sunrise"
        elif prompt_tokens.intersection({"sunset", "dusk"}) or any(term in prompt_value for term in ("日落", "黄昏", "傍晚")):
            time = "sunset"
        elif prompt_tokens.intersection({"night", "midnight"}) or any(term in prompt_value for term in ("夜晚", "深夜", "夜间")):
            time = "night"
        elif archetype == "lunar_station":
            time = "sunrise"
    if weather == "auto" and archetype == "lunar_station":
        weather = "clear"

    archetype_details = {
        "urban_alley": (
            "雨夜巷弄",
            "A narrow walkable alley with layered shopfronts, one readable sign, wet pavement and controlled neon contrast.",
            ["readable_sign", "wet_road", "street_lights"],
            ["traffic", "daylight"],
        ),
        "cozy_room": (
            "暖光居室",
            "A human-scale low-poly room with a clear circulation loop, warm pools of light and a framed exterior view.",
            ["window", "table", "warm_lamp"],
            ["harsh_neon", "outdoor_traffic"],
        ),
        "misty_nature": (
            "雾林石径",
            "A layered forest path with a visible shrine anchor, irregular vegetation clusters and depth carried by mist.",
            ["stone_path", "shrine_gate", "tree_clusters"],
            ["urban_signage", "cars"],
        ),
        "desert_outpost": (
            "荒漠驿站",
            "A wind-cut desert approach with a sheltered outpost, sparse props and a strong sunset silhouette.",
            ["outpost", "dune_path", "signal_light"],
            ["dense_forest", "rain"],
        ),
        "historic_town": (
            "古镇灯巷",
            "A compact historic lane with layered eaves, lantern rhythm, a legible destination and restrained modern elements.",
            ["lanterns", "stone_road", "gateway"],
            ["skyscrapers", "cars"],
        ),
        "lunar_station": (
            "蓝坑晨曦站",
            "A quiet lunar research habitat overlooks a cobalt crater, with an elevated approach, solar arrays, antenna silhouettes and low golden sunrise light.",
            ["research_habitat", "blue_crater", "sunrise_horizon", "solar_arrays"],
            ["trees", "vegetation", "shrine_gate", "street_shops", "rain"],
        ),
    }
    title, direction, must_include, avoid = archetype_details[archetype]
    return ScenePlanValidator().validate(
        {
            "schemaVersion": "1.0.0",
            "title": title,
            "archetype": archetype,
            "visualDirection": direction,
            "seed": seed,
            "styleKit": style_kit,
            "time": time,
            "weather": weather,
            "density": max(0.2, min(1.0, density)),
            "scale": preferences.get("scale", "compact"),
            "mainPath": {
                "shape": "bent" if archetype in {"urban_alley", "historic_town"} else "straight",
                "width": 4.2 if archetype == "lunar_station" else (3.4 if archetype != "cozy_room" else 2.4),
                "length": 44 if archetype == "lunar_station" else (32 if archetype != "cozy_room" else 14),
            },
            "zones": [
                {"id": "arrival", "purpose": "safe camera arrival", "side": "center", "weight": 0.55},
                {"id": "hero_zone", "purpose": must_include[0], "side": "right", "weight": 1.0},
                {"id": "depth_zone", "purpose": "depth and occlusion reveal", "side": "left", "weight": 0.72},
            ],
            "heroAnchors": [must_include[0]],
            "mustInclude": must_include,
            "avoid": avoid,
        }
    )


def _transform(position: list[float], scale: list[float], rotation: list[float] | None = None) -> dict[str, Any]:
    return {"position": position, "rotation": rotation or [0, 0, 0], "scale": scale}


def _material(color: str, *, emissive: str | None = None, intensity: float = 0, roughness: float = 0.72, metalness: float = 0.04, opacity: float = 1) -> dict[str, Any]:
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
    return {"category": category, "tags": list(dict.fromkeys(tags))[:8]}


def _primitive(node_id: str, subtype: str, position: list[float], scale: list[float], material: dict[str, Any], category: str, *, collision: str = "none", rotation: list[float] | None = None, tags: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "id": node_id,
        "kind": "primitive",
        "subtype": subtype,
        "parentId": None,
        "transform": _transform(position, scale, rotation),
        "material": material,
        "semantics": _semantics(category, *tags),
        "collision": {"mode": collision},
    }


def _text(node_id: str, value: str, position: list[float], scale: list[float], color: str, category: str, rotation: list[float] | None = None) -> dict[str, Any]:
    return {
        "id": node_id,
        "kind": "text",
        "subtype": "label",
        "parentId": None,
        "transform": _transform(position, scale, rotation),
        "text": {"value": value[:40], "fontSize": 0.55, "align": "center"},
        "material": _material(color, emissive=color, intensity=4.5),
        "semantics": _semantics(category, "hero", "readable"),
    }


def _light(node_id: str, subtype: str, position: list[float], color: str, intensity: float, *, cast_shadow: bool = False, light_range: float = 18) -> dict[str, Any]:
    return {
        "id": node_id,
        "kind": "light",
        "subtype": subtype,
        "parentId": None,
        "transform": _transform(position, [1, 1, 1]),
        "light": {"color": color, "intensity": intensity, "range": light_range, "decay": 2, "castShadow": cast_shadow},
        "semantics": _semantics("lighting", "rig"),
    }


def _asset(node_id: str, asset_ref: str, fallback: str, position: list[float], scale: list[float], category: str) -> dict[str, Any]:
    return {
        "id": node_id,
        "kind": "asset",
        "subtype": "catalog_asset",
        "parentId": None,
        "transform": _transform(position, scale),
        "assetRef": asset_ref,
        "variant": "default",
        "lod": 1,
        "semantics": _semantics(category, "catalog"),
        "collision": {"mode": "none"},
        "fallback": fallback,
    }


def _procedural(node_id: str, subtype: str, position: list[float], count: int, spread: float, height: float, category: str) -> dict[str, Any]:
    fallback = "cylinders" if subtype == "tree_cluster" else "spheres" if subtype == "rock_cluster" else "boxes"
    return {
        "id": node_id,
        "kind": "procedural",
        "subtype": subtype,
        "parentId": None,
        "transform": _transform(position, [1, 1, 1]),
        "generator": f"{subtype}_v1",
        "parameters": {"count": count, "spacing": max(0.2, spread / max(count, 1)), "spread": spread, "height": height},
        "semantics": _semantics(category, "procedural"),
        "fallback": fallback,
    }


def _instances(node_id: str, primitive: str, material: dict[str, Any], transforms: list[dict[str, Any]], category: str) -> dict[str, Any]:
    return {
        "id": node_id,
        "kind": "instances",
        "subtype": "primitive_instances",
        "parentId": None,
        "transform": _transform([0, 0, 0], [1, 1, 1]),
        "source": {"primitive": primitive, "material": material},
        "instances": transforms,
        "semantics": _semantics(category, "instanced"),
    }


def _prefab(node_id: str, prefab_ref: str, position: list[float], scale: list[float], category: str, rotation: list[float] | None = None) -> dict[str, Any]:
    return {
        "id": node_id,
        "kind": "prefab",
        "subtype": "registered_prefab",
        "parentId": None,
        "transform": _transform(position, scale, rotation),
        "prefabRef": prefab_ref,
        "semantics": _semantics(category, "prefab"),
    }


def _decal(node_id: str, subtype: str, position: list[float], scale: list[float], material: dict[str, Any], category: str) -> dict[str, Any]:
    return {
        "id": node_id,
        "kind": "decal",
        "subtype": subtype,
        "parentId": None,
        "transform": _transform(position, scale, [-math.pi / 2, 0, 0]),
        "material": material,
        "semantics": _semantics(category, "surface_detail"),
    }


class ProceduralSceneCompiler:
    def __init__(self, registry: StyleKitRegistry | None = None) -> None:
        self.registry = registry or StyleKitRegistry()
        self.validator = SceneV2Validator()

    def compile(self, plan: dict[str, Any], *, fingerprint: str, version_kind: str, quality: str) -> dict[str, Any]:
        plan = ScenePlanValidator().validate(deepcopy(plan))
        style = self.registry.get(plan["styleKit"])
        rng = random.Random(plan["seed"])
        archetype = plan["archetype"]
        if archetype == "cozy_room":
            nodes = self._cozy_room(plan, style, rng, version_kind, quality)
        elif archetype == "lunar_station":
            nodes = self._lunar_station(plan, style, rng, version_kind, quality)
        elif archetype in {"misty_nature", "desert_outpost"}:
            nodes = self._nature(plan, style, rng, version_kind, quality)
        else:
            nodes = self._urban(plan, style, rng, version_kind, quality)
        scene = self._document(plan, style, nodes, fingerprint, version_kind, quality)
        return self.validator.validate(scene)

    def _document(self, plan: dict[str, Any], style: dict[str, Any], nodes: list[dict[str, Any]], fingerprint: str, version_kind: str, quality: str) -> dict[str, Any]:
        palette = style["palette"]
        lunar = plan["archetype"] == "lunar_station"
        weather = plan["weather"] if plan["weather"] != "auto" else ("clear" if lunar else ("rain" if plan["styleKit"] == "cyberpunk_tokyo_v1" else "mist"))
        draft = version_kind == "draft" or quality == "draft"
        if plan["archetype"] == "cozy_room":
            sky = "indoor"
        elif lunar:
            sky = plan["time"] if plan["time"] in {"sunrise", "sunset", "night", "day"} else "sunrise"
        elif plan["time"] in {"day", "sunrise", "sunset", "night"}:
            sky = plan["time"]
        else:
            sky = "night" if plan["styleKit"] == "cyberpunk_tokyo_v1" else "overcast"
        return {
            "schemaVersion": "2.0.0",
            "id": f"world_{fingerprint[:16]}",
            "title": plan["title"],
            "seed": plan["seed"],
            "units": "meters",
            "environment": {
                "sky": sky,
                "background": palette["background"],
                "fog": {
                    "type": "linear" if draft or lunar else "exponential",
                    "color": palette["fog"],
                    "density": 0 if draft or lunar else (0.032 if weather == "mist" else 0.014),
                    "near": 24 if lunar else 9,
                    "far": 170 if lunar else 58,
                },
                "ambientLight": {"color": palette["accentAlt"], "intensity": (0.82 if draft else 1.12) if lunar else (0.74 if draft else 1.05)},
                "toneMapping": "acesFilmic",
                "exposure": (1.18 if draft else 1.28) if lunar else (1.12 if draft else 1.24),
                "postprocessing": {"bloom": {"enabled": not draft and style["quality"][quality]["bloom"], "intensity": 0 if draft else (0.38 if lunar else 0.52), "threshold": 0.78 if lunar else 0.72}},
            },
            "camera": {
                "mode": "firstPerson",
                "position": [0, 2.9 if lunar else 1.65, 12 if lunar else (10 if plan["archetype"] != "cozy_room" else 4.8)],
                "lookAt": [3.5 if lunar else 0, 0.28 if lunar else 1.6, -18 if lunar else -8],
                "fov": 72 if lunar else 68,
                "near": 0.05,
                "far": 180,
                "movement": {
                    "speed": 3.4,
                    "sprintMultiplier": 1.8,
                    "eyeHeight": 1.65,
                    **({"baseElevation": 1.25} if lunar else {}),
                },
            },
            "nodes": nodes,
            "metadata": {"generator": "procedural-compiler", "promptLanguage": "unknown"},
            "pipeline": {
                "versionKind": version_kind,
                "planVersion": "1.0.0",
                "compilerVersion": COMPILER_VERSION,
                "styleKit": plan["styleKit"],
                "quality": quality,
                "archetype": plan["archetype"],
                "requestFingerprint": fingerprint,
            },
            "extensions": {"weather": weather, "wetness": 0 if lunar else (0.86 if weather == "rain" else 0.1)},
        }

    def _urban(self, plan: dict[str, Any], style: dict[str, Any], rng: random.Random, version_kind: str, quality: str) -> list[dict[str, Any]]:
        p = style["palette"]
        final = version_kind == "final"
        count = 5 if not final else 8 + round(plan["density"] * 3)
        nodes: list[dict[str, Any]] = [
            _primitive("ground_main", "plane", [0, 0, -5], [7.2, 34, 1], _material(p["ground"], roughness=0.26, metalness=0.28), "ground", collision="ground", rotation=[-math.pi / 2, 0, 0], tags=("walkable", "wet")),
            _procedural("proc_building_left", "building_row", [-5.2, 3.8, -5], count, 30, 7.2, "architecture"),
            _procedural("proc_building_right", "building_row", [5.2, 4.4, -6], count, 32, 8.2, "architecture"),
        ]
        for index in range(count):
            z = 7 - index * (28 / max(count - 1, 1))
            height_left = rng.uniform(5.2, 9.2)
            height_right = rng.uniform(5.6, 10.5)
            nodes.append(_primitive(f"building_left_{index}", "box", [-5.0, height_left / 2, z], [5.7, height_left, 3.0], _material(p["primary"], roughness=0.83), "building", collision="solid", tags=("left_row",)))
            nodes.append(_primitive(f"building_right_{index}", "box", [5.0, height_right / 2, z - 0.4], [5.7, height_right, 3.0], _material(p["secondary"], roughness=0.79), "building", collision="solid", tags=("right_row",)))
        nodes.extend(
            [
                _prefab("hero_shopfront", "prefab_shopfront_v1", [3.25, 1.55, -4.2], [1.4, 1.25, 1], "ramen_shop", rotation=[0, -math.pi / 2, 0]),
                _text("hero_ramen_sign", "ラーメン", [2.12, 3.2, -4.2], [1, 1, 1], p["accent"], "sign", rotation=[0, -math.pi / 2, 0]),
                _text("depth_sign", "雨夜横丁", [-2.12, 3.8, -12.4], [0.78, 0.78, 0.78], p["accentAlt"], "sign", rotation=[0, math.pi / 2, 0]),
                _asset("street_lamp_asset", "asset_street_lamp_v1", "cylinder", [-1.7, 2.2, -1.5], [1, 1, 1], "street_light"),
                _light("key_neon_light", "point", [1.4, 3.2, -4], p["accent"], 54 if final else 24, cast_shadow=final and quality != "draft", light_range=15),
                _light("fill_neon_light", "point", [-1.6, 3.6, -11], p["accentAlt"], 40 if final else 18, light_range=14),
                _light("alley_sky_fill", "directional", [0, 9, 8], "#7d91ad", 1.65 if final else 1.05, light_range=0),
            ]
        )
        if final:
            lanterns = [
                _transform([(-1 if index % 2 else 1) * 2.2, 3.0 + rng.uniform(-0.2, 0.25), 5 - index * 3.3], [0.34, 0.45, 0.34])
                for index in range(9)
            ]
            nodes.extend(
                [
                    _instances("lantern_instances", "sphere", _material(p["warm"], emissive=p["warm"], intensity=3.2, roughness=0.35), lanterns, "lantern"),
                    _decal("puddle_foreground", "puddle", [0.7, 0.018, 5.5], [2.4, 4.8, 1], _material("#243949", roughness=0.12, metalness=0.55, opacity=0.76), "puddle"),
                    _decal("puddle_midground", "puddle", [-0.8, 0.02, -7], [1.7, 3.2, 1], _material("#182d3d", roughness=0.1, metalness=0.62, opacity=0.7), "puddle"),
                    _asset("crate_asset", "asset_wood_crate_v1", "box", [-2.2, 0.45, -3.1], [0.9, 0.9, 0.9], "street_prop"),
                    _instances(
                        "window_left_instances",
                        "box",
                        _material(p["warm"], emissive=p["warm"], intensity=1.5, roughness=0.48),
                        [_transform([-2.08, 2.8 + (index % 2) * 1.7, 4.5 - index * 3.1], [0.1, 0.72, 0.9]) for index in range(8)],
                        "window",
                    ),
                    _instances(
                        "window_right_instances",
                        "box",
                        _material(p["accentAlt"], emissive=p["accentAlt"], intensity=1.35, roughness=0.44),
                        [_transform([2.08, 3.1 + (index % 2) * 1.8, 2.8 - index * 3.4], [0.1, 0.68, 0.82]) for index in range(7)],
                        "window",
                    ),
                ]
            )
        return nodes

    def _cozy_room(self, plan: dict[str, Any], style: dict[str, Any], rng: random.Random, version_kind: str, quality: str) -> list[dict[str, Any]]:
        p = style["palette"]
        final = version_kind == "final"
        nodes = [
            _primitive("ground_main", "plane", [0, 0, 0], [12, 14, 1], _material(p["ground"], roughness=0.78), "floor", collision="ground", rotation=[-math.pi / 2, 0, 0], tags=("walkable",)),
            _primitive("wall_back", "box", [0, 3, -7], [12, 6, 0.25], _material(p["secondary"], roughness=0.9), "wall", collision="solid"),
            _primitive("wall_left", "box", [-6, 3, 0], [0.25, 6, 14], _material(p["primary"], roughness=0.9), "wall", collision="solid"),
            _primitive("wall_right", "box", [6, 3, 0], [0.25, 6, 14], _material(p["primary"], roughness=0.9), "wall", collision="solid"),
            _procedural("proc_interior_shell", "interior_shell", [0, 0, 0], 6, 12, 6, "architecture"),
            _prefab("hero_window", "prefab_cozy_window_v1", [0, 3, -6.82], [2.2, 1.5, 1], "window"),
            _primitive("table_top", "box", [0, 1.15, -1.8], [3.5, 0.18, 1.8], _material(p["primary"], roughness=0.62), "table", collision="solid"),
            _primitive("sofa_body", "box", [3.7, 0.72, 1.2], [2.8, 1.15, 1.3], _material(p["accent"], roughness=0.88), "sofa", collision="solid"),
            _decal("woven_rug", "marking", [0, 0.02, 1.3], [4.2, 5.4, 1], _material(p["accent"], roughness=0.96, opacity=0.88), "rug"),
            _light("warm_key_light", "point", [0, 4.5, -1.2], p["warm"], 16 if final else 7, cast_shadow=final and quality != "draft", light_range=16),
            _light("window_fill_light", "directional", [-3, 5, -4], p["accentAlt"], 1.6 if final else 0.8, light_range=0),
        ]
        chair_transforms = [
            _transform([-1.8, 0.55, -1.8], [0.75, 1.1, 0.75]),
            _transform([1.8, 0.55, -1.8], [0.75, 1.1, 0.75]),
        ]
        nodes.append(_instances("chair_instances", "box", _material(p["secondary"], roughness=0.7), chair_transforms, "chair"))
        if final:
            nodes.extend(
                [
                    _asset("crate_side_table", "asset_wood_crate_v1", "box", [-4.2, 0.5, 2.2], [1.2, 1, 1.2], "side_table"),
                    _instances(
                        "shelf_objects",
                        "sphere",
                        _material(p["accentAlt"], roughness=0.64),
                        [_transform([-4.8 + index * 0.65, 2.1 + (index % 2) * 0.55, -5.9], [0.24, 0.32, 0.24]) for index in range(7)],
                        "decor",
                    ),
                    _text("room_anchor_label", "灯りの部屋", [0, 4.65, -6.72], [0.72, 0.72, 0.72], p["warm"], "sign"),
                ]
            )
        return nodes

    def _lunar_station(self, plan: dict[str, Any], style: dict[str, Any], rng: random.Random, version_kind: str, quality: str) -> list[dict[str, Any]]:
        p = style["palette"]
        final = version_kind == "final"
        rim_count = 18 if final else 9
        rim_transforms = []
        for index in range(rim_count):
            angle = (math.pi * 2 * index) / rim_count
            rim_transforms.append(
                _transform(
                    [3.5 + math.cos(angle) * 13.5, 0.42, -18 + math.sin(angle) * 9.5],
                    [rng.uniform(1.0, 2.2), rng.uniform(0.65, 1.35), rng.uniform(0.9, 1.9)],
                    [rng.uniform(-0.2, 0.2), rng.uniform(0, math.pi), rng.uniform(-0.16, 0.16)],
                )
            )
        solar_transforms = [
            _transform([-8.2, 1.75, -4.5], [4.8, 0.12, 2.3], [-0.12, 0.18, 0]),
            _transform([8.2, 1.75, -4.5], [4.8, 0.12, 2.3], [-0.12, -0.18, 0]),
        ]
        nodes: list[dict[str, Any]] = [
            _primitive("ground_main", "plane", [0, 0, -10], [44, 68, 1], _material(p["ground"], roughness=0.98, metalness=0.02), "lunar_regolith", collision="ground", rotation=[-math.pi / 2, 0, 0], tags=("walkable", "airless")),
            _primitive("approach_deck", "box", [0, 1.28, 1], [4.2, 0.26, 22], _material(p["secondary"], roughness=0.56, metalness=0.48), "station_walkway", tags=("main_path", "elevated")),
            _primitive("blue_crater_outer", "cylinder", [3.5, 0.08, -18], [28, 0.18, 20], _material("#173d68", emissive="#123d6e", intensity=0.42, roughness=0.68, metalness=0.18), "blue_crater", tags=("hero", "crater_rim")),
            _primitive("blue_crater_basin", "cylinder", [3.5, 0.18, -18], [20, 0.12, 13], _material(p["accentAlt"], emissive=p["accent"], intensity=1.05 if final else 0.34, roughness=0.3, metalness=0.26), "blue_crater", tags=("hero", "basin")),
            _instances("crater_rim_instances", "sphere", _material("#9ca5ad", roughness=0.99), rim_transforms, "lunar_rock"),
            _prefab("research_habitat_west", "prefab_lunar_module_v1", [-7.2, 2.75, -8.2], [1.15, 1.15, 1.15], "research_habitat", rotation=[0, 0.18, 0]),
            _instances("solar_array_instances", "box", _material("#163b66", emissive="#1d5c96", intensity=0.28, roughness=0.24, metalness=0.7), solar_transforms, "solar_array"),
            _asset("communications_antenna", "asset_lunar_antenna_v1", "cylinder", [10.5, 3.25, -7.5], [0.55, 5.4, 0.55], "antenna"),
            _primitive("sunrise_disc", "sphere", [17.5, 6.2, -46], [4.2, 4.2, 4.2], _material(p["warm"], emissive=p["warm"], intensity=5.2 if final else 2.2, roughness=0.28), "sun", tags=("sunrise", "horizon")),
            _light("sunrise_key_light", "directional", [16, 10, -34], p["warm"], 3.4 if final else 1.65, cast_shadow=final and quality != "draft", light_range=0),
            _light("earth_fill_light", "directional", [-12, 9, 4], p["accentAlt"], 1.45 if final else 0.72, light_range=0),
            _text("station_identifier", "LUNAR RESEARCH 07", [-6.1, 4.35, -7.0], [0.65, 0.65, 0.65], p["accentAlt"], "station_sign", rotation=[0, 0.18, 0]),
        ]
        if final:
            railing_transforms = [
                _transform([side * 2.25, 1.92, 10 - index * 2.8], [0.1, 1.15, 0.1])
                for index in range(7)
                for side in (-1, 1)
            ]
            nodes.extend(
                [
                    _prefab("research_habitat_east", "prefab_lunar_module_v1", [8.4, 2.6, -7.5], [0.92, 0.92, 0.92], "research_habitat", rotation=[0, -0.28, 0]),
                    _instances("walkway_rail_posts", "box", _material(p["primary"], roughness=0.48, metalness=0.62), railing_transforms, "safety_rail"),
                    _asset("foreground_moon_rock", "asset_rock_v1", "sphere", [-11.5, 0.75, 4], [2.7, 1.4, 2.2], "lunar_rock"),
                    _instances(
                        "equipment_cases",
                        "box",
                        _material(p["primary"], roughness=0.58, metalness=0.4),
                        [
                            _transform([-4.3, 0.45, -4.2], [1.2, 0.9, 0.8]),
                            _transform([4.5, 0.38, -7.1], [0.9, 0.76, 0.72]),
                            _transform([5.6, 0.32, -6.4], [0.7, 0.64, 0.65]),
                        ],
                        "station_equipment",
                    ),
                ]
            )
        return nodes

    def _nature(self, plan: dict[str, Any], style: dict[str, Any], rng: random.Random, version_kind: str, quality: str) -> list[dict[str, Any]]:
        p = style["palette"]
        final = version_kind == "final"
        desert = plan["archetype"] == "desert_outpost"
        nodes = [
            _primitive("ground_main", "plane", [0, 0, -5], [30, 45, 1], _material(p["ground"], roughness=0.96), "ground", collision="ground", rotation=[-math.pi / 2, 0, 0], tags=("walkable",)),
            _primitive("path_main", "plane", [0, 0.025, -5], [3.4, 38, 1], _material(p["secondary"], roughness=0.88), "path", rotation=[-math.pi / 2, 0, 0], tags=("main_path",)),
            _procedural("proc_tree_cluster", "tree_cluster" if not desert else "rock_cluster", [-7, 0, -8], 14 if final else 7, 24, 5.8, "vegetation" if not desert else "rock"),
            _procedural("proc_rock_cluster", "rock_cluster", [7, 0, -11], 12 if final else 6, 22, 2.2, "rock"),
            _prefab("hero_shrine_gate", "prefab_shrine_gate_v1", [0, 2.6, -14], [1.35, 1.35, 1.35], "hero_anchor"),
            _light("nature_key_light", "directional", [-8, 12, 5], p["accentAlt"], 2.2 if final else 1.1, cast_shadow=final and quality != "draft", light_range=0),
        ]
        tree_transforms = []
        for index in range(12 if final else 6):
            side = -1 if index % 2 else 1
            tree_transforms.append(_transform([side * rng.uniform(4.2, 10), rng.uniform(1.8, 3.1), 8 - index * 3.2], [rng.uniform(0.5, 0.9), rng.uniform(4.5, 7.4), rng.uniform(0.5, 0.9)]))
        nodes.append(_instances("trunk_instances", "cylinder", _material(p["primary"], roughness=0.95), tree_transforms, "tree_trunk"))
        canopy_transforms = [
            _transform([item["position"][0], item["position"][1] * 2 + 0.8, item["position"][2]], [rng.uniform(2.2, 3.8), rng.uniform(2.4, 4.2), rng.uniform(2.2, 3.8)])
            for item in tree_transforms
        ]
        nodes.append(_instances("canopy_instances", "sphere", _material(p["primary"] if desert else p["accent"], roughness=0.91), canopy_transforms, "tree_canopy" if not desert else "dune"))
        if final:
            nodes.extend(
                [
                    _instances("rock_instances", "sphere", _material(p["secondary"], roughness=0.98), [_transform([rng.choice([-1, 1]) * rng.uniform(3.2, 8), rng.uniform(0.25, 0.65), rng.uniform(-20, 8)], [rng.uniform(0.6, 1.8), rng.uniform(0.5, 1.3), rng.uniform(0.6, 1.8)]) for _ in range(10)], "rock"),
                    _asset("hero_rock_asset", "asset_rock_v1", "sphere", [3.7, 0.8, -10], [1.8, 1.4, 1.5], "rock"),
                    _asset("foreground_shrub", "asset_shrub_v1", "sphere", [-3.4, 0.65, 4], [1.2, 1.2, 1.2], "vegetation"),
                    _decal("water_mark", "puddle", [0.5, 0.03, -7], [2.2, 5.8, 1], _material("#456368", roughness=0.18, metalness=0.34, opacity=0.55), "water"),
                ]
            )
        return nodes


def migrate_v1_to_v2(scene: dict[str, Any], *, style_kit: str = "cyberpunk_tokyo_v1", quality: str = "balanced") -> dict[str, Any]:
    migrated = deepcopy(scene)
    fingerprint = hashlib.sha256(f"v1:{scene['id']}:{scene['seed']}".encode("utf-8")).hexdigest()
    migrated["schemaVersion"] = "2.0.0"
    migrated["pipeline"] = {
        "versionKind": "final",
        "planVersion": "1.0.0",
        "compilerVersion": COMPILER_VERSION,
        "styleKit": style_kit,
        "quality": quality,
        "archetype": "urban_alley",
        "requestFingerprint": fingerprint,
    }
    migrated["extensions"] = {"weather": "clear", "wetness": 0}
    migrated["metadata"]["generator"] = "v1-migrator"
    return SceneV2Validator().validate(migrated)
