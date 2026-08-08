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
    CreateEncryptedSurveyRequest,
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
_STAT_LABEL_RE = re.compile(r"[^a-zA-Z0-9_.-]+")
_ENCRYPTED_ANSWER_MARKER = "__mcp_surveys_encrypted_answer_v2__"
_LEGACY_ENCRYPTED_ANSWER_MARKER = "__mcp_surveys_encrypted_answer_v1__"
_OBSERVABILITY_LABELS = {
    "source": {"agent", "web", "cli", "other"},
    "client": {"python-cli", "npx-cli", "web", "legacy-or-unknown", "other"},
    "version": {"0.4.0", "0.5.0", "0.5.1", "builtin", "unknown", "other"},
    "mode": {"e2ee_full", "plaintext", "unknown", "other"},
    "endpoint": {"create", "edit", "state", "summary", "answers", "question", "export", "schema", "stats", "other"},
    "reason": {"missing-version", "too-old", "other"},
}


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

    async def create_survey(
        self,
        request: CreateSurveyRequest | CreateEncryptedSurveyRequest,
        client_key: str = "unknown",
        client_info: dict[str, str] | None = None,
    ) -> CreatedSurvey:
        if len(request.model_dump_json().encode("utf-8")) > self.max_create_survey_bytes:
            raise SurveyValidationError(f"create_survey payload is larger than {self.max_create_survey_bytes} bytes")
        if isinstance(request, CreateEncryptedSurveyRequest) and request.crypto.v != 2:
            raise SurveyValidationError("secure E2EE protocol v2 is required; recreate with mcp-surveys-cli >= 0.5.1")
        if self.rate_limiter is not None:
            try:
                await self.rate_limiter.check_create_survey(client_key)
            except RateLimitExceeded:
                await self.record_event("rate_limit_hits", {"source": "agent", **(client_info or {})})
                raise
        created_at = now_utc()
        if isinstance(request, CreateEncryptedSurveyRequest):
            survey = Survey(
                id=_token(),
                result_token=_token(),
                title="Private encrypted survey",
                description="End-to-end encrypted. Only the creating CLI receipt can decrypt the content.",
                questions=[],
                crypto=request.crypto,
                response=SurveyResponse(),
                created_at=created_at,
                expires_at=created_at + timedelta(seconds=self.link_ttl_seconds),
            )
        else:
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
        await self.record_event(
            "created",
            {
                "source": "agent",
                "mode": "e2ee_full" if survey.crypto is not None else "plaintext",
                **(client_info or {}),
            },
        )
        return CreatedSurvey(
            survey_id=survey.id,
            public_url=f"{self.public_base_url}/s/{survey.id}",
            result_token=survey.result_token,
            expires_at=survey.expires_at,
            expires_in_seconds=self.link_ttl_seconds,
        )

    async def get_public_survey(self, survey_id: str, client_info: dict[str, str] | None = None) -> PublicSurvey:
        survey = await self.store.get(survey_id)
        await self.record_event(
            "public_views",
            {
                "source": "web",
                "mode": "e2ee_full" if survey.crypto is not None else "plaintext",
                **(client_info or {}),
            },
        )
        return self._public_survey(survey)

    async def save_answer(self, survey_id: str, question_id: str, answer: AnswerIn, client_info: dict[str, str] | None = None) -> PublicSurvey:
        def mutate(survey: Survey) -> int:
            if survey.response.completed_at:
                raise SurveyLocked("survey is already completed")
            if survey.crypto is not None:
                self._validate_encrypted_answer(survey, question_id, answer.value)
            else:
                question = self._question(survey, question_id)
                self._validate_answer(question, answer)
            survey.response.answers[question_id] = StoredAnswer(
                value=answer.value,
                custom_options={} if survey.crypto is not None else answer.custom_options,
                answered_at=now_utc(),
            )
            survey.interactions += 1
            return self._ttl_for(survey)

        survey = await self.store.update(survey_id, mutate)
        await self.record_event(
            "answers_saved",
            {
                "source": "web",
                "mode": "e2ee_full" if survey.crypto is not None else "plaintext",
                **(client_info or {}),
            },
        )
        return self._public_survey(survey)

    async def complete_survey(self, survey_id: str, client_info: dict[str, str] | None = None) -> SurveySummary:
        newly_completed = False

        def mutate(survey: Survey) -> int:
            nonlocal newly_completed
            newly_completed = False
            if survey.response.completed_at:
                return self._ttl_for(survey)
            _, required_answered = self._counts(survey)
            required_total = self._total_required_questions(survey)
            if required_answered != required_total:
                raise SurveyValidationError(f"all required questions must be answered ({required_answered}/{required_total})")
            completed_at = now_utc()
            survey.response.completed_at = completed_at
            survey.expires_at = completed_at + timedelta(seconds=self.completed_ttl_seconds)
            newly_completed = True
            return self.completed_ttl_seconds

        survey = await self.store.update(survey_id, mutate)
        if newly_completed:
            await self.record_event(
                "completed",
                {
                    "source": "web",
                    "mode": "e2ee_full" if survey.crypto is not None else "plaintext",
                    **(client_info or {}),
                },
            )
        return self._summary(survey)

    async def edit_survey(self, survey_id: str, result_token: str, patch: SurveyPatch) -> PublicSurvey:
        def mutate(survey: Survey) -> int:
            if not secrets.compare_digest(survey.result_token, result_token):
                raise SurveyForbidden("invalid result token")
            if survey.crypto is not None:
                raise SurveyValidationError("encrypted surveys must be recreated by the CLI instead of edited on the server")
            if survey.response.completed_at:
                raise SurveyLocked("completed surveys cannot be edited")
            if patch.title is not None:
                survey.title = patch.title
            if patch.description is not None:
                survey.description = patch.description
            if patch.questions is not None:
                survey.questions = normalize_questions(patch.questions)
                survey.response.answers = self._preserve_valid_answers(survey)
            return self._ttl_for(survey)

        survey = await self.store.update(survey_id, mutate)
        return self._public_survey(survey)

    async def get_survey(self, survey_id: str, result_token: str) -> PublicSurvey:
        return self._public_survey(await self._get_for_agent(survey_id, result_token))

    async def get_summary(self, survey_id: str, result_token: str) -> SurveySummary:
        return self._summary(await self._get_for_agent(survey_id, result_token))

    async def get_answers(self, survey_id: str, result_token: str) -> SurveyAnswers:
        survey = await self._get_for_agent(survey_id, result_token)
        if survey.crypto is not None:
            return SurveyAnswers(
                survey_id=survey.id,
                title=survey.title,
                summary=self._summary(survey),
                answers=[self._encrypted_question_answer(question_id, survey.response.answers.get(question_id)) for question_id in survey.crypto.question_ids],
            )
        return SurveyAnswers(
            survey_id=survey.id,
            title=survey.title,
            summary=self._summary(survey),
            answers=[self._question_answer(question, survey.response.answers.get(question.id or "")) for question in survey.questions],
        )

    async def get_question_answer(self, survey_id: str, result_token: str, question_id: str) -> QuestionAnswer:
        survey = await self._get_for_agent(survey_id, result_token)
        if survey.crypto is not None:
            if question_id not in survey.crypto.question_ids:
                raise SurveyValidationError(f"unknown question id: {question_id}")
            return self._encrypted_question_answer(question_id, survey.response.answers.get(question_id))
        question = self._question(survey, question_id)
        return self._question_answer(question, survey.response.answers.get(question_id))

    async def export_answers(self, survey_id: str, result_token: str, fmt: ExportFormat) -> str:
        answers = await self.get_answers(survey_id, result_token)
        if fmt == "json":
            return answers.model_dump_json(indent=2)
        lines = [f"# {answers.title}", "", f"Status: {answers.summary.status}", ""]
        if any(answer.type == "encrypted" for answer in answers.answers):
            lines.append("_Encrypted survey: use `mcp-surveys-cli export <survey_id>` on the machine that has the receipt._")
            return "\n".join(lines).strip() + "\n"
        for answer in answers.answers:
            lines.append(f"## {answer.prompt}")
            lines.append(self._markdown_answer(answer.answer) if answer.answered else "_Unanswered_")
            lines.append("")
        return "\n".join(lines).strip() + "\n"

    async def get_stats(self) -> SurveyStats:
        return await self.store.get_stats()

    async def record_event(self, event: str, labels: dict[str, str] | None = None) -> None:
        safe_event = self._stat_label(event)
        await self.store.increment_stat(safe_event)
        await self._increment_observability(safe_event, labels or {})

    async def _increment_observability(self, event: str, labels: dict[str, str]) -> None:
        safe_event = self._stat_label(event)
        safe_labels = {
            key: self._bounded_label(key, value)
            for key, value in labels.items()
            if value and key in _OBSERVABILITY_LABELS
        }
        for key, value in safe_labels.items():
            await self.store.increment_stat(f"{safe_event}.{key}.{value}")
        client = safe_labels.get("client")
        version = safe_labels.get("version")
        mode = safe_labels.get("mode")
        if client and version:
            await self.store.increment_stat(f"{safe_event}.client_version.{client}.{version}")
        if client and version and mode:
            await self.store.increment_stat(f"{safe_event}.client_version_mode.{client}.{version}.{mode}")

    @classmethod
    def _bounded_label(cls, key: str, value: str) -> str:
        safe_value = cls._stat_label(value)
        return safe_value if safe_value in _OBSERVABILITY_LABELS[key] else "other"

    @staticmethod
    def _stat_label(value: str) -> str:
        cleaned = _STAT_LABEL_RE.sub("-", str(value).strip())[:80].strip(".-_")
        return cleaned or "unknown"

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

    @staticmethod
    def _validate_encrypted_answer(survey: Survey, question_id: str, value: Any) -> None:
        if survey.crypto is None:
            raise SurveyValidationError("survey is not encrypted")
        if question_id not in survey.crypto.question_ids:
            raise SurveyValidationError(f"unknown question id: {question_id}")
        if not isinstance(value, dict):
            raise SurveyValidationError("encrypted answer must be an object")
        if survey.crypto.v == 1:
            metadata_matches = (
                value.get("marker") == _LEGACY_ENCRYPTED_ANSWER_MARKER
                and value.get("v") == 1
                and value.get("question_id") == question_id
                and value.get("revision") == survey.crypto.revision
            )
        else:
            metadata_matches = (
                value.get("marker") == _ENCRYPTED_ANSWER_MARKER
                and value.get("v") == 2
                and value.get("context_id") == survey.crypto.context_id
                and value.get("survey_id") == survey.id
                and value.get("question_id") == question_id
                and value.get("revision") == survey.crypto.revision
            )
        if value.get("alg") != "RSA-OAEP-256+A256GCM":
            raise SurveyValidationError("unsupported encrypted answer envelope")
        if not metadata_matches:
            raise SurveyValidationError("encrypted answer metadata does not match the survey")
        if survey.crypto.v == 2:
            allowed_fields = {
                "marker",
                "v",
                "alg",
                "context_id",
                "survey_id",
                "question_id",
                "revision",
                "encrypted_key",
                "nonce",
                "ciphertext",
            }
            if set(value) != allowed_fields:
                raise SurveyValidationError("encrypted answer envelope has missing or unknown fields")
        for key in ("encrypted_key", "nonce", "ciphertext"):
            if not isinstance(value.get(key), str) or not value[key]:
                raise SurveyValidationError(f"encrypted answer {key} is required")

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
            crypto=survey.crypto,
            answers=survey.response.answers,
            created_at=survey.created_at,
            expires_at=survey.expires_at,
            completed_at=survey.response.completed_at,
            answered_count=answered,
            total_questions=self._total_questions(survey),
            required_answered_count=required_answered,
            total_required_questions=self._total_required_questions(survey),
        )

    def _summary(self, survey: Survey) -> SurveySummary:
        answered, required_answered = self._counts(survey)
        completed_at = survey.response.completed_at
        return SurveySummary(
            survey_id=survey.id,
            title=survey.title,
            status="completed" if completed_at else "active",
            answered_count=answered,
            total_questions=self._total_questions(survey),
            required_answered_count=required_answered,
            total_required_questions=self._total_required_questions(survey),
            interactions=survey.interactions,
            created_at=survey.created_at,
            completed_at=completed_at,
            expires_at=survey.expires_at,
            seconds_to_answer=(completed_at - survey.created_at).total_seconds() if completed_at else None,
            seconds_until_expiry=max(0, int((survey.expires_at - now_utc()).total_seconds())),
        )

    @staticmethod
    def _total_questions(survey: Survey) -> int:
        return len(survey.crypto.question_ids) if survey.crypto is not None else len(survey.questions)

    @staticmethod
    def _total_required_questions(survey: Survey) -> int:
        return len(survey.crypto.required_question_ids) if survey.crypto is not None else sum(1 for question in survey.questions if question.required)

    def _counts(self, survey: Survey) -> tuple[int, int]:
        if survey.crypto is not None:
            answered_ids = {question_id for question_id, answer in survey.response.answers.items() if self._answer_has_value(answer.value)}
            return len(answered_ids & set(survey.crypto.question_ids)), len(answered_ids & set(survey.crypto.required_question_ids))
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

    @staticmethod
    def _encrypted_question_answer(question_id: str, answer: StoredAnswer | None) -> QuestionAnswer:
        if answer is None:
            return QuestionAnswer(question_id=question_id, prompt="Encrypted question", type="encrypted", answered=False)
        return QuestionAnswer(
            question_id=question_id,
            prompt="Encrypted question",
            type="encrypted",
            answered=True,
            answer=answer.value,
            answered_at=answer.answered_at,
        )

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
