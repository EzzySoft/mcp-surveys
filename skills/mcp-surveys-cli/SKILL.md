---
name: mcp-surveys-cli
description: Use when an agent can run shell commands and needs secure short-lived human surveys. Secure E2EE via uvx is the default; plaintext is explicit opt-in only.
---

# mcp-surveys-cli

Use the CLI plus this skill as the default setup. Secure mode keeps keys local in the CLI receipt and the hosted service stores only ciphertext.

Default hosted instance:

```bash
uvx --refresh-package mcp-surveys-cli mcp-surveys-cli schema
uvx --refresh-package mcp-surveys-cli mcp-surveys-cli template decision > survey.json
uvx --refresh-package mcp-surveys-cli mcp-surveys-cli create survey.json
uvx --refresh-package mcp-surveys-cli mcp-surveys-cli wait <survey_id> --format markdown
uvx --refresh-package mcp-surveys-cli mcp-surveys-cli answers <survey_id>
```

`create` is secure by default. It prints `survey_id`, `public_url`, `result_token`, `receipt_path`, and expiry data. Send only `public_url` to the human. Keep `result_token` and `receipt_path` private.

The CLI saves the E2EE receipt at `~/.config/mcp-surveys/receipts/<survey_id>.json` unless `MCP_SURVEYS_RECEIPT_DIR` is set. Later `answers`, `export`, and `wait` can use just `survey_id`; pass `--receipt /path/to/receipt.json` if running from another machine/session.

Plaintext is not a fallback. Use it only when the user explicitly asks for a non-private/shareable survey and accepts that the server can read survey data:

```bash
uvx --refresh-package mcp-surveys-cli mcp-surveys-cli create survey.json --mode plaintext
```

`npx mcp-surveys-cli create` fails closed for secure mode; use the Python `uvx` CLI for E2EE. `npx ... create --mode plaintext` is explicit plaintext opt-in only.

The hosted API has a critical upgrade gate: stale clients and removed MCP integrations get HTTP 426 with `CRITICAL UPGRADE REQUIRED`. Current CLI commands send anonymous `client/version/mode` headers automatically so stats can show usage without content, keys, tokens, or IP addresses.

Use `MCP_SURVEYS_BASE_URL` or `--base-url` for another instance.

Prefer structured buttons, ranking, matching, scale, `color_choice`, and `binary_tradeoff`; use `text` only when the answer cannot fit those shapes.

Any `http(s)://` URL in title, description, prompt, option text, scale labels, or tradeoff theses renders as a clickable link on the survey page (opens in a new tab). Use this to give the human context — docs, screenshots, dashboards — without dumping it into the prompt itself.
