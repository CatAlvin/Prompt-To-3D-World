from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.domain.scene_validator import SceneValidationError
from app.domain.v3_validator import SceneIntentValidator
from app.providers.base import ProviderError, ProviderResult
from app.services.v3.capability_registry import CapabilityRegistry, normalize_concept


INTENT_TEMPLATE_VERSION = "scene-intent-2.0.0"


@dataclass(slots=True)
class CompiledIntent:
    intent: dict[str, Any]
    provider: str
    model: str
    prompt_tokens: int | None
    completion_tokens: int | None
    retry_count: int


ENTITY_PATTERNS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("pulsar", "celestial", "supporting", (r"\bpulsar\b", r"脉冲星")),
    ("black_hole", "celestial", "supporting", (r"\bblack\s*hole\b", r"黑洞")),
    ("starfield", "environment", "background", (r"\bstarfield\b", r"\bstars\b", r"群星", r"星空", r"繁星")),
    ("star", "celestial", "hero", (r"\bbright\s+star\b", r"\bstar\b", r"\bsun\b", r"恒星", r"耀眼的星")),
    ("planet", "celestial", "supporting", (r"\bplanet\b", r"行星")),
    ("moon", "celestial", "background", (r"\blunar\b", r"\bmoon\b", r"月球", r"月面")),
    ("research_station", "architecture", "hero", (r"\bresearch\s+(?:station|base)\b", r"\bmoonbase\b", r"\bspace\s+station\b", r"研究站", r"科研站", r"实验站")),
    ("crater", "environment", "supporting", (r"\bcrater\b", r"陨石坑", r"月坑", r"环形山")),
    ("solar_panel", "prop", "supporting", (r"\bsolar\s+(?:panel|array)s?\b", r"太阳能板", r"太阳能阵列")),
    ("antenna", "prop", "supporting", (r"\bantenna\b", r"\bradio\s+telescope\b", r"天线", r"射电望远镜")),
    ("ramen_shop", "architecture", "hero", (r"\bramen\b", r"\bnoodle\s+shop\b", r"拉面店?", r"面馆")),
    ("neon_sign", "prop", "supporting", (r"\bneon(?:\s+signs?)?\b", r"霓虹(?:招牌)?")),
    ("street_light", "prop", "supporting", (r"\bstreet\s*lights?\b", r"\blamp\s*posts?\b", r"路灯")),
    ("wet_road", "environment", "supporting", (r"\bwet\s+(?:road|pavement)\b", r"\brainy\s+(?:road|alley)\b", r"湿(?:润)?路面", r"雨夜")),
    ("walkway", "architecture", "supporting", (r"\b(?:metal\s+)?(?:walkway|catwalk)\b", r"金属栈道", r"栈道")),
    ("warning_light", "prop", "supporting", (r"\b(?:warning|beacon)\s+lights?\b", r"警示灯", r"信标灯")),
    ("street", "environment", "structural", (r"\balley\b", r"\bstreet\b", r"\blane\b", r"\broad\b", r"小巷", r"巷弄", r"巷子", r"街巷", r"街道", r"道路")),
    ("library", "architecture", "hero", (r"\blibrary\b", r"\breading\s+room\b", r"图书馆", r"藏书室")),
    ("bookshelf", "prop", "supporting", (r"\bbook(?:shelf|case)\b", r"书架")),
    ("table", "prop", "supporting", (r"\btable\b", r"\bdesk\b", r"桌子", r"书桌")),
    ("lamp", "prop", "supporting", (r"\blamp\b", r"台灯", r"暖灯")),
    ("window", "architecture", "supporting", (r"\bwindow\b", r"窗户", r"玻璃窗", r"舷窗")),
    (
        "room",
        "architecture",
        "structural",
        (
            r"\broom\b",
            r"\binterior\b(?!\s+(?:light|lighting|illumination))",
            r"房间",
            r"室内(?!灯光|照明)",
            r"舱室",
        ),
    ),
    ("forest", "nature", "hero", (r"\bforest\b", r"\bwoodland\b", r"森林", r"树林")),
    ("tree", "nature", "supporting", (r"\btrees?\b", r"\bpines?\b", r"树木?", r"松树")),
    ("rock", "nature", "supporting", (r"\brocks?\b", r"\bstones?\b", r"岩石", r"石头")),
    ("shrine_gate", "architecture", "hero", (r"\btorii\b", r"\bshrine\b", r"鸟居", r"神社")),
    ("stone_path", "environment", "structural", (r"\bstone\s+path\b", r"\btrail\b", r"石径", r"小路")),
    ("desert", "environment", "background", (r"\bdesert\b", r"\bwasteland\b", r"沙漠", r"荒漠")),
    ("dune", "environment", "supporting", (r"\bdunes?\b", r"沙丘")),
    ("outpost", "architecture", "hero", (r"\boutpost\b", r"前哨站", r"前哨", r"驿站")),
    ("historic_town", "architecture", "hero", (r"\bold\s+town\b", r"\bhistoric(?:\s+\w+){0,2}\s+town\b", r"\bancient\s+town\b", r"古镇", r"古城", r"老街")),
    ("gateway", "architecture", "supporting", (r"\bgateway\b", r"\barchway\b", r"城门", r"牌坊")),
    ("lantern", "prop", "supporting", (r"\blanterns?\b", r"灯笼")),
    ("underwater_station", "architecture", "hero", (r"\bunder(?:water|sea)\s+(?:(?:research|science)\s+)?(?:station|lab|laboratory|base)\b", r"海底实验室", r"深海实验站", r"水下研究站")),
    ("water", "environment", "background", (r"\bunderwater\b", r"\bocean\b", r"\bsea\b", r"水下", r"海洋", r"水面")),
    ("waterfall", "nature", "supporting", (r"\bwaterfalls?\b", r"瀑布")),
    ("lightning", "effect", "background", (r"\blightning\b", r"闪电")),
    ("floating_island", "environment", "hero", (r"\bfloating\s+island\b", r"\bsky\s+island\b", r"浮岛", r"空中岛屿")),
    ("cloud", "environment", "background", (r"\bclouds?\b", r"云层", r"云海")),
    ("abstract_sculpture", "abstract", "hero", (r"\babstract\s+(?:sculpture|geometry)\b", r"\bgeometric\s+exhibit\b", r"抽象雕塑", r"几何展品")),
)


def _seed(prompt: str) -> int:
    return int(hashlib.sha256(prompt.strip().encode("utf-8")).hexdigest()[:8], 16) % 2147483647


@lru_cache(maxsize=1)
def _local_validator() -> SceneIntentValidator:
    return SceneIntentValidator()


@lru_cache(maxsize=1)
def _merge_registry() -> CapabilityRegistry:
    return CapabilityRegistry()


def _entity_id(concept: str, used: set[str]) -> str:
    base = f"entity_{normalize_concept(concept) or 'subject'}"[:40]
    candidate = base
    index = 2
    while candidate in used:
        candidate = f"{base[:38]}_{index}"
        index += 1
    used.add(candidate)
    return candidate


NEGATION_START = re.compile(
    r"\b(?:no|without)\b|"
    r"不要(?:出现|包含|加入|生成)?|"
    r"不(?:直接)?出现|"
    r"禁止(?:出现|包含|加入|生成)?|"
    r"避免(?:出现|包含|加入|生成)?|"
    r"排除",
    re.IGNORECASE,
)
NEGATION_END = re.compile(r"[。.!?；;]|\bbut\b|但是|但|不过", re.IGNORECASE)

GENERIC_FORBIDDEN_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("city", (r"\bcit(?:y|ies)\b", r"城市")),
    ("spacecraft", (r"\bspace(?:craft|ship)s?\b", r"宇宙飞船", r"飞船")),
    ("person", (r"\bpeople\b", r"\bpersons?\b", r"\bhumans?\b", r"人物", r"行人")),
    ("vehicle", (r"\bvehicles?\b", r"\bcars?\b", r"车辆", r"汽车")),
    ("shop", (r"\bshops?\b", r"\bstores?\b", r"商铺", r"商店", r"店铺")),
    ("building", (r"\bbuildings?\b", r"建筑")),
    ("rain", (r"\brain\b", r"\brainstorm\b", r"暴雨", r"下雨")),
)


def _negated_ranges(value: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for marker in NEGATION_START.finditer(value):
        tail = value[marker.end() :]
        ending = NEGATION_END.search(tail)
        end = marker.end() + (ending.start() if ending else len(tail))
        ranges.append((marker.end(), end))
    return ranges


def _inside_ranges(position: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start <= position < end for start, end in ranges)


def _first_match(
    value: str,
    patterns: tuple[str, ...],
    negated_ranges: list[tuple[int, int]] | None = None,
) -> str | None:
    excluded = negated_ranges or []
    for pattern in patterns:
        for match in re.finditer(pattern, value, flags=re.IGNORECASE):
            if not _inside_ranges(match.start(), excluded):
                return match.group(0)
    return None


def _infer_time(value: str) -> str:
    if re.search(r"\bsunrise\b|\bdawn\b|\bmorning\b|日出|黎明|清晨", value, re.IGNORECASE):
        return "sunrise"
    if re.search(r"\bsunset\b|\bdusk\b|\bblue\s+hour\b|日落|黄昏|傍晚|蓝调时刻|蓝调时间", value, re.IGNORECASE):
        return "sunset"
    if re.search(r"\bnight\b|\bmidnight\b|夜晚|深夜|夜间", value, re.IGNORECASE):
        return "night"
    if re.search(r"\bindoor\b(?!\s+(?:light|lighting|illumination))|室内(?!灯光|照明)", value, re.IGNORECASE):
        return "indoor"
    if re.search(r"\bday\b|\bnoon\b|白天|正午", value, re.IGNORECASE):
        return "day"
    return "auto"


def _infer_weather(value: str) -> str:
    if re.search(r"\brain\b|\brainy\b|下雨|雨夜|雨天", value, re.IGNORECASE):
        return "rain"
    if re.search(r"\bmist\b|\bfog\b|雾", value, re.IGNORECASE):
        return "mist"
    if re.search(r"\bdust\b|\bsandstorm\b|风沙|沙尘", value, re.IGNORECASE):
        return "dust"
    if re.search(r"\bclear\b|晴朗|清朗", value, re.IGNORECASE):
        return "clear"
    return "auto"


def _style_for(entities: list[dict[str, Any]], scene_mode: str) -> str:
    concepts = {entity["concept"] for entity in entities}
    if concepts.intersection({"ramen_shop", "neon_sign", "street", "wet_road"}):
        return "cyberpunk_tokyo_v1"
    if scene_mode == "interior":
        return "cozy_lowpoly_v1"
    if (
        concepts.intersection({"star", "pulsar", "black_hole", "planet", "moon", "crater"})
        or {"research_station", "moon"}.issubset(concepts)
        or {"research_station", "crater"}.issubset(concepts)
    ):
        return "lunar_research_v1"
    return "misty_nature_v1"


def _title_for(entities: list[dict[str, Any]], scene_mode: str) -> str:
    concepts = {entity["concept"] for entity in entities}
    if "black_hole" in concepts or "pulsar" in concepts:
        return "深空天体观测"
    if "research_station" in concepts and "crater" in concepts:
        return "月面科研站"
    if "ramen_shop" in concepts:
        return "霓雨拉面巷"
    if "library" in concepts:
        return "静谧图书馆"
    if "floating_island" in concepts:
        return "云上浮岛"
    if "underwater_station" in concepts:
        return "深海研究站"
    if "forest" in concepts or "tree" in concepts:
        return "雾林小径"
    if "historic_town" in concepts:
        return "灯火古镇"
    if "desert" in concepts:
        return "荒漠远站"
    return {
        "interior": "室内构想",
        "orbital": "轨道构想",
        "flythrough": "飞越构想",
        "panorama": "全景构想",
        "walkable": "可探索场景",
        "diorama": "微缩世界",
    }[scene_mode]


def _forbidden_concepts(
    value: str,
    negated_ranges: list[tuple[int, int]] | None = None,
) -> list[str]:
    ranges = negated_ranges or _negated_ranges(value)
    forbidden: list[str] = []
    patterns_by_concept = [
        (concept, patterns) for concept, _category, _role, patterns in ENTITY_PATTERNS
    ]
    patterns_by_concept.extend(GENERIC_FORBIDDEN_PATTERNS)
    for concept, patterns in patterns_by_concept:
        if any(
            _inside_ranges(match.start(), ranges)
            for pattern in patterns
            for match in re.finditer(pattern, value, flags=re.IGNORECASE)
        ):
            forbidden.append(concept)
    return list(dict.fromkeys(forbidden))


def build_local_intent(prompt: str, preferences: dict[str, Any]) -> dict[str, Any]:
    value = " ".join(prompt.strip().split())
    negated_ranges = _negated_ranges(value)
    entities: list[dict[str, Any]] = []
    used: set[str] = set()
    for concept, category, role, patterns in ENTITY_PATTERNS:
        matched = _first_match(value, patterns, negated_ranges)
        if matched is None:
            continue
        entity_id = _entity_id(concept, used)
        entities.append(
            {
                "id": entity_id,
                "concept": concept,
                "category": category,
                "role": role,
                "importance": 1.0 if role == "hero" else 0.82 if role == "supporting" else 0.62,
                "count": 1,
                "attributes": {
                    "color": "blue" if concept == "crater" and re.search(r"\bblue\b|蓝", value, re.IGNORECASE) else None,
                    "size": "massive" if concept in {"star", "black_hole", "planet", "moon"} else None,
                    "label": "RAMEN" if concept == "ramen_shop" else None,
                    "state": (
                        "reflective_surface"
                        if concept == "water"
                        and re.search(r"\bpuddles?\b|\breflection\b|积水|水面倒映|倒映", value, re.IGNORECASE)
                        else None
                    ),
                    "brightness": 8 if concept == "star" and re.search(r"\bbright\b|耀眼", value, re.IGNORECASE) else None,
                },
                "sourceText": matched[:200],
            }
        )

    entity_by_concept = {entity["concept"]: entity for entity in entities}
    if {"research_station", "window"}.issubset(entity_by_concept):
        # The station recipe already includes illuminated glazing. Treat a
        # mentioned station window as a component instead of a second object.
        entities = [entity for entity in entities if entity["concept"] != "window"]

    if not entities:
        entities.append(
            {
                "id": _entity_id("scene_subject", used),
                "concept": "scene_subject",
                "category": "abstract",
                "role": "hero",
                "importance": 1.0,
                "count": 1,
                "attributes": {"color": None, "size": "large", "label": None, "state": None, "brightness": None},
                "sourceText": value[:200],
            }
        )

    concepts = {entity["concept"] for entity in entities}
    if (
        concepts.intersection({"star", "pulsar", "black_hole", "planet", "moon"})
        or {"research_station", "crater"}.issubset(concepts)
    ) and not concepts.intersection({"street", "room"}):
        scene_mode = "orbital"
    elif "starfield" in concepts and len(concepts) == 1:
        scene_mode = "panorama"
    elif (
        concepts.intersection({"floating_island", "cloud", "underwater_station"})
        or {"water", "research_station"}.issubset(concepts)
    ) and "room" not in concepts:
        scene_mode = "flythrough"
    elif concepts.intersection({"room", "library"}):
        scene_mode = "interior"
    elif concepts.intersection({"street", "forest", "tree", "desert", "dune", "outpost", "historic_town", "stone_path", "research_station", "crater"}):
        scene_mode = "walkable"
    else:
        scene_mode = "diorama"

    hero = next((entity for entity in entities if entity["role"] == "hero"), None)
    if hero is None:
        hero = next((entity for entity in entities if entity["role"] != "background"), entities[0])
        hero["role"] = "hero"
        hero["importance"] = 1.0

    by_concept = {entity["concept"]: entity["id"] for entity in entities}
    relations: list[dict[str, Any]] = []
    if {"star", "pulsar"}.issubset(by_concept) and re.search(r"\b(?:beside|near|next\s+to)\b|旁边|附近", value, re.IGNORECASE):
        relations.append({"sourceId": by_concept["pulsar"], "type": "near", "targetId": by_concept["star"], "strength": 1.0})
    if {"star", "black_hole"}.issubset(by_concept) and re.search(r"\b(?:far|distant)\b|远处|遥远", value, re.IGNORECASE):
        relations.append({"sourceId": by_concept["black_hole"], "type": "far_from", "targetId": by_concept["star"], "strength": 1.0})
    if {"research_station", "crater"}.issubset(by_concept) and re.search(r"\babove\b|上方|之上", value, re.IGNORECASE):
        relations.append({"sourceId": by_concept["research_station"], "type": "above", "targetId": by_concept["crater"], "strength": 1.0})
    if {"research_station", "floating_island"}.issubset(by_concept) and re.search(
        r"(?:floating\s+island|浮岛).{0,80}(?:research\s+station|研究站|气象站)"
        r"|(?:research\s+station|研究站|气象站).{0,80}(?:floating\s+island|浮岛)",
        value,
        re.IGNORECASE,
    ):
        relations.append(
            {
                "sourceId": by_concept["research_station"],
                "type": "above",
                "targetId": by_concept["floating_island"],
                "strength": 1.0,
            }
        )
    if {"research_station", "antenna"}.issubset(by_concept) and re.search(
        r"(?:右侧|右边|to\s+the\s+right).{0,40}(?:天线|antenna|radar)",
        value,
        re.IGNORECASE,
    ):
        relations.append(
            {
                "sourceId": by_concept["antenna"],
                "type": "right_of",
                "targetId": by_concept["research_station"],
                "strength": 0.95,
            }
        )
    if {"research_station", "walkway"}.issubset(by_concept) and re.search(
        r"(?:研究站|气象站).{0,30}(?:前方|前面).{0,40}(?:栈道|walkway)"
        r"|(?:walkway|catwalk).{0,30}(?:in\s+front\s+of).{0,30}(?:station|研究站)",
        value,
        re.IGNORECASE,
    ):
        relations.append(
            {
                "sourceId": by_concept["walkway"],
                "type": "in_front_of",
                "targetId": by_concept["research_station"],
                "strength": 0.86,
            }
        )
    if {"warning_light", "walkway"}.issubset(by_concept) and re.search(
        r"(?:栈道|walkway).{0,40}(?:两侧|两边|警示灯|warning\s+lights?)",
        value,
        re.IGNORECASE,
    ):
        relations.append(
            {
                "sourceId": by_concept["warning_light"],
                "type": "around",
                "targetId": by_concept["walkway"],
                "strength": 0.76,
            }
        )
    if {"floating_island", "cloud"}.issubset(by_concept) and re.search(
        r"(?:浮岛|岛屿).{0,80}(?:云海|云层).{0,16}(?:之上|上方|下方)"
        r"|(?:above|over).{0,40}(?:cloud|clouds)",
        value,
        re.IGNORECASE,
    ):
        relations.append(
            {
                "sourceId": by_concept["floating_island"],
                "type": "above",
                "targetId": by_concept["cloud"],
                "strength": 1.0,
            }
        )
    if {"rock", "floating_island"}.issubset(by_concept) and re.search(
        r"(?:浮岛|岛屿|岛)(?:边缘|四周|边).{0,50}(?:岩石|石柱)"
        r"|(?:rocks?|stone\s+pillars?).{0,30}(?:around|edge)",
        value,
        re.IGNORECASE,
    ):
        relations.append(
            {
                "sourceId": by_concept["rock"],
                "type": "around",
                "targetId": by_concept["floating_island"],
                "strength": 0.72,
            }
        )
    if {"waterfall", "floating_island"}.issubset(by_concept) and re.search(
        r"(?:瀑布|waterfall).{0,50}(?:岩壁|浮岛|island|cliff)"
        r"|(?:岩壁|浮岛|island|cliff).{0,50}(?:瀑布|waterfall)",
        value,
        re.IGNORECASE,
    ):
        relations.append(
            {
                "sourceId": by_concept["waterfall"],
                "type": "connected_to",
                "targetId": by_concept["floating_island"],
                "strength": 0.82,
            }
        )
    if {"lightning", "research_station"}.issubset(by_concept) and re.search(
        r"(?:远处|遥远|distant|far).{0,50}(?:闪电|lightning)",
        value,
        re.IGNORECASE,
    ):
        relations.append(
            {
                "sourceId": by_concept["lightning"],
                "type": "far_from",
                "targetId": by_concept["research_station"],
                "strength": 0.74,
            }
        )
    if {"water", "research_station"}.issubset(by_concept) and re.search(
        r"\bpuddles?\b|\breflection\b|积水|水面倒映|倒映",
        value,
        re.IGNORECASE,
    ):
        relations.append(
            {
                "sourceId": by_concept["water"],
                "type": "near",
                "targetId": by_concept["research_station"],
                "strength": 0.68,
            }
        )

    style_kit = preferences.get("styleKit", "auto")
    if style_kit == "auto":
        style_kit = _style_for(entities, scene_mode)
    time = preferences.get("time", "auto")
    if time == "auto":
        time = _infer_time(value)
    weather = preferences.get("weather", "auto")
    if weather == "auto":
        weather = _infer_weather(value)
    if scene_mode in {"orbital", "panorama"} and weather == "auto":
        weather = "clear"
    seed = int(preferences["seed"]) if preferences.get("seed") is not None else _seed(value)
    quality = preferences.get("quality", "balanced")
    navigation_required = scene_mode in {"walkable", "interior"}
    required = [entity["id"] for entity in entities if entity["role"] != "structural"]
    optional = [entity["id"] for entity in entities if entity["role"] == "structural"]
    intent = {
        "schemaVersion": "2.0.0",
        "title": _title_for(entities, scene_mode),
        "sceneMode": scene_mode,
        "environment": {"time": time, "weather": weather, "atmosphere": "根据描述建立清晰层次与可读轮廓"},
        "entities": entities,
        "relations": relations,
        "constraints": {
            "requiredEntities": required,
            "forbiddenConcepts": _forbidden_concepts(value, negated_ranges),
            "optionalEntities": optional,
            "maxUnrelatedObjects": 0,
            "preserveOpenSpace": True,
            "navigationRequired": navigation_required,
        },
        "cameraIntent": {"heroEntityId": hero["id"], "framing": "wide" if scene_mode in {"orbital", "panorama", "flythrough"} else "medium", "viewDirection": "优先展示主角与明确关系"},
        "styleIntent": {"styleKit": style_kit, "mood": "coherent, readable, restrained"},
        "quality": quality,
        "seed": seed,
    }
    return _local_validator().validate(intent)


def summarize_intent(intent: dict[str, Any], resolutions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    support_by_entity = {item["entityId"]: item for item in resolutions or []}
    entities = []
    for entity in intent["entities"]:
        resolution = support_by_entity.get(entity["id"])
        entities.append(
            {
                "id": entity["id"],
                "concept": entity["concept"],
                "label": resolution["label"] if resolution else entity["sourceText"],
                "role": entity["role"],
                "support": resolution["support"] if resolution else "pending",
                "message": resolution.get("message") if resolution else None,
            }
        )
    return {
        "title": intent["title"],
        "sceneMode": intent["sceneMode"],
        "entities": entities,
        "relations": intent["relations"],
        "time": intent["environment"]["time"],
        "weather": intent["environment"]["weather"],
        "styleKit": intent["styleIntent"]["styleKit"],
    }


class SceneIntentCompiler:
    def __init__(self, provider: Any, validator: SceneIntentValidator | None = None, max_repairs: int = 1) -> None:
        self.provider = provider
        self.validator = validator or SceneIntentValidator()
        self.max_repairs = max_repairs

    @staticmethod
    def _apply_preferences(intent: dict[str, Any], preferences: dict[str, Any]) -> dict[str, Any]:
        style = preferences.get("styleKit")
        if style and style != "auto":
            intent["styleIntent"]["styleKit"] = style
        for key in ("time", "weather"):
            value = preferences.get(key)
            if value and value != "auto":
                intent["environment"][key] = value
        if preferences.get("quality"):
            intent["quality"] = preferences["quality"]
        if preferences.get("seed") is not None:
            intent["seed"] = int(preferences["seed"])
        return intent

    @staticmethod
    def _merge_explicit_entities(prompt: str, intent: dict[str, Any], preferences: dict[str, Any]) -> dict[str, Any]:
        local = build_local_intent(prompt, preferences)
        registry = _merge_registry()
        forbidden_ordered = list(
            dict.fromkeys(
                normalize_concept(value)
                for value in [
                    *intent["constraints"]["forbiddenConcepts"],
                    *local["constraints"]["forbiddenConcepts"],
                ]
            )
        )
        forbidden = set(forbidden_ordered)
        blocked_ids = {
            entity["id"]
            for entity in intent["entities"]
            if any(
                normalize_concept(entity["concept"]) == concept
                or normalize_concept(entity["concept"]).startswith(f"{concept}_")
                or normalize_concept(entity["concept"]).endswith(f"_{concept}")
                or f"_{concept}_" in normalize_concept(entity["concept"])
                for concept in forbidden
            )
        }
        blocked_ids.update(
            entity["id"]
            for entity in intent["entities"]
            if entity["role"] == "background"
            and entity["category"] in {"environment", "celestial"}
            and (
                "horizon" in normalize_concept(entity["concept"])
                or normalize_concept(entity["concept"]).endswith("_sky")
            )
            and not any(
                token in normalize_concept(entity["concept"])
                for token in ("star", "cloud", "aurora")
            )
        )
        if blocked_ids:
            intent["entities"] = [
                entity for entity in intent["entities"] if entity["id"] not in blocked_ids
            ]
            intent["constraints"]["requiredEntities"] = [
                entity_id
                for entity_id in intent["constraints"]["requiredEntities"]
                if entity_id not in blocked_ids
            ]
            intent["constraints"]["optionalEntities"] = [
                entity_id
                for entity_id in intent["constraints"]["optionalEntities"]
                if entity_id not in blocked_ids
            ]
            intent["relations"] = [
                relation
                for relation in intent["relations"]
                if relation["sourceId"] not in blocked_ids
                and relation["targetId"] not in blocked_ids
            ]
        if local["sceneMode"] != "diorama":
            intent["sceneMode"] = local["sceneMode"]
            intent["constraints"]["navigationRequired"] = local["constraints"]["navigationRequired"]

        provider_by_capability: dict[str, str] = {}
        for entity in intent["entities"]:
            capability_id = registry.resolve(entity, intent["sceneMode"])["capabilityId"]
            provider_by_capability.setdefault(capability_id, entity["id"])

        known_ids = {entity["id"] for entity in intent["entities"]}
        local_to_final: dict[str, str] = {}
        local_optional = set(local["constraints"]["optionalEntities"])
        for entity in local["entities"]:
            capability_id = registry.resolve(entity, local["sceneMode"])["capabilityId"]
            existing_id = provider_by_capability.get(capability_id)
            if (
                entity["concept"] == "scene_subject"
                or normalize_concept(entity["concept"]) in forbidden
            ):
                continue
            if existing_id:
                local_to_final[entity["id"]] = existing_id
                continue
            candidate = deepcopy(entity)
            candidate["id"] = _entity_id(candidate["concept"], known_ids)
            intent["entities"].append(candidate)
            if entity["id"] in local_optional:
                intent["constraints"]["optionalEntities"].append(candidate["id"])
            else:
                intent["constraints"]["requiredEntities"].append(candidate["id"])
            provider_by_capability[capability_id] = candidate["id"]
            local_to_final[entity["id"]] = candidate["id"]

        relation_keys = {
            (relation["sourceId"], relation["type"], relation["targetId"])
            for relation in intent["relations"]
        }
        for relation in local["relations"]:
            source_id = local_to_final.get(relation["sourceId"])
            target_id = local_to_final.get(relation["targetId"])
            if not source_id or not target_id or source_id == target_id:
                continue
            key = (source_id, relation["type"], target_id)
            if key in relation_keys:
                continue
            translated = deepcopy(relation)
            translated["sourceId"] = source_id
            translated["targetId"] = target_id
            intent["relations"].append(translated)
            relation_keys.add(key)
        intent["constraints"]["forbiddenConcepts"] = forbidden_ordered
        positive_concepts = {
            normalize_concept(entity["concept"])
            for entity in intent["entities"]
        }
        provider_style = intent["styleIntent"]["styleKit"]
        incompatible_style = (
            provider_style == "cyberpunk_tokyo_v1"
            and not any(
                any(token in concept for token in ("street", "alley", "ramen", "neon", "shop"))
                for concept in positive_concepts
            )
        ) or (
            provider_style == "lunar_research_v1"
            and not any(
                any(token in concept for token in ("moon", "lunar", "crater", "star", "pulsar", "planet"))
                for concept in positive_concepts
            )
        ) or (
            provider_style == "cozy_lowpoly_v1"
            and intent["sceneMode"] != "interior"
        )
        if provider_style == "auto" or incompatible_style:
            intent["styleIntent"]["styleKit"] = local["styleIntent"]["styleKit"]
        if intent["environment"]["time"] == "auto":
            intent["environment"]["time"] = local["environment"]["time"]
        if intent["environment"]["weather"] == "auto":
            intent["environment"]["weather"] = local["environment"]["weather"]
        entity_ids = {entity["id"] for entity in intent["entities"]}
        intent["relations"] = [
            relation
            for relation in intent["relations"]
            if relation["sourceId"] in entity_ids and relation["targetId"] in entity_ids
        ]
        hero_id = intent["cameraIntent"]["heroEntityId"]
        if hero_id not in entity_ids:
            intent["cameraIntent"]["heroEntityId"] = next(
                (entity["id"] for entity in intent["entities"] if entity["role"] == "hero"),
                intent["entities"][0]["id"],
            )
        return intent

    async def compile(self, prompt: str, preferences: dict[str, Any]) -> CompiledIntent:
        if not hasattr(self.provider, "generate_intent"):
            return CompiledIntent(
                intent=build_local_intent(prompt, preferences),
                provider=getattr(self.provider, "name", "local"),
                model=getattr(self.provider, "model", "local-intent"),
                prompt_tokens=None,
                completion_tokens=None,
                retry_count=0,
            )
        repair_context: dict[str, Any] | None = None
        prompt_tokens = 0
        completion_tokens = 0
        latest: ProviderResult | None = None
        last_errors: list[str] = []
        registry = CapabilityRegistry()
        provider_preferences = {
            **preferences,
            "engineCapabilities": [
                item["concept"] for item in registry.list_public()
                if item["concept"] != "abstract_marker"
            ],
        }
        for attempt in range(self.max_repairs + 1):
            latest = await self.provider.generate_intent(
                prompt,
                provider_preferences,
                self.validator.schema,
                repair_context,
            )
            prompt_tokens += latest.prompt_tokens or 0
            completion_tokens += latest.completion_tokens or 0
            invalid: Any = latest.content
            try:
                if latest.finish_reason == "length":
                    raise SceneValidationError(["The provider intent was truncated"])
                parsed = json.loads(latest.content)
                if not isinstance(parsed, dict):
                    raise SceneValidationError(["The provider intent must be a JSON object"])
                invalid = parsed
                intent = self._apply_preferences(parsed, preferences)
                intent = self._merge_explicit_entities(prompt, intent, preferences)
                self.validator.validate(intent)
                return CompiledIntent(
                    intent=intent,
                    provider=latest.provider,
                    model=latest.model,
                    prompt_tokens=prompt_tokens or None,
                    completion_tokens=completion_tokens or None,
                    retry_count=attempt,
                )
            except json.JSONDecodeError as exc:
                last_errors = [f"Invalid JSON at line {exc.lineno}, column {exc.colno}"]
            except SceneValidationError as exc:
                last_errors = exc.details
            repair_context = {"invalid_output": invalid, "errors": last_errors}
        raise ProviderError("INTENT_OUTPUT_INVALID", "Kimi 场景理解未通过校验，已保留可探索草稿。", True)
