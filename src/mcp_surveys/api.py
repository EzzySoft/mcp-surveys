from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from pydantic import ValidationError

from mcp_surveys.errors import RateLimitExceeded, SurveyForbidden, SurveyLocked, SurveyNotFound, SurveyValidationError
from mcp_surveys.http import client_key
from mcp_surveys.models import (
    AgentExportRequest,
    AgentSurveyPatch,
    AnswerIn,
    CreateEncryptedSurveyRequest,
    CreateSurveyRequest,
    ResultTokenRequest,
    SurveyPatch,
)
from mcp_surveys.schema import question_schema
from mcp_surveys.service import SurveyService

MIN_AGENT_VERSION = "0.4.0"
CRITICAL_UPGRADE_MESSAGE = (
    "CRITICAL UPGRADE REQUIRED: this local mcp-surveys client/MCP integration is too old for the secure CLI-first protocol. "
    "Update now with `uvx --refresh-package mcp-surveys-cli mcp-surveys-cli ...` and recreate the survey. "
    "Secure E2EE surveys require mcp-surveys-cli >= 0.4.0; legacy MCP/plaintext clients are blocked from agent API calls."
)


def _version_tuple(value: str) -> tuple[int, ...] | None:
    parts: list[int] = []
    for chunk in value.split("."):
        digits = ""
        for char in chunk:
            if char.isdigit():
                digits += char
            else:
                break
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts) if parts else None


def _current_agent_version(value: str) -> bool:
    parsed = _version_tuple(value)
    minimum = _version_tuple(MIN_AGENT_VERSION)
    return parsed is not None and minimum is not None and parsed >= minimum


def _create_request(payload: dict[str, Any]) -> CreateSurveyRequest | CreateEncryptedSurveyRequest:
    model = CreateEncryptedSurveyRequest if "crypto" in payload else CreateSurveyRequest
    try:
        return model.model_validate(payload)
    except ValidationError as error:
        raise SurveyValidationError(str(error)) from error


def _client_info(request: Request, payload: dict[str, Any] | None = None, endpoint: str | None = None) -> dict[str, str]:
    mode = request.headers.get("x-mcp-surveys-mode") or ("e2ee_full" if payload and "crypto" in payload else "plaintext")
    info = {
        "source": request.headers.get("x-mcp-surveys-source", "agent"),
        "client": request.headers.get("x-mcp-surveys-client", "legacy-or-unknown"),
        "version": request.headers.get("x-mcp-surveys-version", "unknown"),
        "mode": mode,
    }
    if endpoint:
        info["endpoint"] = endpoint
    return info


def _public_client_info(request: Request) -> dict[str, str]:
    return {
        "source": request.headers.get("x-mcp-surveys-source", "web"),
        "client": request.headers.get("x-mcp-surveys-client", "web"),
        "version": request.headers.get("x-mcp-surveys-version", "builtin"),
    }


async def _require_current_agent(service: SurveyService, request: Request, endpoint: str, payload: dict[str, Any] | None = None) -> dict[str, str]:
    info = _client_info(request, payload, endpoint)
    await service.record_event("agent_requests", info)
    if not _current_agent_version(info["version"]):
        reason = "missing-version" if info["version"] == "unknown" else "too-old"
        await service.record_event("upgrade_required", {**info, "reason": reason})
        raise HTTPException(status.HTTP_426_UPGRADE_REQUIRED, CRITICAL_UPGRADE_MESSAGE)
    return info


def api_router(service: SurveyService) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.post("/agent/surveys")
    async def create_agent_survey(payload: dict[str, Any], request: Request):
        info = await _require_current_agent(service, request, "create", payload)
        return await service.create_survey(_create_request(payload), client_key=client_key(request), client_info=info)

    @router.patch("/agent/surveys/{survey_id}")
    async def edit_agent_survey(survey_id: str, payload: AgentSurveyPatch, request: Request):
        await _require_current_agent(service, request, "edit")
        patch = SurveyPatch(title=payload.title, description=payload.description, questions=payload.questions)
        return await service.edit_survey(survey_id, payload.result_token, patch)

    @router.post("/agent/surveys/{survey_id}/state")
    async def get_agent_survey(survey_id: str, payload: ResultTokenRequest, request: Request):
        await _require_current_agent(service, request, "state")
        return await service.get_survey(survey_id, payload.result_token)

    @router.post("/agent/surveys/{survey_id}/summary")
    async def get_agent_summary(survey_id: str, payload: ResultTokenRequest, request: Request):
        await _require_current_agent(service, request, "summary")
        return await service.get_summary(survey_id, payload.result_token)

    @router.post("/agent/surveys/{survey_id}/answers")
    async def get_agent_answers(survey_id: str, payload: ResultTokenRequest, request: Request):
        await _require_current_agent(service, request, "answers")
        return await service.get_answers(survey_id, payload.result_token)

    @router.post("/agent/surveys/{survey_id}/answers/{question_id}")
    async def get_agent_question_answer(survey_id: str, question_id: str, payload: ResultTokenRequest, request: Request):
        await _require_current_agent(service, request, "question")
        return await service.get_question_answer(survey_id, payload.result_token, question_id)

    @router.post("/agent/surveys/{survey_id}/export")
    async def export_agent_answers(survey_id: str, payload: AgentExportRequest, request: Request):
        await _require_current_agent(service, request, "export")
        return PlainTextResponse(await service.export_answers(survey_id, payload.result_token, payload.format))

    @router.get("/agent/question-schema")
    async def get_question_schema(request: Request):
        await _require_current_agent(service, request, "schema")
        return question_schema()

    @router.get("/agent/stats")
    async def get_agent_stats(request: Request):
        await _require_current_agent(service, request, "stats")
        return await service.get_stats()

    @router.get("/metrics")
    async def get_public_metrics():
        return await service.get_stats()

    @router.get("/surveys/{survey_id}")
    async def get_survey(survey_id: str, request: Request):
        return await service.get_public_survey(survey_id, client_info=_public_client_info(request))

    @router.put("/surveys/{survey_id}/answers/{question_id}")
    async def save_answer(survey_id: str, question_id: str, answer: AnswerIn, request: Request):
        return await service.save_answer(survey_id, question_id, answer, client_info=_public_client_info(request))

    @router.post("/surveys/{survey_id}/complete")
    async def complete_survey(survey_id: str, request: Request):
        return await service.complete_survey(survey_id, client_info=_public_client_info(request))

    @router.get("/healthz")
    async def healthz():
        return {"ok": True}

    return router


def http_error(error: Exception) -> HTTPException:
    if isinstance(error, SurveyNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(error))
    if isinstance(error, SurveyForbidden):
        return HTTPException(status.HTTP_403_FORBIDDEN, str(error))
    if isinstance(error, SurveyLocked):
        return HTTPException(status.HTTP_409_CONFLICT, str(error))
    if isinstance(error, RateLimitExceeded):
        return HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(error))
    if isinstance(error, SurveyValidationError):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error))
    return HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "internal server error")
