from __future__ import annotations

from typing import Protocol

from redis.asyncio import Redis

from mcp_surveys.errors import SurveyNotFound
from mcp_surveys.models import Survey, SurveyStats


class SurveyStore(Protocol):
    async def get(self, survey_id: str) -> Survey:
        ...

    async def save(self, survey: Survey, ttl_seconds: int) -> None:
        ...

    async def increment_stat(self, name: str) -> None:
        ...

    async def get_stats(self) -> SurveyStats:
        ...

    async def close(self) -> None:
        ...


class RedisSurveyStore:
    def __init__(self, redis_url: str, key_prefix: str) -> None:
        self.redis_url = redis_url
        self.key_prefix = key_prefix
        self._client: Redis | None = None

    @property
    def client(self) -> Redis:
        if self._client is None:
            self._client = Redis.from_url(self.redis_url, decode_responses=True)
        return self._client

    def _key(self, survey_id: str) -> str:
        return f"{self.key_prefix}:survey:{survey_id}"

    def _stats_key(self) -> str:
        return f"{self.key_prefix}:stats"

    async def get(self, survey_id: str) -> Survey:
        raw = await self.client.get(self._key(survey_id))
        if not raw:
            raise SurveyNotFound("survey is missing or expired")
        return Survey.model_validate_json(raw)

    async def save(self, survey: Survey, ttl_seconds: int) -> None:
        await self.client.set(self._key(survey.id), survey.model_dump_json(), ex=max(1, ttl_seconds))

    async def increment_stat(self, name: str) -> None:
        await self.client.hincrby(self._stats_key(), name, 1)

    async def get_stats(self) -> SurveyStats:
        raw = await self.client.hgetall(self._stats_key())
        return SurveyStats(**{key: int(value) for key, value in raw.items()})

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
