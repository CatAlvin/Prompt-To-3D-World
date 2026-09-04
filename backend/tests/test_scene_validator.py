from __future__ import annotations

from copy import deepcopy

import pytest

from app.domain.scene_validator import SceneValidationError, SceneValidator
from tests.fakes import load_example_scene


def test_example_scene_passes_schema_and_semantic_validation() -> None:
    validator = SceneValidator()
    scene = validator.validate_and_normalize(
        load_example_scene(),
        "A small cyberpunk Japanese alley at night with ramen shops and neon signs.",
    )
    assert scene["schemaVersion"] == "1.0.0"
    assert scene["metadata"]["promptLanguage"] == "en"
    assert len(scene["nodes"]) >= 8


def test_duplicate_ids_are_rejected() -> None:
    validator = SceneValidator()
    scene = load_example_scene()
    scene["nodes"][1]["id"] = scene["nodes"][0]["id"]
    with pytest.raises(SceneValidationError, match="unique"):
        validator.validate_semantics(scene)


def test_parent_must_reference_a_group() -> None:
    validator = SceneValidator()
    scene = deepcopy(load_example_scene())
    scene["nodes"][1]["parentId"] = scene["nodes"][0]["id"]
    with pytest.raises(SceneValidationError, match="not a group"):
        validator.validate_semantics(scene)

