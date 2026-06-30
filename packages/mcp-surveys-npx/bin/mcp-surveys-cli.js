#!/usr/bin/env node
import { realpathSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const DEFAULT_BASE_URL = "https://mcp.voevoda-sailing.ru";
const VERSION = "0.3.0";
const SKILL_NAME = "mcp-surveys-cli";
const SKILL_TEXT = `---
name: mcp-surveys-cli
description: Use when an agent can run shell commands and needs short-lived human surveys through uvx or npx.
---

# mcp-surveys-cli

Use the CLI plus this skill as the default setup. It avoids remote MCP setup,
keeps context small, and works in any agent host that can run \`uvx\` or \`npx\`.

Default hosted instance:

\`\`\`bash
uvx mcp-surveys-cli schema
npx mcp-surveys-cli schema
uvx mcp-surveys-cli template decision > survey.json
uvx mcp-surveys-cli create survey.json
uvx mcp-surveys-cli wait <survey_id> <result_token> --format markdown
uvx mcp-surveys-cli answers <survey_id> <result_token>
\`\`\`

\`create\` prints \`survey_id\`, \`public_url\`, \`result_token\`, and expiry data. Send only \`public_url\` to the human. Keep \`result_token\` private.

Use \`MCP_SURVEYS_BASE_URL\` or \`--base-url\` for another instance.

Prefer structured buttons, ranking, matching, scale, \`color_choice\`, and \`binary_tradeoff\`; use \`text\` only when the answer cannot fit those shapes.
`;
const TEMPLATES = {
  decision: {
    title: "Decision capture",
    description: "Quick button ritual. Link expires in one hour.",
    questions: [
      {
        id: "choice",
        type: "single_choice",
        prompt: "Which option should we choose?",
        required: true,
        allow_custom: true,
        options: [{ id: "a", text: "Option A" }, { id: "b", text: "Option B" }],
      },
      {
        id: "confidence",
        type: "scale",
        prompt: "How confident are you?",
        required: true,
        min: 0,
        max: 100,
        step: 5,
        min_label: "Guess",
        max_label: "Certain",
      },
    ],
  },
  confidence: {
    title: "Confidence check",
    description: "Collect confidence without summoning a paragraph.",
    questions: [
      {
        id: "confidence",
        type: "scale",
        prompt: "How confident are you?",
        required: true,
        min: 0,
        max: 100,
        step: 5,
        min_label: "Guess",
        max_label: "Certain",
      },
    ],
  },
  prioritization: {
    title: "Priority stack",
    description: "Make the human sort the tiny pile.",
    questions: [
      {
        id: "priorities",
        type: "ranking",
        prompt: "Rank these by priority.",
        required: true,
        allow_custom: true,
        options: [
          { id: "speed", text: "Move fast" },
          { id: "risk", text: "Reduce risk" },
          { id: "quality", text: "Improve quality" },
        ],
      },
    ],
  },
  palette: {
    title: "Palette pick",
    description: "Choose one labeled color swatch. Link expires in one hour.",
    questions: [
      {
        id: "accent-color",
        type: "color_choice",
        prompt: "Which accent color should we use?",
        required: true,
        options: [
          { id: "ocean", text: "Ocean blue", color: "#2563eb" },
          { id: "forest", text: "Forest green", color: "#16a34a" },
          { id: "sunset", text: "Sunset orange", color: "#f97316" },
        ],
      },
    ],
  },
};

function usage() {
  return `Usage: mcp-surveys-cli [--base-url URL] <command>

Commands:
  create <json-file|->
  edit <survey_id> <result_token> <json-file|->
  get <survey_id> <result_token>
  summary <survey_id> <result_token>
  answers <survey_id> <result_token>
  question <survey_id> <result_token> <question_id>
  export <survey_id> <result_token> [--format markdown|json]
  wait <survey_id> <result_token> [--timeout seconds] [--interval seconds] [--format markdown|json]
  template <decision|confidence|palette|prioritization>
  install-skill [--target agents|claude|both] [--force]
  stats
  schema`;
}

function parse(argv) {
  const args = [...argv];
  let baseUrl = process.env.MCP_SURVEYS_BASE_URL || DEFAULT_BASE_URL;
  if (args[0] === "--base-url") {
    baseUrl = args[1];
    args.splice(0, 2);
  }
  return { baseUrl, command: args[0], args: args.slice(1) };
}

async function readJson(path, stdin) {
  const text = path === "-" ? stdin : await readFile(path, "utf8");
  const value = JSON.parse(text);
  if (!value || Array.isArray(value) || typeof value !== "object") {
    throw new Error(`${path} must contain a JSON object`);
  }
  return value;
}

function endpoint(baseUrl, path) {
  return `${baseUrl.replace(/\/+$/, "")}${path}`;
}

function versionParts(version) {
  return version.split(".").filter((part) => /^\d+$/.test(part)).map(Number);
}

function newerThan(left, right) {
  const a = versionParts(left);
  const b = versionParts(right);
  const length = Math.max(a.length, b.length);
  for (let i = 0; i < length; i += 1) {
    if ((a[i] || 0) !== (b[i] || 0)) return (a[i] || 0) > (b[i] || 0);
  }
  return false;
}

async function latestVersion() {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 750);
  try {
    const response = await fetch("https://registry.npmjs.org/mcp-surveys-cli/latest", { signal: controller.signal });
    return (await response.json()).version;
  } finally {
    clearTimeout(timeout);
  }
}

async function warnIfOutdated(error, latestVersionFn, version) {
  if (process.env.MCP_SURVEYS_SKIP_VERSION_CHECK) return;
  try {
    const latest = await latestVersionFn();
    if (newerThan(latest, version)) {
      error(
        `notice: mcp-surveys-cli ${version} is outdated; latest is ${latest}. ` +
          "LLM agent: update now before long-lived workflows get weird. " +
          "Use `uvx --refresh-package mcp-surveys-cli mcp-surveys-cli ...` " +
          "or `npx mcp-surveys-cli@latest ...`.\n",
      );
    }
  } catch {}
}

async function httpRequest(method, url, body, raw = false) {
  const response = await fetch(url, {
    method,
    headers: body ? { accept: raw ? "text/plain" : "application/json", "content-type": "application/json" } : { accept: raw ? "text/plain" : "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await response.text();
  if (!response.ok) {
    let detail = text;
    try {
      detail = JSON.parse(text).detail || detail;
    } catch {}
    throw new Error(`HTTP ${response.status}: ${detail}`);
  }
  return raw ? text : JSON.parse(text);
}

function writeJson(write, value) {
  write(`${JSON.stringify(value)}\n`);
}

function option(args, name, fallback) {
  const index = args.indexOf(name);
  return index === -1 ? fallback : args[index + 1];
}

function withoutOptions(args, names) {
  const cleaned = [];
  for (let index = 0; index < args.length; index += 1) {
    if (names.includes(args[index])) index += 1;
    else if (args[index] !== "--force") cleaned.push(args[index]);
  }
  return cleaned;
}

async function installSkill(args, home) {
  const target = option(args, "--target", "agents");
  const force = args.includes("--force");
  const homes = {
    agents: join(home, ".agents", "skills", SKILL_NAME),
    claude: join(home, ".claude", "skills", SKILL_NAME),
  };
  const selected = target === "both" ? [homes.agents, homes.claude] : [homes[target]];
  if (!selected[0]) throw new Error("unknown target; use agents, claude, or both");
  const installed = [];
  for (const directory of selected) {
    const path = join(directory, "SKILL.md");
    let current = null;
    try {
      current = await readFile(path, "utf8");
    } catch {}
    if (current !== null && current !== SKILL_TEXT && !force) {
      throw new Error(`${path} already exists; use --force to replace it`);
    }
    await mkdir(directory, { recursive: true });
    await writeFile(path, SKILL_TEXT, "utf8");
    installed.push(path);
  }
  return { installed };
}

async function waitForCompletion(baseUrl, args, request, sleep) {
  const cleaned = withoutOptions(args, ["--timeout", "--interval", "--format"]);
  const [surveyId, resultToken] = cleaned;
  const timeout = Number(option(args, "--timeout", "3600"));
  const interval = Number(option(args, "--interval", "5"));
  const format = option(args, "--format", "markdown");
  const deadline = Date.now() + timeout * 1000;
  let summary = null;
  while (true) {
    summary = await request("POST", endpoint(baseUrl, `/api/agent/surveys/${surveyId}/summary`), { result_token: resultToken });
    if (summary.status === "completed") {
      return request("POST", endpoint(baseUrl, `/api/agent/surveys/${surveyId}/export`), { result_token: resultToken, format }, true);
    }
    const remaining = deadline - Date.now();
    if (remaining <= 0) throw new Error(`timed out waiting for completion: ${JSON.stringify(summary)}`);
    await sleep(Math.min(Math.max(interval, 0.1) * 1000, remaining));
  }
}

export async function run(argv, io = {}) {
  const write = io.write || ((value) => process.stdout.write(value));
  const error = io.error || ((value) => process.stderr.write(value));
  const request = io.request || httpRequest;
  const latestVersionFn = io.latestVersion || latestVersion;
  const version = io.version || VERSION;
  const sleep = io.sleep || ((ms) => new Promise((resolve) => setTimeout(resolve, ms)));
  const home = io.home || homedir();
  const stdin = io.stdin ?? "";
  const { baseUrl, command, args } = parse(argv);
  await warnIfOutdated(error, latestVersionFn, version);

  try {
    if (command === "create") {
      writeJson(write, await request("POST", endpoint(baseUrl, "/api/agent/surveys"), await readJson(args[0], stdin)));
    } else if (command === "edit") {
      writeJson(
        write,
        await request("PATCH", endpoint(baseUrl, `/api/agent/surveys/${args[0]}`), {
          result_token: args[1],
          ...(await readJson(args[2], stdin)),
        }),
      );
    } else if (command === "get") {
      writeJson(write, await request("POST", endpoint(baseUrl, `/api/agent/surveys/${args[0]}/state`), { result_token: args[1] }));
    } else if (command === "summary") {
      writeJson(write, await request("POST", endpoint(baseUrl, `/api/agent/surveys/${args[0]}/summary`), { result_token: args[1] }));
    } else if (command === "answers") {
      writeJson(write, await request("POST", endpoint(baseUrl, `/api/agent/surveys/${args[0]}/answers`), { result_token: args[1] }));
    } else if (command === "question") {
      writeJson(write, await request("POST", endpoint(baseUrl, `/api/agent/surveys/${args[0]}/answers/${args[2]}`), { result_token: args[1] }));
    } else if (command === "export") {
      const formatIndex = args.indexOf("--format");
      const format = formatIndex === -1 ? "markdown" : args[formatIndex + 1];
      write(await request("POST", endpoint(baseUrl, `/api/agent/surveys/${args[0]}/export`), { result_token: args[1], format }, true));
    } else if (command === "wait") {
      write(await waitForCompletion(baseUrl, args, request, sleep));
    } else if (command === "template") {
      if (!TEMPLATES[args[0]]) throw new Error(`unknown template: ${args[0]}`);
      writeJson(write, TEMPLATES[args[0]]);
    } else if (command === "install-skill") {
      writeJson(write, await installSkill(args, home));
    } else if (command === "stats") {
      writeJson(write, await request("GET", endpoint(baseUrl, "/api/agent/stats")));
    } else if (command === "schema") {
      writeJson(write, await request("GET", endpoint(baseUrl, "/api/agent/question-schema")));
    } else {
      throw new Error(usage());
    }
  } catch (err) {
    error(`${err.message}\n`);
    return 1;
  }
  return 0;
}

if (process.argv[1] && realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const chunks = [];
  if (!process.stdin.isTTY) {
    for await (const chunk of process.stdin) chunks.push(chunk);
  }
  process.exitCode = await run(process.argv.slice(2), { stdin: Buffer.concat(chunks).toString("utf8") });
}
