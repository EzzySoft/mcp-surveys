from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from mcp_surveys.http import client_key
from mcp_surveys.models import CreateSurveyRequest, ExportFormat, SurveyPatch
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
            "Prefer single_choice, multiple_choice, ranking, matching, or scale. Use scale for "
            "confidence, intensity, risk, fit, or other degree answers. Use text only when the "
            "answer cannot be represented by the other question types. Public links expire; "
            "never expose result_token to the respondent."
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

        return {
            "single_choice": {"value": "option_id", "custom_options": {"custom:id": "text"}},
            "multiple_choice": {"value": ["option_id"], "custom_options": {"custom:id": "text"}},
            "ranking": {"value": ["first_option_id", "second_option_id"]},
            "matching": {"left_item_id": "right_item_id"},
            "scale": {"value": 75, "fields": {"min": 0, "max": 100, "step": 5, "min_label": "Guess", "max_label": "Certain"}},
            "text": "Use only when other types cannot express the answer.",
            "limits": {
                "questions": 50,
                "options_per_list": 50,
                "create_payload_bytes": "configured by MAX_CREATE_SURVEY_BYTES",
            },
        }

    return mcp
