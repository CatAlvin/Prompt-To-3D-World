from __future__ import annotations

import math
from copy import deepcopy
from typing import Any


ROLE_SCALE = {
    "hero": 1.25,
    "supporting": 0.9,
    "background": 1.5,
    "structural": 1.0,
}

SIZE_SCALE = {
    None: 1.0,
    "tiny": 0.35,
    "small": 0.65,
    "medium": 1.0,
    "large": 1.5,
    "massive": 2.4,
}


class LayoutSolver:
    def solve(self, intent: dict[str, Any]) -> dict[str, Any]:
        mode = intent["sceneMode"]
        entities = intent["entities"]
        positions = self._base_positions(entities, mode)
        ordered_relations = sorted(
            intent["relations"], key=lambda item: item["strength"], reverse=True
        )
        for relation in ordered_relations:
            source = positions.get(relation["sourceId"])
            target = positions.get(relation["targetId"])
            if source is None or target is None:
                continue
            positions[relation["sourceId"]] = self._apply_relation(source, target, relation["type"], mode)

        # Relations such as “lightning inside clouds” and “lightning far from
        # the station” form a small constraint group. Repair failed constraints
        # after the first pass and move the containing entity with its child so
        # a weaker containment rule does not erase a stronger spatial rule.
        containers = {
            relation["sourceId"]: relation["targetId"]
            for relation in intent["relations"]
            if relation["type"] == "inside"
        }
        for _attempt in range(4):
            repaired = False
            for relation in ordered_relations:
                source_id = relation["sourceId"]
                target_id = relation["targetId"]
                source = positions.get(source_id)
                target = positions.get(target_id)
                if source is None or target is None:
                    continue
                if self._relation_satisfied(source, target, relation["type"]):
                    continue
                updated = self._apply_relation(source, target, relation["type"], mode)
                delta = [updated[index] - source[index] for index in range(3)]
                positions[source_id] = updated
                container_id = containers.get(source_id)
                if container_id and relation["type"] != "inside":
                    container = positions[container_id]
                    positions[container_id] = [
                        container[index] + delta[index] for index in range(3)
                    ]
                repaired = True
            if not repaired:
                break

        items: dict[str, dict[str, Any]] = {}
        for entity in entities:
            size = entity.get("attributes", {}).get("size")
            multiplier = ROLE_SCALE[entity["role"]] * SIZE_SCALE.get(size, 1.0)
            items[entity["id"]] = {
                "position": [round(value, 3) for value in positions[entity["id"]]],
                "scaleMultiplier": round(multiplier, 3),
                "layer": self._layer(entity, mode),
            }

        hero_id = intent["cameraIntent"]["heroEntityId"] or entities[0]["id"]
        hero_position = items[hero_id]["position"]
        camera = self._camera(mode, hero_position, intent["cameraIntent"]["framing"])
        return {
            "sceneMode": mode,
            "entities": items,
            "camera": camera,
            "relations": [
                {
                    **deepcopy(relation),
                    "satisfied": self._relation_satisfied(
                        items[relation["sourceId"]]["position"],
                        items[relation["targetId"]]["position"],
                        relation["type"],
                    ),
                }
                for relation in intent["relations"]
            ],
        }

    @staticmethod
    def _base_positions(entities: list[dict[str, Any]], mode: str) -> dict[str, list[float]]:
        positions: dict[str, list[float]] = {}
        role_counts = {"hero": 0, "supporting": 0, "background": 0, "structural": 0}
        for index, entity in enumerate(entities):
            role = entity["role"]
            slot = role_counts[role]
            role_counts[role] += 1
            side = -1 if slot % 2 else 1
            row = slot // 2
            if mode in {"orbital", "panorama"}:
                if role == "hero":
                    position = [0 + slot * 10, 5 + row * 4, -32 - row * 10]
                elif role == "supporting":
                    position = [side * (13 + row * 7), 4 + (slot % 3) * 4, -38 - row * 13]
                elif role == "background":
                    position = [side * (20 + row * 12), 9 + row * 4, -90 - row * 28]
                else:
                    position = [side * 8, 0, -20 - row * 10]
            elif mode == "flythrough":
                position = [side * (5 + row * 5), 3 + (slot % 3) * 4, -14 - index * 9]
            elif mode == "interior":
                if role == "hero":
                    position = [0, 1.8, -5]
                elif role == "structural":
                    position = [0, 0, -3]
                else:
                    position = [side * (2.6 + row * 1.4), 1.0, -4.5 - row * 3]
            elif mode == "walkable":
                if role == "hero":
                    position = [side * 3.6, 1.5, -11 - row * 12]
                elif role == "structural":
                    position = [0, 0, -10 - row * 12]
                elif role == "background":
                    position = [side * 10, 3, -32 - row * 14]
                else:
                    position = [side * (4.8 + row), 1.2, -10 - row * 9]
            else:
                angle = index * 2.39996
                radius = 3.5 + math.sqrt(index) * 2.2
                position = [math.cos(angle) * radius, 1.3 + (index % 3) * 0.7, math.sin(angle) * radius - 5]
            positions[entity["id"]] = position
        return positions

    @staticmethod
    def _apply_relation(source: list[float], target: list[float], relation: str, mode: str) -> list[float]:
        near = 6 if mode in {"orbital", "panorama"} else 2.6
        far = 34 if mode in {"orbital", "panorama"} else 16
        result = list(source)
        if relation == "left_of":
            result[0] = target[0] - near
            result[1] = target[1]
            result[2] = target[2]
        elif relation == "right_of":
            result[0] = target[0] + near
            result[1] = target[1]
            result[2] = target[2]
        elif relation == "in_front_of":
            result[1] = target[1]
            result[2] = target[2] + near
        elif relation == "behind":
            result[1] = target[1]
            result[2] = target[2] - near
        elif relation == "above":
            result[1] = target[1] + near
            result[2] = target[2]
        elif relation == "below":
            result[1] = target[1] - near
            result[2] = target[2]
        elif relation == "far_from":
            result[2] = target[2] - far
        elif relation == "inside":
            result = list(target)
        elif relation == "near":
            result = [target[0] + near, target[1] + near * 0.2, target[2] - near * 0.25]
        elif relation == "around":
            result[0] = target[0] + near
            result[1] = target[1]
            result[2] = target[2] - near
        elif relation == "orbiting":
            result[0] = target[0] + near * 1.5
            result[1] = target[1] + near * 0.3
        elif relation == "connected_to":
            result = [target[0] + near * 0.65, target[1], target[2]]
        return result

    @staticmethod
    def _layer(entity: dict[str, Any], mode: str) -> str:
        if entity["role"] == "background":
            return "background"
        if mode in {"orbital", "panorama"} and entity["role"] == "supporting":
            return "distant"
        if entity["role"] == "structural":
            return "navigable"
        return "foreground" if entity["role"] == "hero" else "navigable"

    @staticmethod
    def _camera(mode: str, hero: list[float], framing: str) -> dict[str, Any]:
        distance = {"close": 8, "medium": 14, "wide": 24}[framing]
        if mode in {"orbital", "panorama"}:
            position = [hero[0], hero[1] + 4, hero[2] + distance * 1.45]
            camera_mode = "orbit" if mode == "orbital" else "panorama"
            far = 1200
            fov = 62 if mode == "orbital" else 74
        elif mode == "flythrough":
            position = [
                hero[0] - distance * 0.35,
                hero[1] + distance * 0.2,
                hero[2] + distance * 1.15,
            ]
            camera_mode = "fly"
            far = 600
            fov = 70
        elif mode == "diorama":
            position = [12, 10, 16]
            camera_mode = "orbit"
            far = 300
            fov = 55
        else:
            position = [0, 1.65, 8 if mode == "walkable" else 4.5]
            camera_mode = "firstPerson"
            far = 240
            fov = 68
        return {
            "mode": camera_mode,
            "position": [round(value, 3) for value in position],
            "lookAt": [round(value, 3) for value in hero],
            "fov": fov,
            "near": 0.05,
            "far": far,
            "movement": {"speed": 3.4, "sprintMultiplier": 1.8, "eyeHeight": 1.65},
        }

    @staticmethod
    def _relation_satisfied(source: list[float], target: list[float], relation: str) -> bool:
        if relation == "left_of":
            return (
                source[0] < target[0]
                and abs(source[1] - target[1]) <= 0.5
                and abs(source[2] - target[2]) <= 16
            )
        if relation == "right_of":
            return (
                source[0] > target[0]
                and abs(source[1] - target[1]) <= 0.5
                and abs(source[2] - target[2]) <= 16
            )
        if relation == "above":
            return source[1] > target[1] and abs(source[2] - target[2]) <= 16
        if relation == "below":
            return source[1] < target[1] and abs(source[2] - target[2]) <= 16
        if relation == "behind":
            return source[2] < target[2] and abs(source[1] - target[1]) <= 0.5
        if relation == "in_front_of":
            return source[2] > target[2] and abs(source[1] - target[1]) <= 0.5
        if relation == "facing":
            return True
        distance = math.dist(source, target)
        if relation in {"near", "inside", "connected_to"}:
            return distance <= 16
        if relation == "far_from":
            return distance >= 12
        return True
