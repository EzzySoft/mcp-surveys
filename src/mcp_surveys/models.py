from __future__ import annotations

import re
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


QuestionType = Literal[
    "single_choice",
    "multiple_choice",
    "ranking",
    "matching",
    "scale",
    "color_choice",
    "binary_tradeoff",
    "text",
]
ExportFormat = Literal["json", "markdown"]
_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Option(ApiModel):
    id: str | None = Field(default=None, description="Stable option id. Generated when omitted.")
    text: str = Field(min_length=1, max_length=MAX_OPTION_CHARS)
    color: str | None = Field(default=None, max_length=7, description="Optional #RRGGBB color for color_choice options.")

    @model_validator(mode="after")
    def validate_color(self) -> "Option":
        if self.color and not _COLOR_RE.fullmatch(self.color):
            raise ValueError("color must be a #RRGGBB hex color")
        return self


class Question(ApiModel):
    id: str | None = Field(default=None, description="Stable question id. Generated when omitted.")
    type: QuestionType
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS)
    required: bool = True
    options: list[Option] = Field(default_factory=list, max_length=MAX_OPTIONS_PER_LIST)
    left: list[Option] = Field(default_factory=list, max_length=MAX_OPTIONS_PER_LIST)
    right: list[Option] = Field(default_factory=list, max_length=MAX_OPTIONS_PER_LIST)
    allow_custom: bool = True
    min: int | None = None
    max: int | None = None
    step: int | None = Field(default=None, gt=0)
    min_label: str | None = Field(default=None, max_length=MAX_OPTION_CHARS)
    max_label: str | None = Field(default=None, max_length=MAX_OPTION_CHARS)
    theme: str | None = Field(default=None, max_length=24)
    left_color: str | None = Field(default=None, max_length=7)
    right_color: str | None = Field(default=None, max_length=7)

    @model_validator(mode="after")
    def validate_shape(self) -> "Question":
        if self.type in {"single_choice", "multiple_choice", "ranking", "color_choice"} and len(self.options) < 2:
            raise ValueError(f"{self.type} requires at least two options")
        if self.type == "matching" and (not self.left or not self.right):
            raise ValueError("matching requires left and right items")
        if self.type == "color_choice":
            if self.left or self.right:
                raise ValueError("color_choice questions cannot have left or right items")
            if any(not option.color for option in self.options):
                raise ValueError("color_choice options require color")
        if self.type == "binary_tradeoff" and (len(self.left) != 1 or len(self.right) != 1):
            raise ValueError("binary_tradeoff requires exactly one left and one right thesis")
        if self.type in {"scale", "text"} and (self.options or self.left or self.right):
            raise ValueError(f"{self.type} questions cannot have options, left, or right")
        if self.type == "binary_tradeoff" and self.options:
            raise ValueError("binary_tradeoff questions cannot have options")
        if self.type == "scale":
            self.min = 0 if self.min is None else self.min
            self.max = 100 if self.max is None else self.max
            self.step = 1 if self.step is None else self.step
            if self.min >= self.max:
                raise ValueError("scale min must be less than max")
        if self.type == "binary_tradeoff":
            self.min = -100 if self.min is None else self.min
            self.max = 100 if self.max is None else self.max
            self.step = 5 if self.step is None else self.step
            self.theme = self.theme or "signal"
            if self.min >= self.max:
                raise ValueError("binary_tradeoff min must be less than max")
            if self.theme not in {"signal", "mono", "calm", "custom"}:
                raise ValueError("binary_tradeoff theme must be signal, mono, calm, or custom")
            if self.theme == "custom" and (not self.left_color or not self.right_color):
                raise ValueError("binary_tradeoff custom theme requires left_color and right_color")
            if self.left_color and not _COLOR_RE.fullmatch(self.left_color):
                raise ValueError("left_color must be a #RRGGBB hex color")
            if self.right_color and not _COLOR_RE.fullmatch(self.right_color):
                raise ValueError("right_color must be a #RRGGBB hex color")
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


class ResultTokenRequest(ApiModel):
    result_token: str = Field(min_length=1)


class AgentSurveyPatch(SurveyPatch):
    result_token: str = Field(min_length=1)


class AgentExportRequest(ResultTokenRequest):
    format: ExportFormat = "markdown"


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


class SurveyStats(ApiModel):
    created: int = 0
    completed: int = 0
    answers_saved: int = 0
    rate_limit_hits: int = 0
