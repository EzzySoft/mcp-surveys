---
name: mcp-surveys-cli
description: Use when an agent can run shell commands and needs short-lived human surveys through uvx or npx.
---

# mcp-surveys-cli

Use the CLI plus this skill as the default setup. It avoids remote MCP setup,
keeps context small, and works in any agent host that can run `uvx` or `npx`.

Default hosted instance:

```bash
uvx mcp-surveys-cli schema
npx mcp-surveys-cli schema
uvx mcp-surveys-cli create survey.json
npx mcp-surveys-cli create survey.json
uvx mcp-surveys-cli summary <survey_id> <result_token>
uvx mcp-surveys-cli answers <survey_id> <result_token>
```

`create` prints `survey_id`, `public_url`, `result_token`, and expiry data. Send only `public_url` to the human. Keep `result_token` private.

Use `MCP_SURVEYS_BASE_URL` or `--base-url` for another instance.

Prefer structured buttons, ranking, matching, scale, and `binary_tradeoff`; use `text` only when the answer cannot fit those shapes.
