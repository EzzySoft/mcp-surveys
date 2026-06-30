from __future__ import annotations

import json
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from mcp_surveys.errors import RateLimitExceeded, SurveyForbidden, SurveyLocked, SurveyValidationError
from mcp_surveys.limits import MAX_CUSTOM_OPTIONS, MAX_TEXT_ANSWER_CHARS
from mcp_surveys.models import (
    AnswerIn,
    CreatedSurvey,
    CreateSurveyRequest,
    ExportFormat,
    Option,
    PublicSurvey,
    Question,
    QuestionAnswer,
    StoredAnswer,
    Survey,
    SurveyAnswers,
    SurveyPatch,
    SurveyResponse,
    SurveyStats,
    SurveySummary,
)
from mcp_surveys.storage import SurveyStore


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def now_utc() -> datetime:
    return datetime.now(UTC)


def _token() -> str:
    return secrets.token_urlsafe(24)


def _slug(value: str, fallback: str) -> str:
    slug = _SLUG_RE.sub("-", value.lower()).strip("-")
    return slug[:48] or fallback


def _unique(value: str, used: set[str], fallback: str) -> str:
    base = _slug(value, fallback)
    candidate = base
    index = 2
    while candidate in used:
        candidate = f"{base}-{index}"
        index += 1
    used.add(candidate)
    return candidate


def _normalize_options(options: list[Option], prefix: str) -> list[Option]:
    used: set[str] = set()
    normalized: list[Option] = []
    for index, option in enumerate(options, start=1):
        option_id = _unique(option.id or option.text, used, f"{prefix}{index}")
        normalized.append(option.model_copy(update={"id": option_id}))
    return normalized


def normalize_questions(questions: list[Question]) -> list[Question]:
    used: set[str] = set()
    normalized: list[Question] = []
    for index, question in enumerate(questions, start=1):
        question_id = _unique(question.id or question.prompt, used, f"q{index}")
        normalized.append(
            question.model_copy(
                update={
                    "id": question_id,
                    "options": _normalize_options(question.options, "o"),
                    "left": _normalize_options(question.left, "l"),
                    "right": _normalize_options(question.right, "r"),
                },
            )
        )
    return normalized


class SurveyService:
    def __init__(
        self,
        store: SurveyStore,
        public_base_url: str,
        link_ttl_seconds: int,
        completed_ttl_seconds: int,
        rate_limiter: Any | None = None,
        max_create_survey_bytes: int = 128 * 1024,
    ) -> None:
        self.store = store
        self.public_base_url = public_base_url.rstrip("/")
        self.link_ttl_seconds = link_ttl_seconds
        self.completed_ttl_seconds = completed_ttl_seconds
        self.rate_limiter = rate_limiter
        self.max_create_survey_bytes = max_create_survey_bytes

    async def create_survey(self, request: CreateSurveyRequest, client_key: str = "unknown") -> CreatedSurvey:
        if len(request.model_dump_json().encode("utf-8")) > self.max_create_survey_bytes:
            raise SurveyValidationError(f"create_survey payload is larger than {self.max_create_survey_bytes} bytes")
        if self.rate_limiter is not None:
            try:
                await self.rate_limiter.check_create_survey(client_key)
            except RateLimitExceeded:
                await self.store.increment_stat("rate_limit_hits")
                raise
        created_at = now_utc()
        survey = Survey(
            id=_token(),
            result_token=_token(),
            title=request.title,
            description=request.description,
            questions=normalize_questions(request.questions),
            response=SurveyResponse(),
            created_at=created_at,
            expires_at=created_at + timedelta(seconds=self.link_ttl_seconds),
        )
        await self.store.save(survey, self.link_ttl_seconds)
        await self.store.increment_stat("created")
        return CreatedSurvey(
            survey_id=survey.id,
            public_url=f"{self.public_base_url}/s/{survey.id}",
            result_token=survey.result_token,
            expires_at=survey.expires_at,
            expires_in_seconds=self.link_ttl_seconds,
        )

    async def get_public_survey(self, survey_id: str) -> PublicSurvey:
        survey = await self.store.get(survey_id)
        return self._public_survey(survey)

    async def save_answer(self, survey_id: str, question_id: str, answer: AnswerIn) -> PublicSurvey:
        survey = await self.store.get(survey_id)
        if survey.response.completed_at:
            raise SurveyLocked("survey is already completed")
        question = self._question(survey, question_id)
        self._validate_answer(question, answer)
        survey.response.answers[question_id] = StoredAnswer(
            value=answer.value,
            custom_options=answer.custom_options,
            answered_at=now_utc(),
        )
        survey.interactions += 1
        await self.store.save(survey, self._ttl_for(survey))
        await self.store.increment_stat("answers_saved")
        return self._public_survey(survey)

    async def complete_survey(self, survey_id: str) -> SurveySummary:
        survey = await self.store.get(survey_id)
        if not survey.response.completed_at:
            completed_at = now_utc()
            survey.response.completed_at = completed_at
            survey.expires_at = completed_at + timedelta(seconds=self.completed_ttl_seconds)
            await self.store.save(survey, self.completed_ttl_seconds)
            await self.store.increment_stat("completed")
        return self._summary(survey)

    async def edit_survey(self, survey_id: str, result_token: str, patch: SurveyPatch) -> PublicSurvey:
        survey = await self._get_for_agent(survey_id, result_token)
        if survey.response.completed_at:
            raise SurveyLocked("completed surveys cannot be edited")
        if patch.title is not None:
            survey.title = patch.title
        if patch.description is not None:
            survey.description = patch.description
        if patch.questions is not None:
            survey.questions = normalize_questions(patch.questions)
            survey.response.answers = self._preserve_valid_answers(survey)
        await self.store.save(survey, self._ttl_for(survey))
        return self._public_survey(survey)

    async def get_survey(self, survey_id: str, result_token: str) -> PublicSurvey:
        return self._public_survey(await self._get_for_agent(survey_id, result_token))

    async def get_summary(self, survey_id: str, result_token: str) -> SurveySummary:
        return self._summary(await self._get_for_agent(survey_id, result_token))

    async def get_answers(self, survey_id: str, result_token: str) -> SurveyAnswers:
        survey = await self._get_for_agent(survey_id, result_token)
        return SurveyAnswers(
            survey_id=survey.id,
            title=survey.title,
            summary=self._summary(survey),
            answers=[self._question_answer(question, survey.response.answers.get(question.id or "")) for question in survey.questions],
        )

    async def get_question_answer(self, survey_id: str, result_token: str, question_id: str) -> QuestionAnswer:
        survey = await self._get_for_agent(survey_id, result_token)
        question = self._question(survey, question_id)
        return self._question_answer(question, survey.response.answers.get(question_id))

    async def export_answers(self, survey_id: str, result_token: str, fmt: ExportFormat) -> str:
        answers = await self.get_answers(survey_id, result_token)
        if fmt == "json":
            return answers.model_dump_json(indent=2)
        lines = [f"# {answers.title}", "", f"Status: {answers.summary.status}", ""]
        for answer in answers.answers:
            lines.append(f"## {answer.prompt}")
            lines.append(self._markdown_answer(answer.answer) if answer.answered else "_Unanswered_")
            lines.append("")
        return "\n".join(lines).strip() + "\n"

    async def get_stats(self) -> SurveyStats:
        return await self.store.get_stats()

    async def _get_for_agent(self, survey_id: str, result_token: str) -> Survey:
        survey = await self.store.get(survey_id)
        if not secrets.compare_digest(survey.result_token, result_token):
            raise SurveyForbidden("invalid result token")
        return survey

    def _preserve_valid_answers(self, survey: Survey) -> dict[str, StoredAnswer]:
        questions = {question.id: question for question in survey.questions}
        kept: dict[str, StoredAnswer] = {}
        for question_id, answer in survey.response.answers.items():
            question = questions.get(question_id)
            if question is None:
                continue
            try:
                self._validate_answer(question, AnswerIn(value=answer.value, custom_options=answer.custom_options))
            except SurveyValidationError:
                continue
            kept[question_id] = answer
        return kept

    def _question(self, survey: Survey, question_id: str) -> Question:
        for question in survey.questions:
            if question.id == question_id:
                return question
        raise SurveyValidationError(f"unknown question id: {question_id}")

    def _validate_answer(self, question: Question, answer: AnswerIn) -> None:
        custom_options = self._validated_custom_options(question, answer.custom_options)
        if question.type == "single_choice":
            self._validate_choice_value(answer.value, self._option_ids(question) | custom_options, "single_choice")
        elif question.type == "color_choice":
            self._validate_choice_value(answer.value, self._option_ids(question), "color_choice")
        elif question.type == "multiple_choice":
            self._validate_list_value(answer.value, self._option_ids(question) | custom_options, "multiple_choice")
        elif question.type == "ranking":
            self._validate_list_value(answer.value, self._option_ids(question) | custom_options, "ranking")
            if set(answer.value) != self._option_ids(question) | custom_options:
                raise SurveyValidationError("ranking answer must include every option exactly once")
        elif question.type == "matching":
            self._validate_matching(answer.value, question)
        elif question.type in {"scale", "binary_tradeoff"}:
            self._validate_scale(answer.value, question)
        elif question.type == "text":
            if not isinstance(answer.value, str) or len(answer.value) > MAX_TEXT_ANSWER_CHARS:
                raise SurveyValidationError(f"text answers must be strings up to {MAX_TEXT_ANSWER_CHARS} characters")

    def _validated_custom_options(self, question: Question, options: dict[str, str]) -> set[str]:
        if options and not question.allow_custom:
            raise SurveyValidationError("custom options are disabled for this question")
        if question.type not in {"single_choice", "multiple_choice", "ranking"} and options:
            raise SurveyValidationError("custom options are only supported for choice and ranking questions")
        if len(options) > MAX_CUSTOM_OPTIONS:
            raise SurveyValidationError("too many custom options")
        for option_id, text in options.items():
            if not option_id.startswith("custom:") or not text.strip() or len(text) > 300:
                raise SurveyValidationError("custom options must use custom:* ids and non-empty text")
        return set(options)

    @staticmethod
    def _option_ids(question: Question) -> set[str]:
        return {option.id or "" for option in question.options}

    @staticmethod
    def _validate_choice_value(value: Any, allowed: set[str], label: str) -> None:
        if not isinstance(value, str) or value not in allowed:
            raise SurveyValidationError(f"{label} answer must be one allowed option id")

    @staticmethod
    def _validate_list_value(value: Any, allowed: set[str], label: str) -> None:
        if not isinstance(value, list) or not value:
            raise SurveyValidationError(f"{label} answer must be a non-empty list")
        if len(value) != len(set(value)) or any(not isinstance(item, str) or item not in allowed for item in value):
            raise SurveyValidationError(f"{label} answer contains unknown or duplicate options")

    @staticmethod
    def _validate_matching(value: Any, question: Question) -> None:
        left_ids = {item.id or "" for item in question.left}
        right_ids = {item.id or "" for item in question.right}
        if not isinstance(value, dict):
            raise SurveyValidationError("matching answer must be a left_id -> right_id object")
        if set(value) - left_ids or any(item not in right_ids for item in value.values()):
            raise SurveyValidationError("matching answer contains unknown item ids")

    @staticmethod
    def _validate_scale(value: Any, question: Question) -> None:
        scale_min = question.min if question.min is not None else 0
        scale_max = question.max if question.max is not None else 100
        step = question.step if question.step is not None else 1
        if isinstance(value, bool) or not isinstance(value, int):
            raise SurveyValidationError("scale answer must be an integer")
        if value < scale_min or value > scale_max or (value - scale_min) % step:
            raise SurveyValidationError("scale answer is outside the allowed range")

    def _ttl_for(self, survey: Survey) -> int:
        return max(1, int((survey.expires_at - now_utc()).total_seconds()))

    def _public_survey(self, survey: Survey) -> PublicSurvey:
        answered, required_answered = self._counts(survey)
        return PublicSurvey(
            id=survey.id,
            title=survey.title,
            description=survey.description,
            questions=survey.questions,
            answers=survey.response.answers,
            created_at=survey.created_at,
            expires_at=survey.expires_at,
            completed_at=survey.response.completed_at,
            answered_count=answered,
            total_questions=len(survey.questions),
            required_answered_count=required_answered,
            total_required_questions=sum(1 for question in survey.questions if question.required),
        )

    def _summary(self, survey: Survey) -> SurveySummary:
        answered, required_answered = self._counts(survey)
        completed_at = survey.response.completed_at
        return SurveySummary(
            survey_id=survey.id,
            title=survey.title,
            status="completed" if completed_at else "active",
            answered_count=answered,
            total_questions=len(survey.questions),
            required_answered_count=required_answered,
            total_required_questions=sum(1 for question in survey.questions if question.required),
            interactions=survey.interactions,
            created_at=survey.created_at,
            completed_at=completed_at,
            expires_at=survey.expires_at,
            seconds_to_answer=(completed_at - survey.created_at).total_seconds() if completed_at else None,
            seconds_until_expiry=max(0, int((survey.expires_at - now_utc()).total_seconds())),
        )

    def _counts(self, survey: Survey) -> tuple[int, int]:
        answered = 0
        required_answered = 0
        for question in survey.questions:
            answer = survey.response.answers.get(question.id or "")
            if answer and self._answer_has_value(answer.value):
                answered += 1
                if question.required:
                    required_answered += 1
        return answered, required_answered

    @staticmethod
    def _answer_has_value(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (list, dict)):
            return bool(value)
        return True

    def _question_answer(self, question: Question, answer: StoredAnswer | None) -> QuestionAnswer:
        if answer is None:
            return QuestionAnswer(question_id=question.id or "", prompt=question.prompt, type=question.type, answered=False)
        return QuestionAnswer(
            question_id=question.id or "",
            prompt=question.prompt,
            type=question.type,
            answered=True,
            answer=self._resolve_answer(question, answer),
            answered_at=answer.answered_at,
        )

    def _resolve_answer(self, question: Question, answer: StoredAnswer) -> Any:
        labels = {option.id: option.text for option in question.options}
        colors = {option.id: option.color for option in question.options if option.color}
        labels.update({item.id: item.text for item in question.left})
        labels.update({item.id: item.text for item in question.right})
        labels.update(answer.custom_options)
        if question.type == "single_choice":
            return {"id": answer.value, "text": labels.get(answer.value, answer.value)}
        if question.type == "color_choice":
            return {"id": answer.value, "text": labels.get(answer.value, answer.value), "color": colors.get(answer.value)}
        if question.type in {"multiple_choice", "ranking"}:
            return [{"id": item, "text": labels.get(item, item)} for item in answer.value]
        if question.type == "matching":
            return [
                {
                    "left_id": left_id,
                    "left_text": labels.get(left_id, left_id),
                    "right_id": right_id,
                    "right_text": labels.get(right_id, right_id),
                }
                for left_id, right_id in answer.value.items()
            ]
        if question.type == "binary_tradeoff":
            value = answer.value
            return {
                "value": value,
                "lean": "left" if value < 0 else "right" if value > 0 else "balanced",
                "strength": self._tradeoff_strength(abs(value)),
                "left": {"id": question.left[0].id, "text": question.left[0].text},
                "right": {"id": question.right[0].id, "text": question.right[0].text},
            }
        return answer.value

    @staticmethod
    def _tradeoff_strength(value: int) -> str:
        if value == 0:
            return "balanced"
        if value < 35:
            return "mild"
        if value < 70:
            return "clear"
        return "strong"

    @staticmethod
    def _markdown_answer(answer: Any) -> str:
        if isinstance(answer, str):
            return answer
        return "```json\n" + json.dumps(answer, ensure_ascii=False, indent=2) + "\n```"
