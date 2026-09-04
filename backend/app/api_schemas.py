from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class GenerationPreferences(BaseModel):
    quality: Literal["fast", "balanced", "quality"] = "balanced"


class GenerationCreate(BaseModel):
    prompt: str = Field(min_length=3, max_length=2000)
    preferences: GenerationPreferences = Field(default_factory=GenerationPreferences)

    @field_validator("prompt")
    @classmethod
    def normalize_prompt(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 3:
            raise ValueError("Prompt 至少需要 3 个字符")
        return normalized


class GenerationPreferencesV2(BaseModel):
    styleKit: Literal["auto", "cyberpunk_tokyo_v1", "cozy_lowpoly_v1", "misty_nature_v1", "lunar_research_v1"] = "auto"
    time: Literal["auto", "day", "sunrise", "sunset", "night", "indoor"] = "auto"
    weather: Literal["auto", "clear", "rain", "mist", "dust"] = "auto"
    density: float = Field(default=0.68, ge=0.2, le=1)
    quality: Literal["draft", "balanced", "quality"] = "balanced"
    scale: Literal["compact", "medium", "wide"] = "compact"
    seed: int | None = Field(default=None, ge=0, le=2147483647)


class GenerationCreateV2(BaseModel):
    prompt: str = Field(min_length=3, max_length=2000)
    preferences: GenerationPreferencesV2 = Field(default_factory=GenerationPreferencesV2)

    @field_validator("prompt")
    @classmethod
    def normalize_prompt(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if len(normalized) < 3:
            raise ValueError("Prompt 至少需要 3 个字符")
        return normalized


class GenerationPreferencesV3(GenerationPreferencesV2):
    pass


class GenerationCreateV3(BaseModel):
    prompt: str = Field(min_length=3, max_length=2000)
    preferences: GenerationPreferencesV3 = Field(default_factory=GenerationPreferencesV3)

    @field_validator("prompt")
    @classmethod
    def normalize_prompt(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if len(normalized) < 3:
            raise ValueError("Prompt 至少需要 3 个字符")
        return normalized


class SceneCommandPayload(BaseModel):
    sourceVersionId: str = Field(min_length=8, max_length=64)
    type: Literal["set_environment", "set_style_kit", "set_density", "remove_by_semantics"]
    parameters: dict[str, Any] = Field(default_factory=dict)


class SceneCommandPayloadV3(BaseModel):
    sourceVersionId: str = Field(min_length=8, max_length=64)
    type: Literal[
        "set_environment",
        "set_style_kit",
        "set_density",
        "remove_by_semantics",
        "remove_entity",
        "replace_entity",
        "add_entity",
        "change_relation",
        "change_scene_mode",
    ]
    parameters: dict[str, Any] = Field(default_factory=dict)


class RestoreVersionPayload(BaseModel):
    sourceVersionId: str = Field(min_length=8, max_length=64)
