from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import PlainTextResponse

from mcp_surveys.errors import RateLimitExceeded, SurveyForbidden, SurveyLocked, SurveyNotFound, SurveyValidationError
from mcp_surveys.http import client_key
from mcp_surveys.models import (
    AgentExportRequest,
    AgentSurveyPatch,
    AnswerIn,
    CreateSurveyRequest,
    ResultTokenRequest,
    SurveyPatch,
)
from mcp_surveys.schema import question_schema
from mcp_surveys.service import SurveyService


def api_router(service: SurveyService) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.post("/agent/surveys")
    async def create_agent_survey(payload: CreateSurveyRequest, request: Request):
        return await service.create_survey(payload, client_key=client_key(request))

    @router.patch("/agent/surveys/{survey_id}")
    async def edit_agent_survey(survey_id: str, payload: AgentSurveyPatch):
        patch = SurveyPatch(title=payload.title, description=payload.description, questions=payload.questions)
        return await service.edit_survey(survey_id, payload.result_token, patch)

    @router.post("/agent/surveys/{survey_id}/state")
    async def get_agent_survey(survey_id: str, payload: ResultTokenRequest):
        return await service.get_survey(survey_id, payload.result_token)

    @router.post("/agent/surveys/{survey_id}/summary")
    async def get_agent_summary(survey_id: str, payload: ResultTokenRequest):
        return await service.get_summary(survey_id, payload.result_token)

    @router.post("/agent/surveys/{survey_id}/answers")
    async def get_agent_answers(survey_id: str, payload: ResultTokenRequest):
        return await service.get_answers(survey_id, payload.result_token)

    @router.post("/agent/surveys/{survey_id}/answers/{question_id}")
    async def get_agent_question_answer(survey_id: str, question_id: str, payload: ResultTokenRequest):
        return await service.get_question_answer(survey_id, payload.result_token, question_id)

    @router.post("/agent/surveys/{survey_id}/export")
    async def export_agent_answers(survey_id: str, payload: AgentExportRequest):
        return PlainTextResponse(await service.export_answers(survey_id, payload.result_token, payload.format))

    @router.get("/agent/question-schema")
    async def get_question_schema():
        return question_schema()

    @router.get("/surveys/{survey_id}")
    async def get_survey(survey_id: str):
        return await service.get_public_survey(survey_id)

    @router.put("/surveys/{survey_id}/answers/{question_id}")
    async def save_answer(survey_id: str, question_id: str, answer: AnswerIn):
        return await service.save_answer(survey_id, question_id, answer)

    @router.post("/surveys/{survey_id}/complete")
    async def complete_survey(survey_id: str):
        return await service.complete_survey(survey_id)

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
