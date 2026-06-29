from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from mcp_surveys.errors import RateLimitExceeded, SurveyForbidden, SurveyLocked, SurveyNotFound, SurveyValidationError
from mcp_surveys.models import AnswerIn
from mcp_surveys.service import SurveyService


def api_router(service: SurveyService) -> APIRouter:
    router = APIRouter(prefix="/api")

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
