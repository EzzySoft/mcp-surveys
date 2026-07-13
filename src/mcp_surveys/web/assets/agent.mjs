const [, , publicUrl, answersJson] = process.argv;

if (!publicUrl) {
  throw new Error("usage: node agent.mjs <public-url> ['{\"question-id\":\"answer\"}']");
}

const link = new URL(publicUrl);
const surveyId = link.pathname.split("/").filter(Boolean).pop();
const basePath = link.pathname.includes("/s/") ? link.pathname.split("/s/")[0] : "";
const apiBase = `${link.origin}${basePath}/api/surveys/${encodeURIComponent(surveyId)}`;
const headers = {
  "content-type": "application/json",
  "x-mcp-surveys-source": "agent",
  "x-mcp-surveys-client": "node-helper",
  "x-mcp-surveys-version": "builtin",
};

async function request(path = "", options = {}) {
  const response = await fetch(`${apiBase}${path}`, { ...options, headers });
  if (!response.ok) throw new Error(`HTTP ${response.status}: ${await response.text()}`);
  return response.json();
}

function base64UrlToBytes(value) {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (value.length % 4)) % 4);
  const binary = atob(padded);
  return Uint8Array.from(binary, (char) => char.charCodeAt(0));
}

function bytesToBase64Url(bytes) {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function hashParam(name) {
  return new URLSearchParams(link.hash.replace(/^#/, "")).get(name);
}

function isSecure(survey) {
  return survey.crypto?.mode === "e2ee_full";
}

async function decryptSurvey(survey) {
  if (!isSecure(survey)) return survey;
  const keyText = hashParam("k") || hashParam("key");
  if (!keyText) throw new Error("missing secure survey key in URL fragment");
  const key = await crypto.subtle.importKey("raw", base64UrlToBytes(keyText), "AES-GCM", false, ["decrypt"]);
  const plaintext = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: base64UrlToBytes(survey.crypto.spec.nonce) },
    key,
    base64UrlToBytes(survey.crypto.spec.ciphertext),
  );
  const decoded = JSON.parse(new TextDecoder().decode(plaintext));
  return {
    ...survey,
    title: decoded.title,
    description: decoded.description || "",
    questions: decoded.questions || [],
  };
}

function answerParts(answer) {
  if (answer && typeof answer === "object" && !Array.isArray(answer) && Object.hasOwn(answer, "value")) {
    return [answer.value, answer.custom_options || {}];
  }
  return [answer, {}];
}

async function encryptAnswer(survey, questionId, value, customOptions) {
  const answerKey = crypto.getRandomValues(new Uint8Array(32));
  const nonce = crypto.getRandomValues(new Uint8Array(12));
  const aesKey = await crypto.subtle.importKey("raw", answerKey, "AES-GCM", false, ["encrypt"]);
  const plaintext = new TextEncoder().encode(JSON.stringify({
    question_id: questionId,
    revision: survey.crypto.revision,
    value,
    custom_options: customOptions,
  }));
  const ciphertext = await crypto.subtle.encrypt({ name: "AES-GCM", iv: nonce }, aesKey, plaintext);
  const publicKey = await crypto.subtle.importKey(
    "spki",
    base64UrlToBytes(survey.crypto.answer_public_key_spki),
    { name: "RSA-OAEP", hash: "SHA-256" },
    false,
    ["encrypt"],
  );
  const encryptedKey = await crypto.subtle.encrypt({ name: "RSA-OAEP" }, publicKey, answerKey);
  return {
    marker: "__mcp_surveys_encrypted_answer_v1__",
    v: 1,
    alg: "RSA-OAEP-256+A256GCM",
    question_id: questionId,
    revision: survey.crypto.revision,
    encrypted_key: bytesToBase64Url(new Uint8Array(encryptedKey)),
    nonce: bytesToBase64Url(nonce),
    ciphertext: bytesToBase64Url(new Uint8Array(ciphertext)),
  };
}

function snapshot(survey, completed = Boolean(survey.completed_at)) {
  return {
    protocol: "mcp-surveys/node/v1",
    id: survey.id,
    title: survey.title,
    description: survey.description || "",
    questions: survey.questions,
    completed,
    expires_at: survey.expires_at,
    instructions: "Choose stable question/option IDs, then rerun this helper with a question-id -> answer JSON object as the second argument.",
  };
}

const survey = await decryptSurvey(await request());

if (!answersJson) {
  console.log(JSON.stringify(snapshot(survey)));
} else {
  const answers = JSON.parse(answersJson);
  if (!answers || typeof answers !== "object" || Array.isArray(answers)) {
    throw new Error("answers must be a question-id -> answer object");
  }
  for (const [questionId, answer] of Object.entries(answers)) {
    if (!survey.questions.some((question) => question.id === questionId)) {
      throw new Error(`unknown question id: ${questionId}`);
    }
    const [value, customOptions] = answerParts(answer);
    const body = isSecure(survey)
      ? { value: await encryptAnswer(survey, questionId, value, customOptions), custom_options: {} }
      : { value, custom_options: customOptions };
    await request(`/answers/${encodeURIComponent(questionId)}`, { method: "PUT", body: JSON.stringify(body) });
  }
  await request("/complete", { method: "POST" });
  console.log(JSON.stringify({ ...snapshot(survey, true), answers }));
}
