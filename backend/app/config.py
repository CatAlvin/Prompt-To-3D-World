from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "development"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173"

    llm_provider: str = "kimi"
    moonshot_api_key: str = Field(default="", repr=False)
    kimi_base_url: str = "https://api.moonshot.cn/v1"
    kimi_model: str = "kimi-k3"
    kimi_reasoning_effort: str = "low"
    llm_timeout_seconds: float = 240
    llm_max_output_tokens: int = 12000
    generation_timeout_seconds: float = 360
    v2_inline_worker: bool = True

    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = Field(default="", repr=False)
    mysql_database: str = "prompt_to_3d_world"
    database_url_override: str | None = None

    anonymous_retention_days: int = 30
    generation_rate_limit_per_minute: int = 10

    @field_validator("kimi_reasoning_effort")
    @classmethod
    def validate_reasoning_effort(cls, value: str) -> str:
        if value not in {"low", "high", "max"}:
            raise ValueError("KIMI_REASONING_EFFORT must be low, high, or max")
        return value

    @field_validator("mysql_database")
    @classmethod
    def validate_database_name(cls, value: str) -> str:
        if not value.replace("_", "").isalnum():
            raise ValueError("MYSQL_DATABASE may contain only letters, numbers, and underscores")
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def database_url(self) -> str:
        if self.database_url_override:
            return self.database_url_override
        password = quote_plus(self.mysql_password)
        username = quote_plus(self.mysql_user)
        return (
            f"mysql+asyncmy://{username}:{password}@{self.mysql_host}:"
            f"{self.mysql_port}/{self.mysql_database}?charset=utf8mb4"
        )

    @property
    def sync_database_url(self) -> str:
        if self.database_url_override:
            return self.database_url_override.replace("+aiosqlite", "").replace("+asyncmy", "+pymysql")
        password = quote_plus(self.mysql_password)
        username = quote_plus(self.mysql_user)
        return (
            f"mysql+pymysql://{username}:{password}@{self.mysql_host}:"
            f"{self.mysql_port}/{self.mysql_database}?charset=utf8mb4"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
