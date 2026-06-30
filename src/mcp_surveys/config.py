from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
WEB_DIR = ROOT_DIR / "web"


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


@dataclass(frozen=True)
class Settings:
    redis_url: str
    public_base_url: str
    survey_link_ttl_seconds: int
    survey_completed_ttl_seconds: int
    redis_key_prefix: str
    create_survey_rate_limit_per_hour: int
    max_create_survey_bytes: int


def load_settings() -> Settings:
    return Settings(
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        public_base_url=os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/"),
        survey_link_ttl_seconds=_int_env("SURVEY_LINK_TTL_SECONDS", 3600),
        survey_completed_ttl_seconds=_int_env("SURVEY_COMPLETED_TTL_SECONDS", 10800),
        redis_key_prefix=os.getenv("REDIS_KEY_PREFIX", "mcp-surveys"),
        create_survey_rate_limit_per_hour=_int_env("CREATE_SURVEY_RATE_LIMIT_PER_HOUR", 60),
        max_create_survey_bytes=_int_env("MAX_CREATE_SURVEY_BYTES", 128 * 1024),
    )
