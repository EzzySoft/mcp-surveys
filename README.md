# mcp-surveys

<p align="center">
  <strong>Secure CLI-first short-lived surveys for agents.</strong><br>
  E2EE by default: the hosted service stores encrypted survey specs and encrypted answers; the creating CLI receipt holds the local keys.
</p>

<p align="center">
  <a href="https://pypi.org/project/mcp-surveys-cli/"><img alt="PyPI" src="https://img.shields.io/pypi/v/mcp-surveys-cli?label=uvx"></a>
  <a href="https://www.npmjs.com/package/mcp-surveys-cli"><img alt="npm" src="https://img.shields.io/npm/v/mcp-surveys-cli?label=npx"></a>
  <a href="https://github.com/EzzySoft/mcp-surveys/releases"><img alt="release" src="https://img.shields.io/github/v/release/EzzySoft/mcp-surveys?filter=cli-v*"></a>
  <a href="https://mcp.voevoda-sailing.ru/health"><img alt="hosted" src="https://img.shields.io/badge/hosted-online-16a34a"></a>
</p>

Give your human a tiny page with buttons instead of another paragraph that says
"pick one of these fourteen things, spiritually".

## Hosted Button Portal

- CLI/API base URL: `https://mcp.voevoda-sailing.ru`
- Health check: `https://mcp.voevoda-sailing.ru/health`
- Human links look like: `https://mcp.voevoda-sailing.ru/s/<survey_id>#k=<view_key>`
- No bearer token. Do not invent one.

## Secure CLI flow

Install/update the agent skill:

```bash
uvx --refresh-package mcp-surveys-cli mcp-surveys-cli install-skill --target both
```

Create and wait for a secure survey:

```bash
uvx --refresh-package mcp-surveys-cli mcp-surveys-cli template decision > survey.json
uvx --refresh-package mcp-surveys-cli mcp-surveys-cli create survey.json
# send only public_url to the human
uvx --refresh-package mcp-surveys-cli mcp-surveys-cli wait <survey_id> --format markdown
```

`create` is secure by default. It prints `survey_id`, `public_url`, `result_token`,
`receipt_path`, and expiry data. Send only `public_url` to the human. Keep
`result_token` and `receipt_path` private.

The CLI stores the E2EE receipt at:

```text
~/.config/mcp-surveys/receipts/<survey_id>.json
```

Use `MCP_SURVEYS_RECEIPT_DIR` to move receipts. If another machine/session needs
to read answers, pass `--receipt /path/to/receipt.json`.

Useful commands:

```bash
uvx --refresh-package mcp-surveys-cli mcp-surveys-cli schema
uvx --refresh-package mcp-surveys-cli mcp-surveys-cli template confidence
uvx --refresh-package mcp-surveys-cli mcp-surveys-cli template palette
uvx --refresh-package mcp-surveys-cli mcp-surveys-cli template prioritization
uvx --refresh-package mcp-surveys-cli mcp-surveys-cli answers <survey_id>
uvx --refresh-package mcp-surveys-cli mcp-surveys-cli export <survey_id> --format markdown
uvx --refresh-package mcp-surveys-cli mcp-surveys-cli stats
```

## Privacy model

Secure mode is designed so the hosted service cannot read survey content:

1. The CLI normalizes the survey and encrypts title/description/questions locally.
2. The server stores only an encrypted spec plus an answer public key.
3. The browser gets the view key from the URL fragment (`#k=...`), which is not sent in HTTP requests.
4. The browser encrypts each answer before saving it.
5. The CLI decrypts answers locally using the private receipt.

Losing the receipt means losing the ability to decrypt answers. That is the point.

## Plaintext is explicit opt-in

Plaintext is not a fallback. Use it only when the user explicitly asks for a
non-private/shareable survey and accepts that the server can read survey data:

```bash
uvx --refresh-package mcp-surveys-cli mcp-surveys-cli create survey.json --mode plaintext
```

`npx mcp-surveys-cli create` fails closed for secure mode. Use the Python `uvx`
CLI for E2EE; `npx ... create --mode plaintext` is explicit plaintext opt-in only.

## Critical upgrade gate

Agent API calls must identify a current client with:

```text
x-mcp-surveys-client: python-cli | npx-cli
x-mcp-surveys-version: 0.4.0+
x-mcp-surveys-mode: e2ee_full | plaintext | unknown
```

Missing or older versions get HTTP `426 Upgrade Required` with a loud message:

```text
CRITICAL UPGRADE REQUIRED: this local mcp-surveys client/MCP integration is too old...
```

The removed `/mcp` endpoint also returns `426` and tells agents to switch to:

```bash
uvx --refresh-package mcp-surveys-cli mcp-surveys-cli ...
```

This makes stale local tools fail loudly instead of silently creating readable/plaintext surveys.

## Observability

The hosted service records anonymous operational counters only:

- event: `created`, `answers_saved`, `completed`, `public_views`, `agent_requests`, `upgrade_required`, rate-limit hits;
- endpoint: `create`, `summary`, `answers`, `export`, `schema`, `stats`, or `mcp` for legacy calls;
- source: `cli`, `web`, `mcp`, or `agent`;
- mode: `e2ee_full`, `plaintext`, or `unknown`;
- client family: `python-cli`, `npx-cli`, `web`, `legacy-mcp`, or `legacy-or-unknown`;
- client version.

It does not store survey contents, keys, result tokens, or IP addresses in stats.
Secure survey contents cannot be decrypted by the hosted service.

## Question types

- `single_choice`: one option.
- `multiple_choice`: several options.
- `ranking`: move options up or down by priority.
- `matching`: connect left-side items to right-side items.
- `scale`: slide to express confidence, risk, intensity, fit, or any other degree.
- `color_choice`: choose one labeled `#RRGGBB` color swatch.
- `binary_tradeoff`: place a marker between option A and option B when both theses are true enough to argue.
- `text`: fallback for answers that cannot be structured.

Prefer structured questions. Use `text` only when the answer refuses to become a button, ranking, matching, scale, swatch, or tradeoff.

## Example payload

IDs are optional. If you skip them, the CLI/server makes stable IDs from text.

```json
{
  "title": "Pick the launch plan",
  "description": "Quick decision capture. Link expires in one hour.",
  "questions": [
    {
      "type": "single_choice",
      "prompt": "Which launch window should we use?",
      "required": true,
      "allow_custom": true,
      "options": [
        { "text": "Monday morning" },
        { "text": "Tuesday afternoon" },
        { "text": "Wait until next week" }
      ]
    },
    {
      "type": "ranking",
      "prompt": "Prioritize the constraints.",
      "required": true,
      "options": [
        { "text": "Lowest operational risk" },
        { "text": "Fastest release" },
        { "text": "Most reviewer availability" }
      ]
    },
    {
      "type": "scale",
      "prompt": "How confident are you in this plan?",
      "required": true,
      "min": 0,
      "max": 100,
      "step": 5,
      "min_label": "Guess",
      "max_label": "Certain"
    }
  ]
}
```

## Limits

- `60` created surveys per client IP per hour.
- `128 KiB` maximum serialized create payload.
- `50` questions per survey.
- `50` options per option list.
- `10` custom respondent options per answer.
- `200` characters per title.
- `1200` characters per prompt.
- `500` characters per option.
- `2000` characters per description or free-text answer.
- `1 hour` active survey lifetime.
- `3 hours` completed result lifetime.

Survey IDs and result tokens are secure random URL-safe tokens. The public link is a capability URL: anyone with it can answer until it expires.

## Self-hosting

The hosted instance is the normal path. Self-host when you need your own domain,
different limits, or isolated Redis storage.

```bash
cp .env.example .env
docker compose up -d --build
curl http://127.0.0.1:18173/health
```

Local development without Docker:

```bash
uv sync --extra dev
REDIS_URL=redis://localhost:6379/0 uv run mcp-surveys
```

Survey pages open at `/s/{survey_id}`. The JSON API is under `/api/`. Redis stores short-lived specs and answers with TTLs.

## Publishing the CLI

Package target: `mcp-surveys-cli`.

Release:

```bash
git tag cli-vX.Y.Z
git push origin cli-vX.Y.Z
```

The workflows publish the Python CLI package and npm shim through trusted publishing/provenance. No package token goes into this repo.

## Knobs

| Variable | Default | Why you care |
| --- | --- | --- |
| `REDIS_URL` | `redis://redis:6379/0` | Where short-lived state lives |
| `PUBLIC_BASE_URL` | `https://mcp.voevoda-sailing.ru` | Base URL returned to agents |
| `SURVEY_LINK_TTL_SECONDS` | `3600` | Active survey lifetime |
| `SURVEY_COMPLETED_TTL_SECONDS` | `10800` | Result lifetime after completion |
| `REDIS_KEY_PREFIX` | `mcp-surveys` | Redis key namespace |
| `CREATE_SURVEY_RATE_LIMIT_PER_HOUR` | `60` | Created surveys per client IP per hour |
| `MAX_CREATE_SURVEY_BYTES` | `131072` | Max serialized create payload |

## What is inside

- FastAPI serves the human UI and JSON API.
- Python `uvx` CLI implements secure create/decrypt flows.
- Dependency-free `npx` shim supports templates/schema/stats and explicit plaintext create.
- Redis stores encrypted specs and answers with TTLs.
- Docker Compose runs app plus Redis.
