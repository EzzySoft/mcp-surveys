from __future__ import annotations

import pytest
from pydantic import ValidationError

from mcp_surveys.errors import RateLimitExceeded, SurveyValidationError
from mcp_surveys.models import AnswerIn, CreateSurveyRequest, Option, Question
from mcp_surveys.service import SurveyService


class MemoryStore:
    def __init__(self) -> None:
        self.items = {}
        self.ttls = {}
        self.stats = {}

    async def get(self, survey_id):
        return self.items[survey_id]

    async def save(self, survey, ttl_seconds):
        self.items[survey.id] = survey
        self.ttls[survey.id] = ttl_seconds

    async def increment_stat(self, name):
        self.stats[name] = self.stats.get(name, 0) + 1

    async def get_stats(self):
        from mcp_surveys.models import SurveyStats

        return SurveyStats(**self.stats)

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
    store = MemoryStore()
    service = SurveyService(store, "https://survey.test", 3600, 10800)
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
    stats = await service.get_stats()
    assert stats.created == 1
    assert stats.answers_saved == 1
    assert stats.completed == 1


@pytest.mark.asyncio
async def test_scale_question_accepts_number_in_range():
    service = SurveyService(MemoryStore(), "https://survey.test", 3600, 10800)
    created = await service.create_survey(
        CreateSurveyRequest(
            title="Confidence",
            questions=[
                Question(
                    type="scale",
                    prompt="How confident are you?",
                    min=0,
                    max=100,
                    step=5,
                    min_label="Guess",
                    max_label="Certain",
                )
            ],
        ),
        client_key="127.0.0.1",
    )

    await service.save_answer(created.survey_id, "how-confident-are-you", AnswerIn(value=75))
    answers = await service.get_answers(created.survey_id, created.result_token)

    assert answers.answers[0].answer == 75


@pytest.mark.asyncio
async def test_color_choice_returns_selected_color():
    service = SurveyService(MemoryStore(), "https://survey.test", 3600, 10800)
    created = await service.create_survey(
        CreateSurveyRequest(
            title="Accent",
            questions=[
                Question(
                    id="accent-color",
                    type="color_choice",
                    prompt="Which accent color should we use?",
                    options=[
                        Option(id="ocean", text="Ocean blue", color="#2563eb"),
                        Option(id="forest", text="Forest green", color="#16a34a"),
                    ],
                )
            ],
        ),
        client_key="127.0.0.1",
    )

    await service.save_answer(created.survey_id, "accent-color", AnswerIn(value="forest"))
    answers = await service.get_answers(created.survey_id, created.result_token)

    assert answers.answers[0].answer == {"id": "forest", "text": "Forest green", "color": "#16a34a"}


def test_color_choice_requires_hex_colors():
    with pytest.raises(ValidationError, match="color must be a #RRGGBB hex color"):
        Question(
            id="accent-color",
            type="color_choice",
            prompt="Which accent color should we use?",
            options=[
                Option(id="ocean", text="Ocean blue", color="blue"),
                Option(id="forest", text="Forest green", color="#16a34a"),
            ],
        )


@pytest.mark.asyncio
async def test_binary_tradeoff_returns_lean_metadata():
    service = SurveyService(MemoryStore(), "https://survey.test", 3600, 10800)
    created = await service.create_survey(
        CreateSurveyRequest(
            title="Release lean",
            questions=[
                Question(
                    id="release-lean",
                    type="binary_tradeoff",
                    prompt="Where should this release lean?",
                    left=[Option(id="ship", text="Ship this week")],
                    right=[Option(id="safe", text="Reduce launch risk")],
                    theme="calm",
                )
            ],
        ),
        client_key="127.0.0.1",
    )

    await service.save_answer(created.survey_id, "release-lean", AnswerIn(value=35))
    answers = await service.get_answers(created.survey_id, created.result_token)

    assert answers.answers[0].answer == {
        "value": 35,
        "lean": "right",
        "strength": "clear",
        "left": {"id": "ship", "text": "Ship this week"},
        "right": {"id": "safe", "text": "Reduce launch risk"},
    }


def test_binary_tradeoff_custom_theme_requires_colors():
    with pytest.raises(ValidationError, match="custom theme requires left_color and right_color"):
        Question(
            id="release-lean",
            type="binary_tradeoff",
            prompt="Where should this release lean?",
            left=[Option(id="ship", text="Ship this week")],
            right=[Option(id="safe", text="Reduce launch risk")],
            theme="custom",
        )


@pytest.mark.asyncio
async def test_rate_limit_blocks_create():
    store = MemoryStore()
    service = SurveyService(store, "https://survey.test", 3600, 10800, rate_limiter=CountingLimiter(1))

    await service.create_survey(make_request(), client_key="127.0.0.1")

    with pytest.raises(RateLimitExceeded):
        await service.create_survey(make_request(), client_key="127.0.0.1")
    assert (await service.get_stats()).rate_limit_hits == 1


@pytest.mark.asyncio
async def test_create_payload_size_limit():
    service = SurveyService(MemoryStore(), "https://survey.test", 3600, 10800, max_create_survey_bytes=10)

    with pytest.raises(SurveyValidationError):
        await service.create_survey(make_request(), client_key="127.0.0.1")
