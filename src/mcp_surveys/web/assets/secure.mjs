const encoder = new TextEncoder();
const PROTOCOL_VERSION = 2;
const CONTEXT_PROTOCOL = "mcp-surveys/e2ee/v2";
const SPEC_MARKER = "__mcp_surveys_encrypted_spec_v2__";

function sameArray(left, right) {
  return Array.isArray(left) && Array.isArray(right)
    && left.length === right.length
    && left.every((value, index) => value === right[index]);
}

export function specAad() {
  return encoder.encode("mcp-surveys/spec/v2");
}

export function answerAad(contextId, surveyId, revision, questionId) {
  return encoder.encode(JSON.stringify([
    "mcp-surveys/answer/v2",
    contextId,
    surveyId,
    revision,
    questionId,
  ]));
}

export function assertSecureContext(decoded, crypto) {
  const context = decoded?.context;
  const survey = decoded?.survey;
  const questions = Array.isArray(survey?.questions) ? survey.questions : [];
  const questionIds = questions.map((question) => question.id);
  const requiredQuestionIds = questions.filter((question) => question.required !== false).map((question) => question.id);
  const valid = decoded?.marker === SPEC_MARKER
    && decoded?.v === PROTOCOL_VERSION
    && crypto?.v === PROTOCOL_VERSION
    && crypto?.mode === "e2ee_full"
    && crypto?.spec?.v === PROTOCOL_VERSION
    && context?.protocol === CONTEXT_PROTOCOL
    && context?.mode === "e2ee_full"
    && context.context_id === crypto.context_id
    && context.revision === crypto.revision
    && context.answer_public_key_spki === crypto.answer_public_key_spki
    && sameArray(context.question_ids, crypto.question_ids)
    && sameArray(context.required_question_ids, crypto.required_question_ids)
    && sameArray(context.question_ids, questionIds)
    && sameArray(context.required_question_ids, requiredQuestionIds)
    && new Set(questionIds).size === questionIds.length;
  if (!valid) throw new Error("secure survey integrity check failed");
  return { context: Object.freeze({ ...context }), survey };
}

export function assertPublicSecureMetadata(crypto, pinned, surveyId, responseSurveyId) {
  const valid = responseSurveyId === surveyId
    && crypto?.v === PROTOCOL_VERSION
    && crypto?.mode === "e2ee_full"
    && crypto?.spec?.v === PROTOCOL_VERSION
    && crypto.context_id === pinned.context_id
    && crypto.revision === pinned.revision
    && crypto.answer_public_key_spki === pinned.answer_public_key_spki
    && sameArray(crypto.question_ids, pinned.question_ids)
    && sameArray(crypto.required_question_ids, pinned.required_question_ids);
  if (!valid) throw new Error("secure survey metadata changed after authentication");
}

export const secureProtocolVersion = PROTOCOL_VERSION;
