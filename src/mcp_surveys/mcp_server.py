from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from mcp_surveys.http import client_key
from mcp_surveys.models import CreateSurveyRequest, ExportFormat, SurveyPatch
from mcp_surveys.schema import question_schema as survey_question_schema
from mcp_surveys.service import SurveyService

try:
    from fastmcp.server.dependencies import get_http_request
except Exception:  # pragma: no cover - old FastMCP fallback
    get_http_request = None


def _mcp_client_key() -> str:
    if get_http_request is None:
        return "mcp"
    try:
        return client_key(get_http_request())
    except Exception:
        return "mcp"


def build_mcp(service: SurveyService) -> FastMCP:
    mcp = FastMCP(
        "mcp-surveys",
        instructions=(
            "Create short-lived, tappable surveys for humans when plain chat would be clumsy. "
            "Prefer single_choice, multiple_choice, ranking, matching, scale, or binary_tradeoff. "
            "Use scale for confidence, intensity, risk, fit, or other degree answers. Use "
            "binary_tradeoff when two competing theses are both valid and the human should place "
            "a marker between A and B. Use text only when the answer cannot be represented by the "
            "other question types. Public links expire; never expose result_token to the respondent."
        ),
    )

    @mcp.tool
    async def create_survey(payload: CreateSurveyRequest) -> dict[str, Any]:
        """Create an ephemeral survey and return a public URL plus private result token."""

        result = await service.create_survey(payload, client_key=_mcp_client_key())
        return result.model_dump(mode="json")

    @mcp.tool
    async def edit_survey(survey_id: str, result_token: str, patch: SurveyPatch) -> dict[str, Any]:
        """Edit a small part of an active survey. Create a new survey for substantial rewrites."""

        result = await service.edit_survey(survey_id, result_token, patch)
        return result.model_dump(mode="json")

    @mcp.tool
    async def get_survey(survey_id: str, result_token: str) -> dict[str, Any]:
        """Return the current survey spec and progress."""

        result = await service.get_survey(survey_id, result_token)
        return result.model_dump(mode="json")

    @mcp.tool
    async def get_survey_summary(survey_id: str, result_token: str) -> dict[str, Any]:
        """Return completion state, progress counts, timing, and remaining storage time."""

        result = await service.get_summary(survey_id, result_token)
        return result.model_dump(mode="json")

    @mcp.tool
    async def get_survey_answers(survey_id: str, result_token: str) -> dict[str, Any]:
        """Return all survey answers with option labels resolved."""

        result = await service.get_answers(survey_id, result_token)
        return result.model_dump(mode="json")

    @mcp.tool
    async def get_question_answer(survey_id: str, result_token: str, question_id: str) -> dict[str, Any]:
        """Return one answer by question id."""

        result = await service.get_question_answer(survey_id, result_token, question_id)
        return result.model_dump(mode="json")

    @mcp.tool
    async def get_survey_export(survey_id: str, result_token: str, format: ExportFormat = "markdown") -> str:
        """Return answers as compact Markdown or JSON."""

        return await service.export_answers(survey_id, result_token, format)

    @mcp.tool
    async def question_schema() -> dict[str, Any]:
        """Return the supported question types and payload shapes."""

        return survey_question_schema()

    return mcp
