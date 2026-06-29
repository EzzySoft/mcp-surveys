import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { run } from "../bin/mcp-surveys-cli.js";

process.env.MCP_SURVEYS_SKIP_VERSION_CHECK = "1";

test("create posts a JSON payload", async () => {
  const calls = [];
  const out = [];
  const code = await run(["--base-url", "https://survey.test", "create", "-"], {
    stdin: '{"title":"Lunch","questions":[]}',
    write: (value) => out.push(value),
    error: () => {},
    request: async (method, url, body, raw) => {
      calls.push([method, url, body, raw]);
      return { survey_id: "s1" };
    },
  });

  assert.equal(code, 0);
  assert.deepEqual(JSON.parse(out.join("")), { survey_id: "s1" });
  assert.deepEqual(calls, [["POST", "https://survey.test/api/agent/surveys", { title: "Lunch", questions: [] }, undefined]]);
});

test("request errors are printed", async () => {
  const err = [];
  const code = await run(["summary", "s1", "bad"], {
    stdin: "",
    write: () => {},
    error: (value) => err.push(value),
    request: async () => {
      throw new Error("HTTP 403: invalid result token");
    },
  });

  assert.equal(code, 1);
  assert.match(err.join(""), /invalid result token/);
});

test("template prints a payload", async () => {
  const out = [];
  const code = await run(["template", "decision"], {
    write: (value) => out.push(value),
    error: () => {},
  });

  assert.equal(code, 0);
  assert.equal(JSON.parse(out.join("")).title, "Decision capture");
});

test("wait exports once completed", async () => {
  const calls = [];
  const out = [];
  const code = await run(["--base-url", "https://survey.test", "wait", "s1", "tok", "--format", "markdown"], {
    write: (value) => out.push(value),
    error: () => {},
    request: async (method, url, body, raw) => {
      calls.push([method, url, body, raw]);
      return url.endsWith("/summary") ? { status: "completed" } : "# Done\n";
    },
  });

  assert.equal(code, 0);
  assert.equal(out.join(""), "# Done\n");
  assert.deepEqual(calls.at(-1), [
    "POST",
    "https://survey.test/api/agent/surveys/s1/export",
    { result_token: "tok", format: "markdown" },
    true,
  ]);
});

test("install-skill writes the skill", async () => {
  const home = await mkdtemp(join(tmpdir(), "mcp-surveys-cli-"));
  try {
    const out = [];
    const code = await run(["install-skill", "--target", "agents"], {
      home,
      write: (value) => out.push(value),
      error: () => {},
    });
    const installed = JSON.parse(out.join("")).installed[0];

    assert.equal(code, 0);
    assert.equal(installed, join(home, ".agents", "skills", "mcp-surveys-cli", "SKILL.md"));
    assert.match(await readFile(installed, "utf8"), /uvx mcp-surveys-cli template decision/);
  } finally {
    await rm(home, { recursive: true, force: true });
  }
});

test("warns when version is outdated", async () => {
  delete process.env.MCP_SURVEYS_SKIP_VERSION_CHECK;
  const err = [];
  try {
    const code = await run(["template", "confidence"], {
      write: () => {},
      error: (value) => err.push(value),
      version: "0.2.0",
      latestVersion: async () => "9.0.0",
    });

    assert.equal(code, 0);
    assert.match(err.join(""), /mcp-surveys-cli 0\.2\.0 is outdated/);
    assert.match(err.join(""), /LLM agent/);
  } finally {
    process.env.MCP_SURVEYS_SKIP_VERSION_CHECK = "1";
  }
});

test("ignores version check errors", async () => {
  delete process.env.MCP_SURVEYS_SKIP_VERSION_CHECK;
  const err = [];
  try {
    const code = await run(["template", "confidence"], {
      write: () => {},
      error: (value) => err.push(value),
      latestVersion: async () => {
        throw new Error("registry nap");
      },
    });

    assert.equal(code, 0);
    assert.doesNotMatch(err.join(""), /registry nap/);
  } finally {
    process.env.MCP_SURVEYS_SKIP_VERSION_CHECK = "1";
  }
});
