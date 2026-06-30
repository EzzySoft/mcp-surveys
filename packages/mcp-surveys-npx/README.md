# mcp-surveys-cli

Dependency-free npm shim for the hosted mcp-surveys API.

Use the Python `uvx` CLI for secure E2EE create/decrypt flows. The npm shim intentionally fails closed for secure `create`; it only allows plaintext create when explicitly requested.

```bash
npx mcp-surveys-cli install-skill
npx mcp-surveys-cli template decision > survey.json
npx mcp-surveys-cli template palette
npx mcp-surveys-cli schema
npx mcp-surveys-cli create survey.json --mode plaintext
npx mcp-surveys-cli stats
```

Plaintext is explicit opt-in only and means the server can read survey contents. For private surveys use:

```bash
uvx --refresh-package mcp-surveys-cli mcp-surveys-cli create survey.json
```

Use `MCP_SURVEYS_BASE_URL` or `--base-url` to point at another instance. Outdated-version notices go to stderr and never block the command.

The hosted API has a server-side critical upgrade gate: stale local clients or removed MCP integrations receive HTTP 426 with an urgent update message. Current npx commands send anonymous `client/version/mode` headers automatically for observability.
