# mcp-surveys-cli

Python CLI for secure short-lived human surveys.

Secure `create` is the default and stores the E2EE receipt locally. Send only the returned `public_url` to the human.

```bash
uvx --refresh-package mcp-surveys-cli mcp-surveys-cli install-skill --target both
uvx --refresh-package mcp-surveys-cli mcp-surveys-cli template decision > survey.json
uvx --refresh-package mcp-surveys-cli mcp-surveys-cli schema
uvx --refresh-package mcp-surveys-cli mcp-surveys-cli create survey.json
uvx --refresh-package mcp-surveys-cli mcp-surveys-cli wait <survey_id> --format markdown
uvx --refresh-package mcp-surveys-cli mcp-surveys-cli answers <survey_id>
uvx --refresh-package mcp-surveys-cli mcp-surveys-cli stats
```

Receipt path defaults to `~/.config/mcp-surveys/receipts/<survey_id>.json`; override with `MCP_SURVEYS_RECEIPT_DIR` or pass `--receipt` when reading answers elsewhere.

Plaintext is explicit opt-in only:

```bash
uvx --refresh-package mcp-surveys-cli mcp-surveys-cli create survey.json --mode plaintext
```

Use `MCP_SURVEYS_BASE_URL` or `--base-url` to point at a different instance. Outdated-version notices go to stderr and never block the command.

The hosted API also has a server-side critical upgrade gate: agent calls without `x-mcp-surveys-version: 0.4.0+` receive HTTP 426 with an urgent update message. Current CLI commands send anonymous `client/version/mode` headers automatically for observability.
