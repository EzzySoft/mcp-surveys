from __future__ import annotations

import pytest

from mcp_surveys.errors import RateLimitExceeded, SurveyValidationError
from mcp_surveys.models import AnswerIn, CreateSurveyRequest, Option, Question
from mcp_surveys.service import SurveyService


class MemoryStore:
    def __init__(self) -> None:
        self.items = {}
        self.ttls = {}

    async def get(self, survey_id):
        return self.items[survey_id]

    async def save(self, survey, ttl_seconds):
        self.items[survey.id] = survey
        self.ttls[survey.id] = ttl_seconds

    async def close(self):
        pass


class CountingLimiter:
    def __init__(self, limit):
        self.limit = limit
        self.count = 0

    async def check_create_survey(self, client_key):
        self.count += 1
        if self.count > self.limit:
            raise RateLimitExceeded("too many")


def make_request():
    return CreateSurveyRequest(
        title="Lunch",
        questions=[
            Question(
                type="single_choice",
                prompt="Where should we go?",
                options=[Option(text="Ramen"), Option(text="Pizza")],
            )
        ],
    )


@pytest.mark.asyncio
async def test_create_save_complete_and_read_answers():
    service = SurveyService(MemoryStore(), "https://survey.test", 3600, 10800)
    created = await service.create_survey(make_request(), client_key="127.0.0.1")
    survey = await service.get_public_survey(created.survey_id)
    question = survey.questions[0]

    await service.save_answer(created.survey_id, question.id, AnswerIn(value=question.options[0].id))
    public_after_save = await service.get_public_survey(created.survey_id)
    summary = await service.complete_survey(created.survey_id)
    answers = await service.get_answers(created.survey_id, created.result_token)

    assert created.public_url == f"https://survey.test/s/{created.survey_id}"
    assert public_after_save.answers[question.id].value == question.options[0].id
    assert summary.status == "completed"
    assert summary.answered_count == 1
    assert answers.answers[0].answer == {"id": question.options[0].id, "text": "Ramen"}


@pytest.mark.asyncio
async def test_rate_limit_blocks_create():
    service = SurveyService(MemoryStore(), "https://survey.test", 3600, 10800, rate_limiter=CountingLimiter(1))

    await service.create_survey(make_request(), client_key="127.0.0.1")

    with pytest.raises(RateLimitExceeded):
        await service.create_survey(make_request(), client_key="127.0.0.1")


@pytest.mark.asyncio
async def test_create_payload_size_limit():
    service = SurveyService(MemoryStore(), "https://survey.test", 3600, 10800, max_create_survey_bytes=10)

    with pytest.raises(SurveyValidationError):
        await service.create_survey(make_request(), client_key="127.0.0.1")
