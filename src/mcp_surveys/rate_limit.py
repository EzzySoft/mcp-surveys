from __future__ import annotations

from typing import Protocol

from redis.asyncio import Redis

from mcp_surveys.errors import RateLimitExceeded


class RateLimiter(Protocol):
    async def check_create_survey(self, client_key: str) -> None:
        ...


class RedisRateLimiter:
    def __init__(self, redis_url: str, key_prefix: str, limit: int) -> None:
        self.redis_url = redis_url
        self.key_prefix = key_prefix
        self.limit = limit
        self._client: Redis | None = None

    @property
    def client(self) -> Redis:
        if self._client is None:
            self._client = Redis.from_url(self.redis_url, decode_responses=True)
        return self._client

    async def check_create_survey(self, client_key: str) -> None:
        key = f"{self.key_prefix}:rate:create_survey:{client_key}"
        count = await self.client.incr(key)
        if count == 1:
            await self.client.expire(key, 3600)
        if count > self.limit:
            raise RateLimitExceeded(f"create_survey limit exceeded: {self.limit} per hour")

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
