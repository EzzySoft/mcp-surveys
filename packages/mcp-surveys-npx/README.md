# mcp-surveys-cli

Tiny dependency-free CLI for the hosted mcp-surveys API.

```bash
npx mcp-surveys-cli schema
npx mcp-surveys-cli create survey.json
npx mcp-surveys-cli answers <survey_id> <result_token>
```

Use `MCP_SURVEYS_BASE_URL` or `--base-url` to point at another instance.
