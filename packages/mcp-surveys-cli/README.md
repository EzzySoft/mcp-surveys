# mcp-surveys-cli

Tiny stdlib-only CLI for the hosted mcp-surveys API.

```bash
uvx mcp-surveys-cli install-skill
uvx mcp-surveys-cli template decision > survey.json
uvx mcp-surveys-cli schema
uvx mcp-surveys-cli create survey.json
uvx mcp-surveys-cli wait <survey_id> <result_token> --format markdown
uvx mcp-surveys-cli answers <survey_id> <result_token>
uvx mcp-surveys-cli stats
```

Use `MCP_SURVEYS_BASE_URL` or `--base-url` to point at a different instance.
