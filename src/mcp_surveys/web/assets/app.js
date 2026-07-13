import { tokenizeLinks, firstUrl } from "./text.mjs";

const surveyId = location.pathname.split("/").filter(Boolean).pop();
const basePath = location.pathname.includes("/s/") ? location.pathname.split("/s/")[0] : "";
const agentBridge = document.querySelector('meta[name="mcp-surveys-agent"]');
const agentInput = document.querySelector("[data-mcp-surveys-agent-submit]");
const state = {
  survey: null,
  answers: new Map(),
};

const $ = (id) => document.getElementById(id);

// Render a string into `el`, linkifying any http(s) URLs as clickable anchors.
// Uses text nodes for prose (auto-escaped) and a real <a> for each URL, so it
// is XSS-safe without innerHTML. Links open in a new tab with a safe rel.
function renderLinkified(el, text) {
  el.replaceChildren();
  for (const token of tokenizeLinks(text || "")) {
    if (token.type === "text") {
      el.append(document.createTextNode(token.value));
    } else {
      const a = document.createElement("a");
      a.href = token.href;
      a.textContent = token.text;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      el.append(a);
    }
  }
}

function questionTypeLabel(type) {
  const labels = {
    single_choice: "Choose one",
    multiple_choice: "Choose any",
    ranking: "Rank",
    matching: "Match",
    scale: "Scale",
    color_choice: "Color",
    binary_tradeoff: "Tradeoff",
    text: "Short answer",
  };
  return labels[type] || type.replace("_", " ");
}

function setStatus(text) {
  $("save-status").textContent = text;
  $("save-status").parentElement.dataset.status = text.toLowerCase().replace(/\s+/g, "-");
}

function setExpiry(expiresAt) {
  const expiry = new Date(expiresAt);
  $("expiry-status").textContent = `Expires ${expiry.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
}

function showEmpty() {
  document.body.innerHTML = "";
  document.body.append(document.getElementById("empty-template").content.cloneNode(true));
}

async function api(path, options = {}) {
  const headers = {
    "content-type": "application/json",
    "x-mcp-surveys-source": "web",
    "x-mcp-surveys-client": "web",
    "x-mcp-surveys-version": "0.4.0",
    ...(options.headers || {}),
  };
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    throw new Error(await response.text());
  }
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
  const params = new URLSearchParams(location.hash.replace(/^#/, ""));
  return params.get(name);
}

function isSecureSurvey() {
  return state.survey?.crypto?.mode === "e2ee_full";
}

async function decryptSecureSurvey() {
  const keyText = hashParam("k") || hashParam("key");
  if (!keyText) throw new Error("missing secure survey key");
  const key = await crypto.subtle.importKey("raw", base64UrlToBytes(keyText), "AES-GCM", false, ["decrypt"]);
  const spec = state.survey.crypto.spec;
  const plaintext = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: base64UrlToBytes(spec.nonce) },
    key,
    base64UrlToBytes(spec.ciphertext),
  );
  const decoded = JSON.parse(new TextDecoder().decode(plaintext));
  state.survey.title = decoded.title;
  state.survey.description = decoded.description || "";
  state.survey.questions = decoded.questions || [];
}

async function encryptSecureAnswer(question, value, customOptions = {}) {
  const answerKey = crypto.getRandomValues(new Uint8Array(32));
  const nonce = crypto.getRandomValues(new Uint8Array(12));
  const aesKey = await crypto.subtle.importKey("raw", answerKey, "AES-GCM", false, ["encrypt"]);
  const plaintext = new TextEncoder().encode(JSON.stringify({
    question_id: question.id,
    revision: state.survey.crypto.revision,
    value,
    custom_options: customOptions,
  }));
  const ciphertext = await crypto.subtle.encrypt({ name: "AES-GCM", iv: nonce }, aesKey, plaintext);
  const publicKey = await crypto.subtle.importKey(
    "spki",
    base64UrlToBytes(state.survey.crypto.answer_public_key_spki),
    { name: "RSA-OAEP", hash: "SHA-256" },
    false,
    ["encrypt"],
  );
  const encryptedKey = await crypto.subtle.encrypt({ name: "RSA-OAEP" }, publicKey, answerKey);
  return {
    marker: "__mcp_surveys_encrypted_answer_v1__",
    v: 1,
    alg: "RSA-OAEP-256+A256GCM",
    question_id: question.id,
    revision: state.survey.crypto.revision,
    encrypted_key: bytesToBase64Url(new Uint8Array(encryptedKey)),
    nonce: bytesToBase64Url(nonce),
    ciphertext: bytesToBase64Url(new Uint8Array(ciphertext)),
  };
}

function currentAnswer(question) {
  return state.answers.get(question.id);
}

async function save(question, value, customOptions = {}, throwOnError = false) {
  state.answers.set(question.id, { value, custom_options: customOptions });
  renderProgress();
  setStatus("Saving");
  try {
    const decrypted = isSecureSurvey()
      ? { title: state.survey.title, description: state.survey.description, questions: state.survey.questions }
      : null;
    const body = isSecureSurvey()
      ? { value: await encryptSecureAnswer(question, value, customOptions), custom_options: {} }
      : { value, custom_options: customOptions };
    state.survey = await api(`${basePath}/api/surveys/${surveyId}/answers/${question.id}`, {
      method: "PUT",
      body: JSON.stringify(body),
    });
    if (decrypted) Object.assign(state.survey, decrypted);
    setStatus("Saved");
    renderProgress();
  } catch (error) {
    setStatus("Save failed");
    if (throwOnError) throw error;
  }
}

function renderProgress() {
  const total = state.survey?.total_questions || 0;
  let answered = 0;
  for (const question of state.survey?.questions || []) {
    const answer = state.answers.get(question.id);
    if (answer && hasValue(answer.value)) answered += 1;
  }
  $("progress").textContent = `${answered} / ${total}`;
  const progressBar = $("progress-bar");
  if (progressBar) progressBar.style.width = total ? `${Math.round((answered / total) * 100)}%` : "0%";
}

function hasValue(value) {
  if (typeof value === "string") return value.trim().length > 0;
  if (Array.isArray(value)) return value.length > 0;
  if (value && typeof value === "object") return Object.keys(value).length > 0;
  return value !== null && value !== undefined;
}

function optionButton(question, option, selected, onClick) {
  const button = document.createElement("button");
  const isMulti = question.type === "multiple_choice";
  button.type = "button";
  button.className = `choice ${isMulti ? "choice--multiple" : "choice--single"}${selected ? " is-selected" : ""}`;
  button.setAttribute("aria-pressed", selected ? "true" : "false");
  const label = document.createElement("span");
  label.className = "choice-label";
  label.textContent = option.text;
  const mark = document.createElement("span");
  mark.className = "mark";
  mark.setAttribute("aria-hidden", "true");
  button.append(label);
  const href = firstUrl(option.text);
  if (href) {
    button.classList.add("choice--has-link");
    const a = document.createElement("a");
    a.className = "choice-link";
    a.href = href;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.setAttribute("aria-label", `Open ${href} in a new tab`);
    a.textContent = "↗";
    a.addEventListener("click", (event) => {
      event.stopPropagation();
    });
    button.append(a);
  }
  button.append(mark);
  button.addEventListener("click", onClick);
  return button;
}

function renderCustom(question, wrapper, currentCustom = {}) {
  if (!question.allow_custom || ["matching", "scale", "color_choice", "binary_tradeoff", "text"].includes(question.type)) return;

  const row = document.createElement("div");
  row.className = "custom-row";
  const input = document.createElement("input");
  input.placeholder = "Add your own option";
  input.maxLength = 300;
  const button = document.createElement("button");
  button.type = "button";
  button.className = "secondary";
  button.textContent = "Add option";
  button.addEventListener("click", () => {
    const text = input.value.trim();
    if (!text) return;
    const id = `custom:${Date.now().toString(36)}`;
    const custom = { ...currentCustom, [id]: text };
    const option = { id, text };
    question.options = [...question.options, option];
    input.value = "";
    if (question.type === "single_choice") save(question, id, custom);
    if (question.type === "multiple_choice") {
      const selected = Array.isArray(currentAnswer(question)?.value) ? currentAnswer(question).value : [];
      save(question, [...selected, id], custom);
    }
    if (question.type === "ranking") {
      const ranked = Array.isArray(currentAnswer(question)?.value)
        ? currentAnswer(question).value
        : question.options.map((item) => item.id).filter((itemId) => itemId !== id);
      save(question, [...ranked, id], custom);
    }
    renderQuestion(question);
  });
  row.append(input, button);
  wrapper.append(row);
}

function renderChoice(question, multi) {
  const wrapper = document.createElement("div");
  wrapper.className = "choices";
  const answer = currentAnswer(question);
  const selected = new Set(Array.isArray(answer?.value) ? answer.value : answer?.value ? [answer.value] : []);
  const custom = answer?.custom_options || {};

  for (const option of question.options) {
    wrapper.append(optionButton(question, option, selected.has(option.id), () => {
      if (multi) {
        selected.has(option.id) ? selected.delete(option.id) : selected.add(option.id);
        save(question, [...selected], custom);
      } else {
        save(question, option.id, custom);
      }
      renderQuestion(question);
    }));
  }

  renderCustom(question, wrapper, custom);
  return wrapper;
}

function isHexColor(value) {
  return typeof value === "string" && /^#[0-9a-fA-F]{6}$/.test(value);
}

function renderColorChoice(question) {
  const wrapper = document.createElement("div");
  wrapper.className = "color-choices";
  const selected = currentAnswer(question)?.value;

  for (const option of question.options) {
    const color = isHexColor(option.color) ? option.color : "#ded7d1";
    const button = document.createElement("button");
    button.type = "button";
    button.className = `color-choice${selected === option.id ? " is-selected" : ""}`;
    button.style.setProperty("--color-choice", color);
    button.setAttribute("aria-pressed", selected === option.id ? "true" : "false");

    const swatch = document.createElement("span");
    swatch.className = "color-swatch";
    swatch.setAttribute("aria-hidden", "true");
    const label = document.createElement("span");
    label.className = "color-label";
    label.textContent = option.text;
    const value = document.createElement("span");
    value.className = "color-value";
    value.textContent = color.toUpperCase();
    button.append(swatch, label, value);

    button.addEventListener("click", () => {
      save(question, option.id);
      renderQuestion(question);
    });
    wrapper.append(button);
  }

  return wrapper;
}

function move(items, from, to) {
  const next = [...items];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

function renderRanking(question) {
  const wrapper = document.createElement("div");
  wrapper.className = "ranking";
  const answer = currentAnswer(question);
  const ids = Array.isArray(answer?.value) ? answer.value : question.options.map((option) => option.id);
  const custom = answer?.custom_options || {};
  const byId = new Map(question.options.map((option) => [option.id, option]));

  ids.forEach((id, index) => {
    const option = byId.get(id);
    if (!option) return;
    const row = document.createElement("div");
    row.className = "rank-row";
    row.innerHTML = `<span class="rank-index">${index + 1}</span><span class="rank-label"></span>`;
    renderLinkified(row.children[1], option.text);

    const up = document.createElement("button");
    up.type = "button";
    up.className = "small";
    up.textContent = "↑";
    up.setAttribute("aria-label", `Move ${option.text} up`);
    up.disabled = index === 0;
    up.addEventListener("click", () => {
      save(question, move(ids, index, index - 1), custom);
      renderQuestion(question);
    });

    const down = document.createElement("button");
    down.type = "button";
    down.className = "small";
    down.textContent = "↓";
    down.setAttribute("aria-label", `Move ${option.text} down`);
    down.disabled = index === ids.length - 1;
    down.addEventListener("click", () => {
      save(question, move(ids, index, index + 1), custom);
      renderQuestion(question);
    });

    row.append(up, down);
    wrapper.append(row);
  });

  renderCustom(question, wrapper, custom);
  return wrapper;
}

function renderMatching(question) {
  const wrapper = document.createElement("div");
  wrapper.className = "matching";
  const current = currentAnswer(question)?.value || {};

  for (const left of question.left) {
    const row = document.createElement("div");
    row.className = "match-row";
    const label = document.createElement("strong");
    renderLinkified(label, left.text);
    const connector = document.createElement("span");
    connector.className = "connector";
    connector.textContent = "→";
    const select = document.createElement("select");
    const empty = document.createElement("option");
    empty.value = "";
    empty.textContent = "Choose match";
    select.append(empty);
    for (const right of question.right) {
      const option = document.createElement("option");
      option.value = right.id;
      option.textContent = right.text;
      select.append(option);
    }
    select.value = current[left.id] || "";
    select.addEventListener("change", () => {
      const next = { ...(currentAnswer(question)?.value || {}) };
      select.value ? (next[left.id] = select.value) : delete next[left.id];
      save(question, next);
    });
    row.append(label, connector, select);
    wrapper.append(row);
  }

  return wrapper;
}

function renderText(question) {
  const wrapper = document.createElement("div");
  wrapper.className = "text-answer";
  const textarea = document.createElement("textarea");
  textarea.maxLength = 2000;
  textarea.value = currentAnswer(question)?.value || "";
  textarea.placeholder = "Write a short answer";
  textarea.addEventListener("input", () => save(question, textarea.value));
  wrapper.append(textarea);
  return wrapper;
}

function renderScale(question) {
  const wrapper = document.createElement("div");
  wrapper.className = "scale-answer";
  const min = Number.isFinite(question.min) ? question.min : 0;
  const max = Number.isFinite(question.max) ? question.max : 100;
  const step = Number.isFinite(question.step) ? question.step : 1;
  const answer = currentAnswer(question);
  const fallback = Math.round(((min + max) / 2 - min) / step) * step + min;
  const value = Number.isFinite(Number(answer?.value)) ? Number(answer.value) : fallback;

  const valueRow = document.createElement("div");
  valueRow.className = "scale-value-row";
  const minLabel = document.createElement("span");
  renderLinkified(minLabel, question.min_label || String(min));
  const output = document.createElement("strong");
  const maxLabel = document.createElement("span");
  renderLinkified(maxLabel, question.max_label || String(max));
  valueRow.append(minLabel, output, maxLabel);

  const control = document.createElement("div");
  control.className = "scale-control";
  const input = document.createElement("input");
  input.type = "range";
  input.className = "scale-range";
  input.min = String(min);
  input.max = String(max);
  input.step = String(step);
  input.value = String(value);
  input.setAttribute("aria-label", question.prompt);

  const ticks = document.createElement("div");
  ticks.className = "scale-ticks";
  for (let i = 0; i < 5; i += 1) {
    ticks.append(document.createElement("span"));
  }

  const setScaleValue = (next) => {
    const progress = max === min ? 0 : ((next - min) / (max - min)) * 100;
    wrapper.style.setProperty("--scale-progress", `${Math.min(100, Math.max(0, progress))}%`);
    output.textContent = String(next);
  };

  input.addEventListener("input", () => {
    const next = Number(input.value);
    setScaleValue(next);
    save(question, next);
  });

  setScaleValue(value);
  control.append(input, ticks);
  wrapper.append(valueRow, control);
  return wrapper;
}

function hexToSoft(hex) {
  const clean = (hex || "").replace("#", "");
  if (!/^[0-9a-fA-F]{6}$/.test(clean)) return "#eee7f0";
  const value = Number.parseInt(clean, 16);
  const r = (value >> 16) & 255;
  const g = (value >> 8) & 255;
  const b = value & 255;
  return `rgb(${Math.round(r + (255 - r) * 0.86)}, ${Math.round(g + (255 - g) * 0.86)}, ${Math.round(b + (255 - b) * 0.86)})`;
}

function tradeoffTheme(question) {
  const themes = {
    signal: { left: "#c6533d", leftSoft: "#fae9e3", right: "#126a74", rightSoft: "#e2f3f2" },
    mono: { left: "#111111", leftSoft: "#eeeeee", right: "#777777", rightSoft: "#f7f7f7" },
    calm: { left: "#5b6ee1", leftSoft: "#e9ecff", right: "#228b5f", rightSoft: "#e2f5ea" },
  };
  const base = themes[question.theme] || themes.signal;
  return {
    left: question.left_color || base.left,
    leftSoft: question.left_color ? hexToSoft(question.left_color) : base.leftSoft,
    right: question.right_color || base.right,
    rightSoft: question.right_color ? hexToSoft(question.right_color) : base.rightSoft,
  };
}

function tradeoffStrength(absValue) {
  if (absValue === 0) return "balanced";
  if (absValue < 35) return "mild";
  if (absValue < 70) return "clear";
  return "strong";
}

function renderBinaryTradeoff(question) {
  const wrapper = document.createElement("div");
  wrapper.className = "binary-tradeoff";
  const left = question.left[0];
  const right = question.right[0];
  const min = Number.isFinite(question.min) ? question.min : -100;
  const max = Number.isFinite(question.max) ? question.max : 100;
  const step = Number.isFinite(question.step) ? question.step : 5;
  const answer = currentAnswer(question);
  const value = Number.isFinite(Number(answer?.value)) ? Number(answer.value) : 0;
  const theme = tradeoffTheme(question);
  wrapper.style.setProperty("--tradeoff-left", theme.left);
  wrapper.style.setProperty("--tradeoff-left-soft", theme.leftSoft);
  wrapper.style.setProperty("--tradeoff-right", theme.right);
  wrapper.style.setProperty("--tradeoff-right-soft", theme.rightSoft);

  const definitions = document.createElement("div");
  definitions.className = "tradeoff-definitions";
  const leftCard = tradeoffDefinition("A", "Left thesis", left.text, "left");
  const rightCard = tradeoffDefinition("B", "Right thesis", right.text, "right");
  definitions.append(leftCard, rightCard);

  const axis = document.createElement("div");
  axis.className = "tradeoff-axis";
  axis.innerHTML = `
    <div class="tradeoff-axis-end tradeoff-axis-end--left">
      <span class="tradeoff-letter">A</span>
      <span class="tradeoff-axis-title"></span>
    </div>
    <span class="tradeoff-zero">0</span>
    <div class="tradeoff-axis-end tradeoff-axis-end--right">
      <span class="tradeoff-axis-title"></span>
      <span class="tradeoff-letter">B</span>
    </div>
  `;
  renderLinkified(axis.querySelector(".tradeoff-axis-end--left .tradeoff-axis-title"), left.text);
  renderLinkified(axis.querySelector(".tradeoff-axis-end--right .tradeoff-axis-title"), right.text);

  const input = document.createElement("input");
  input.type = "range";
  input.className = "tradeoff-range";
  input.min = String(min);
  input.max = String(max);
  input.step = String(step);
  input.value = String(value);
  input.setAttribute("aria-label", question.prompt);

  const readout = document.createElement("div");
  readout.className = "tradeoff-readout";
  const readoutCopy = document.createElement("div");
  const headline = document.createElement("strong");
  const caption = document.createElement("span");
  readoutCopy.append(headline, caption);
  const score = document.createElement("div");
  score.className = "tradeoff-score";
  readout.append(readoutCopy, score);

  const quick = document.createElement("div");
  quick.className = "tradeoff-quick-picks";
  [
    ["A hard", -80],
    ["A soft", -35],
    ["Balance", 0],
    ["B soft", 35],
    ["B hard", 80],
  ].forEach(([label, next]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    button.addEventListener("click", () => {
      input.value = String(next);
      setTradeoffValue(next);
      save(question, next);
    });
    quick.append(button);
  });

  const setTradeoffValue = (next) => {
    const percent = max === min ? 50 : ((next - min) / (max - min)) * 100;
    const lean = next < 0 ? "A" : next > 0 ? "B" : "balance";
    const absValue = Math.abs(next);
    wrapper.style.setProperty("--tradeoff-progress", `${Math.min(100, Math.max(0, percent))}%`);
    wrapper.style.setProperty("--tradeoff-active", next < 0 ? theme.left : next > 0 ? theme.right : "var(--accent)");
    wrapper.style.setProperty("--tradeoff-active-soft", next < 0 ? theme.leftSoft : next > 0 ? theme.rightSoft : "var(--accent-soft)");
    headline.textContent = next === 0 ? "Balanced tradeoff" : `Leaning toward ${lean}`;
    caption.textContent = next === 0
      ? "Both theses carry equal weight."
      : `${tradeoffStrength(absValue)} signal. Treat this as a ${absValue}/100 pull toward option ${lean}.`;
    score.textContent = next > 0 ? `+${next}` : String(next);
  };

  input.addEventListener("input", () => {
    const next = Number(input.value);
    setTradeoffValue(next);
    save(question, next);
  });

  setTradeoffValue(value);
  wrapper.append(definitions, axis, input, readout, quick);
  return wrapper;
}

function tradeoffDefinition(letter, label, text, side) {
  const card = document.createElement("section");
  card.className = `tradeoff-definition tradeoff-definition--${side}`;
  const mark = document.createElement("span");
  mark.className = "tradeoff-definition-letter";
  mark.textContent = letter;
  const copy = document.createElement("div");
  copy.className = "tradeoff-definition-copy";
  const eyebrow = document.createElement("span");
  eyebrow.textContent = label;
  const title = document.createElement("strong");
  renderLinkified(title, text);
  copy.append(eyebrow, title);
  card.append(mark, copy);
  return card;
}

function renderQuestion(question) {
  const existing = document.querySelector(`[data-question-id="${question.id}"]`);
  const section = existing || document.createElement("article");
  section.className = "question";
  section.dataset.questionId = question.id;
  section.innerHTML = "";

  const head = document.createElement("div");
  head.className = "question-head";
  const title = document.createElement("h2");
  renderLinkified(title, question.prompt);
  const type = document.createElement("span");
  type.className = "question-type";
  type.textContent = question.required ? `${questionTypeLabel(question.type)} · required` : questionTypeLabel(question.type);
  head.append(title, type);
  section.append(head);

  if (question.type === "single_choice") section.append(renderChoice(question, false));
  if (question.type === "multiple_choice") section.append(renderChoice(question, true));
  if (question.type === "ranking") section.append(renderRanking(question));
  if (question.type === "matching") section.append(renderMatching(question));
  if (question.type === "scale") section.append(renderScale(question));
  if (question.type === "color_choice") section.append(renderColorChoice(question));
  if (question.type === "binary_tradeoff") section.append(renderBinaryTradeoff(question));
  if (question.type === "text") section.append(renderText(question));

  if (!existing) $("questions").append(section);
}

function renderSurvey() {
  renderLinkified($("title"), state.survey.title);
  renderLinkified($("description"), state.survey.description || "");
  setExpiry(state.survey.expires_at);
  state.answers = isSecureSurvey() ? new Map() : new Map(Object.entries(state.survey.answers || {}));
  $("questions").innerHTML = "";
  for (const question of state.survey.questions) renderQuestion(question);
  renderProgress();
}

async function complete(throwOnError = false) {
  $("complete").disabled = true;
  setStatus("Submitting");
  try {
    await api(`${basePath}/api/surveys/${surveyId}/complete`, { method: "POST" });
    setStatus("Submitted");
    $("complete").textContent = "Submitted";
    document.body.dataset.completed = "true";
  } catch (error) {
    $("complete").disabled = false;
    setStatus("Submit failed");
    if (throwOnError) throw error;
  }
}

function agentSnapshot() {
  return {
    protocol: "mcp-surveys/browser/v1",
    id: state.survey.id,
    title: state.survey.title,
    description: state.survey.description || "",
    questions: state.survey.questions,
    answers: Object.fromEntries(state.answers),
    completed: document.body.dataset.completed === "true",
    expires_at: state.survey.expires_at,
  };
}

function publishAgentSnapshot(snapshot = agentSnapshot()) {
  agentBridge.dataset.survey = JSON.stringify(snapshot);
  return snapshot;
}

function agentAnswerParts(answer) {
  if (answer && typeof answer === "object" && !Array.isArray(answer) && Object.hasOwn(answer, "value")) {
    return [answer.value, answer.custom_options || {}];
  }
  return [answer, {}];
}

let ready;
const agentApi = Object.freeze({
  read: async () => {
    await ready;
    return publishAgentSnapshot();
  },
  answer: async (questionId, answer) => {
    await ready;
    const question = state.survey.questions.find((item) => item.id === questionId);
    if (!question) throw new Error(`unknown question id: ${questionId}`);
    const [value, customOptions] = agentAnswerParts(answer);
    await save(question, value, customOptions, true);
    return publishAgentSnapshot();
  },
  submit: async (answers = {}) => {
    await ready;
    if (!answers || typeof answers !== "object" || Array.isArray(answers)) {
      throw new Error("answers must be a question-id -> answer object");
    }
    for (const [questionId, answer] of Object.entries(answers)) {
      await agentApi.answer(questionId, answer);
    }
    await complete(true);
    return publishAgentSnapshot();
  },
});
Object.defineProperty(window, "mcpSurveys", { value: agentApi });

agentInput.addEventListener("keydown", async (event) => {
  if (event.key !== "Enter") return;
  event.preventDefault();
  agentBridge.dataset.state = "submitting";
  try {
    const result = await agentApi.submit(JSON.parse(agentInput.value));
    agentBridge.dataset.result = JSON.stringify(result);
    agentBridge.dataset.state = "submitted";
  } catch (error) {
    agentBridge.dataset.result = JSON.stringify({ error: String(error) });
    agentBridge.dataset.state = "error";
  }
});

async function boot() {
  try {
    state.survey = await api(`${basePath}/api/surveys/${surveyId}`);
    if (isSecureSurvey()) await decryptSecureSurvey();
    if (state.survey.completed_at) {
      $("complete").disabled = true;
      $("complete").textContent = "Submitted";
      document.body.dataset.completed = "true";
    }
    $("complete").addEventListener("click", () => complete());
    setStatus("Ready");
    renderSurvey();
    agentBridge.dataset.state = "ready";
    publishAgentSnapshot();
  } catch {
    showEmpty();
  }
}

ready = boot();
ready.catch(() => {});
