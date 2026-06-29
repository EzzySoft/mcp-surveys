#!/usr/bin/env node
import { realpathSync } from "node:fs";
import { readFile } from "node:fs/promises";
import process from "node:process";
import { fileURLToPath } from "node:url";

const DEFAULT_BASE_URL = "https://mcp.voevoda-sailing.ru";

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

export async function run(argv, io = {}) {
  const write = io.write || ((value) => process.stdout.write(value));
  const error = io.error || ((value) => process.stderr.write(value));
  const request = io.request || httpRequest;
  const stdin = io.stdin ?? "";
  const { baseUrl, command, args } = parse(argv);

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
