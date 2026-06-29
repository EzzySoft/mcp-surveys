# mcp-surveys-cli

Tiny dependency-free CLI for the hosted mcp-surveys API.

```bash
npx mcp-surveys-cli install-skill
npx mcp-surveys-cli template decision > survey.json
npx mcp-surveys-cli schema
npx mcp-surveys-cli create survey.json
npx mcp-surveys-cli wait <survey_id> <result_token> --format markdown
npx mcp-surveys-cli answers <survey_id> <result_token>
npx mcp-surveys-cli stats
```

Use `MCP_SURVEYS_BASE_URL` or `--base-url` to point at another instance.
Outdated-version notices go to stderr and never block the command.
