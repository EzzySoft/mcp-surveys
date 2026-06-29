import assert from "node:assert/strict";
import { test } from "node:test";

import { run } from "../bin/mcp-surveys-cli.js";

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
