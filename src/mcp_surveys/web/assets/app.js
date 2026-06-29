const surveyId = location.pathname.split("/").filter(Boolean).pop();
const basePath = location.pathname.includes("/s/") ? location.pathname.split("/s/")[0] : "";
const state = {
  survey: null,
  answers: new Map(),
};

const $ = (id) => document.getElementById(id);

function questionTypeLabel(type) {
  return type.replace("_", " ");
}

function setStatus(text) {
  $("save-status").textContent = text;
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
  const response = await fetch(path, {
    headers: { "content-type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

function currentAnswer(question) {
  return state.answers.get(question.id);
}

async function save(question, value, customOptions = {}) {
  state.answers.set(question.id, { value, custom_options: customOptions });
  renderProgress();
  setStatus("Saving");
  try {
      state.survey = await api(`${basePath}/api/surveys/${surveyId}/answers/${question.id}`, {
      method: "PUT",
      body: JSON.stringify({ value, custom_options: customOptions }),
    });
    setStatus("Saved");
    renderProgress();
  } catch {
    setStatus("Save failed");
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
}

function hasValue(value) {
  if (typeof value === "string") return value.trim().length > 0;
  if (Array.isArray(value)) return value.length > 0;
  if (value && typeof value === "object") return Object.keys(value).length > 0;
  return value !== null && value !== undefined;
}

function optionButton(question, option, selected, onClick) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `choice${selected ? " is-selected" : ""}`;
  button.innerHTML = `<span class="mark">✓</span><span></span>`;
  button.lastElementChild.textContent = option.text;
  button.addEventListener("click", onClick);
  return button;
}

function renderCustom(question, wrapper, currentCustom = {}) {
  if (!question.allow_custom || question.type === "matching" || question.type === "text") return;

  const row = document.createElement("div");
  row.className = "custom-row";
  const input = document.createElement("input");
  input.placeholder = "Add your own option";
  input.maxLength = 300;
  const button = document.createElement("button");
  button.type = "button";
  button.className = "secondary";
  button.textContent = "Add";
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
    row.innerHTML = `<span class="rank-index">${index + 1}</span><span></span>`;
    row.children[1].textContent = option.text;

    const up = document.createElement("button");
    up.type = "button";
    up.className = "small";
    up.textContent = "Up";
    up.disabled = index === 0;
    up.addEventListener("click", () => {
      save(question, move(ids, index, index - 1), custom);
      renderQuestion(question);
    });

    const down = document.createElement("button");
    down.type = "button";
    down.className = "small";
    down.textContent = "Down";
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
    label.textContent = left.text;
    const connector = document.createElement("span");
    connector.className = "connector";
    connector.textContent = "to";
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

function renderQuestion(question) {
  const existing = document.querySelector(`[data-question-id="${question.id}"]`);
  const section = existing || document.createElement("article");
  section.className = "question";
  section.dataset.questionId = question.id;
  section.innerHTML = "";

  const head = document.createElement("div");
  head.className = "question-head";
  const title = document.createElement("h2");
  title.textContent = question.prompt;
  const type = document.createElement("span");
  type.className = "question-type";
  type.textContent = questionTypeLabel(question.type);
  head.append(title, type);
  section.append(head);

  if (question.type === "single_choice") section.append(renderChoice(question, false));
  if (question.type === "multiple_choice") section.append(renderChoice(question, true));
  if (question.type === "ranking") section.append(renderRanking(question));
  if (question.type === "matching") section.append(renderMatching(question));
  if (question.type === "text") section.append(renderText(question));

  if (!existing) $("questions").append(section);
}

function renderSurvey() {
  $("title").textContent = state.survey.title;
  $("description").textContent = state.survey.description || "";
  setExpiry(state.survey.expires_at);
  state.answers = new Map(Object.entries(state.survey.answers || {}));
  $("questions").innerHTML = "";
  for (const question of state.survey.questions) renderQuestion(question);
  renderProgress();
}

async function complete() {
  $("complete").disabled = true;
  setStatus("Submitting");
  try {
    await api(`${basePath}/api/surveys/${surveyId}/complete`, { method: "POST" });
    setStatus("Submitted");
    $("complete").textContent = "Submitted";
  } catch {
    $("complete").disabled = false;
    setStatus("Submit failed");
  }
}

async function boot() {
  try {
    state.survey = await api(`${basePath}/api/surveys/${surveyId}`);
    if (state.survey.completed_at) $("complete").disabled = true;
    $("complete").addEventListener("click", complete);
    setStatus("Ready");
    renderSurvey();
  } catch {
    showEmpty();
  }
}

boot();
