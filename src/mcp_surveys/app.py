from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Awaitable, Callable

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mcp_surveys.api import api_router, http_error
from mcp_surveys.config import WEB_DIR, load_settings
from mcp_surveys.errors import SurveyError
from mcp_surveys.mcp_server import build_mcp
from mcp_surveys.rate_limit import RedisRateLimiter
from mcp_surveys.service import SurveyService
from mcp_surveys.storage import RedisSurveyStore


class BodyTooLarge(Exception):
    pass


class MaxBodySizeMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int, protected_prefixes: tuple[str, ...]) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.protected_prefixes = protected_prefixes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not str(scope["path"]).startswith(self.protected_prefixes):
            await self.app(scope, receive, send)
            return

        seen = 0

        async def limited_receive() -> Message:
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.max_bytes:
                    raise BodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except BodyTooLarge:
            response = JSONResponse({"detail": f"request body is larger than {self.max_bytes} bytes"}, status_code=413)
            await response(scope, receive, send)


def _authorized(request: Request, token: str | None) -> bool:
    if token is None:
        return True
    return request.headers.get("authorization") == f"Bearer {token}"


def create_app() -> FastAPI:
    settings = load_settings()
    store = RedisSurveyStore(settings.redis_url, settings.redis_key_prefix)
    rate_limiter = RedisRateLimiter(
        settings.redis_url,
        settings.redis_key_prefix,
        settings.create_survey_rate_limit_per_hour,
    )
    service = SurveyService(
        store=store,
        public_base_url=settings.public_base_url,
        link_ttl_seconds=settings.survey_link_ttl_seconds,
        completed_ttl_seconds=settings.survey_completed_ttl_seconds,
        rate_limiter=rate_limiter,
        max_create_survey_bytes=settings.max_create_survey_bytes,
    )
    mcp = build_mcp(service)
    mcp_app = mcp.http_app(path="/")

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        async with mcp_app.lifespan(_):
            yield
        await store.close()
        await rate_limiter.close()

    app = FastAPI(title="mcp-surveys", lifespan=lifespan)
    app.state.service = service
    app.add_middleware(
        MaxBodySizeMiddleware,
        max_bytes=settings.max_create_survey_bytes + 8192,
        protected_prefixes=("/mcp", "/api"),
    )

    @app.middleware("http")
    async def protect_mcp(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if request.url.path.startswith("/mcp") and not _authorized(request, settings.mcp_auth_token):
            return JSONResponse({"detail": "missing or invalid bearer token"}, status_code=401)
        return await call_next(request)

    @app.exception_handler(SurveyError)
    async def survey_exception_handler(_: Request, error: SurveyError) -> JSONResponse:
        http = http_error(error)
        return JSONResponse({"detail": http.detail}, status_code=http.status_code)

    app.include_router(api_router(service))
    app.mount("/mcp", mcp_app)

    @app.get("/", include_in_schema=False)
    async def root():
        return {"ok": True, "service": "mcp-surveys"}

    @app.get("/health", include_in_schema=False)
    async def health():
        return {"ok": True}

    app.frontend("/", directory=str(WEB_DIR), fallback="index.html")

    return app


app = create_app()


def main() -> None:
    uvicorn.run("mcp_surveys.app:app", host="127.0.0.1", port=8000, reload=False)
