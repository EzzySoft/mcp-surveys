# mcp-surveys-cli

Tiny stdlib-only CLI for the hosted mcp-surveys API.

```bash
uvx mcp-surveys-cli schema
uvx mcp-surveys-cli create survey.json
uvx mcp-surveys-cli answers <survey_id> <result_token>
```

Use `MCP_SURVEYS_BASE_URL` or `--base-url` to point at a different instance.
