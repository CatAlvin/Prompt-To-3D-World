from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.v3.capability_registry import normalize_concept


@dataclass(slots=True)
class FidelityResult:
    report: dict[str, Any]
    passed: bool
    unsupported_entities: list[dict[str, Any]]


class SemanticFidelityEvaluator:
    def evaluate(
        self,
        intent: dict[str, Any],
        scene: dict[str, Any],
        resolutions: list[dict[str, Any]],
        layout: dict[str, Any],
    ) -> FidelityResult:
        required = list(intent["constraints"]["requiredEntities"])
        covered = {
            node["provenance"]["entityId"]
            for node in scene["nodes"]
            if node["provenance"]["entityId"] is not None
        }
        covered_required = [entity_id for entity_id in required if entity_id in covered]
        missing = [entity_id for entity_id in required if entity_id not in covered]
        required_coverage = len(covered_required) / len(required) if required else 1.0

        relation_results = [item["satisfied"] for item in layout["relations"]]
        relation_satisfaction = (
            sum(1 for result in relation_results if result) / len(relation_results)
            if relation_results
            else 1.0
        )

        forbidden = {normalize_concept(value) for value in intent["constraints"]["forbiddenConcepts"]}
        forbidden_violations = 0
        for node in scene["nodes"]:
            concepts = {
                normalize_concept(node["semantics"]["category"]),
                *(normalize_concept(tag) for tag in node["semantics"]["tags"]),
            }
            if concepts.intersection(forbidden):
                forbidden_violations += 1

        semantic_nodes = [
            node
            for node in scene["nodes"]
            if node["provenance"]["origin"] not in {"structural", "style"}
        ]
        unrelated = [
            node
            for node in semantic_nodes
            if node["provenance"]["entityId"] is None
        ]
        unrelated_ratio = len(unrelated) / len(semantic_nodes) if semantic_nodes else 0.0

        hero_id = intent["cameraIntent"]["heroEntityId"]
        hero_visible = hero_id is not None and hero_id in covered
        passed = (
            required_coverage >= 0.95
            and relation_satisfaction >= 0.9
            and forbidden_violations == 0
            and unrelated_ratio <= 0.1
            and hero_visible
        )
        report = {
            "status": "passed" if passed else "failed",
            "requiredCoverage": round(required_coverage, 4),
            "relationSatisfaction": round(relation_satisfaction, 4),
            "forbiddenViolations": forbidden_violations,
            "unrelatedRatio": round(unrelated_ratio, 4),
            "heroVisible": hero_visible,
            "coveredEntityIds": covered_required,
            "missingEntityIds": missing,
        }
        scene["semanticReport"] = report
        unsupported = [
            {
                "entityId": resolution["entityId"],
                "concept": resolution["concept"],
                "support": resolution["support"],
                "message": resolution["message"],
            }
            for resolution in resolutions
            if resolution["support"] != "exact"
        ]
        return FidelityResult(report=report, passed=passed, unsupported_entities=unsupported)
