from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mcp_surveys.limits import (
    MAX_DESCRIPTION_CHARS,
    MAX_OPTION_CHARS,
    MAX_OPTIONS_PER_LIST,
    MAX_PROMPT_CHARS,
    MAX_SURVEY_QUESTIONS,
    MAX_TITLE_CHARS,
)


QuestionType = Literal["single_choice", "multiple_choice", "ranking", "matching", "text"]
ExportFormat = Literal["json", "markdown"]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Option(ApiModel):
    id: str | None = Field(default=None, description="Stable option id. Generated when omitted.")
    text: str = Field(min_length=1, max_length=MAX_OPTION_CHARS)


class Question(ApiModel):
    id: str | None = Field(default=None, description="Stable question id. Generated when omitted.")
    type: QuestionType
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS)
    required: bool = True
    options: list[Option] = Field(default_factory=list, max_length=MAX_OPTIONS_PER_LIST)
    left: list[Option] = Field(default_factory=list, max_length=MAX_OPTIONS_PER_LIST)
    right: list[Option] = Field(default_factory=list, max_length=MAX_OPTIONS_PER_LIST)
    allow_custom: bool = True

    @model_validator(mode="after")
    def validate_shape(self) -> "Question":
        if self.type in {"single_choice", "multiple_choice", "ranking"} and len(self.options) < 2:
            raise ValueError(f"{self.type} requires at least two options")
        if self.type == "matching" and (not self.left or not self.right):
            raise ValueError("matching requires left and right items")
        if self.type == "text" and (self.options or self.left or self.right):
            raise ValueError("text questions cannot have options, left, or right")
        return self


class AnswerIn(ApiModel):
    value: Any
    custom_options: dict[str, str] = Field(default_factory=dict)


class StoredAnswer(ApiModel):
    value: Any
    custom_options: dict[str, str] = Field(default_factory=dict)
    answered_at: datetime


class SurveyResponse(ApiModel):
    answers: dict[str, StoredAnswer] = Field(default_factory=dict)
    completed_at: datetime | None = None


class Survey(ApiModel):
    id: str
    result_token: str
    title: str = Field(min_length=1, max_length=MAX_TITLE_CHARS)
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION_CHARS)
    questions: list[Question] = Field(min_length=1, max_length=MAX_SURVEY_QUESTIONS)
    response: SurveyResponse = Field(default_factory=SurveyResponse)
    interactions: int = 0
    created_at: datetime
    expires_at: datetime


class CreateSurveyRequest(ApiModel):
    title: str = Field(min_length=1, max_length=MAX_TITLE_CHARS)
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION_CHARS)
    questions: list[Question] = Field(min_length=1, max_length=MAX_SURVEY_QUESTIONS)


class SurveyPatch(ApiModel):
    title: str | None = Field(default=None, min_length=1, max_length=MAX_TITLE_CHARS)
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION_CHARS)
    questions: list[Question] | None = Field(
        default=None,
        description="Replacement question list. Use edit_survey only for small edits.",
    )


class CreatedSurvey(ApiModel):
    survey_id: str
    public_url: str
    result_token: str
    expires_at: datetime
    expires_in_seconds: int


class PublicSurvey(ApiModel):
    id: str
    title: str
    description: str | None
    questions: list[Question]
    answers: dict[str, StoredAnswer]
    created_at: datetime
    expires_at: datetime
    completed_at: datetime | None
    answered_count: int
    total_questions: int
    required_answered_count: int
    total_required_questions: int


class SurveySummary(ApiModel):
    survey_id: str
    title: str
    status: Literal["active", "completed"]
    answered_count: int
    total_questions: int
    required_answered_count: int
    total_required_questions: int
    interactions: int
    created_at: datetime
    completed_at: datetime | None
    expires_at: datetime
    seconds_to_answer: float | None
    seconds_until_expiry: int


class QuestionAnswer(ApiModel):
    question_id: str
    prompt: str
    type: QuestionType
    answered: bool
    answer: Any = None
    answered_at: datetime | None = None


class SurveyAnswers(ApiModel):
    survey_id: str
    title: str
    summary: SurveySummary
    answers: list[QuestionAnswer]
