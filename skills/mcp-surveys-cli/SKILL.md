---
name: mcp-surveys-cli
description: Use when an agent needs short-lived human surveys but should use a small CLI instead of connecting an MCP server.
---

# mcp-surveys-cli

Use the CLI when MCP setup is unavailable, too expensive for context, or the host agent can run shell commands safely.

Default hosted instance:

```bash
uvx mcp-surveys-cli schema
uvx mcp-surveys-cli create survey.json
uvx mcp-surveys-cli summary <survey_id> <result_token>
uvx mcp-surveys-cli answers <survey_id> <result_token>
```

Before the PyPI release, replace `uvx mcp-surveys-cli` with:

```bash
uvx --from "git+https://github.com/EzzySoft/mcp-surveys.git#subdirectory=packages/mcp-surveys-cli" mcp-surveys-cli
```

`create` prints `survey_id`, `public_url`, `result_token`, and expiry data. Send only `public_url` to the human. Keep `result_token` private.

Use `MCP_SURVEYS_BASE_URL` or `--base-url` for another instance.

Question choice rules are the same as the MCP skill: prefer structured buttons, ranking, matching, scale, and `binary_tradeoff`; use `text` only when the answer cannot fit those shapes.
