# mcp-surveys

Ephemeral surveys for agents. An MCP client creates a survey, sends the public
link to a person, then reads the saved answers back through MCP.

The service is intentionally small:

- FastAPI serves the browser UI and JSON API.
- FastMCP exposes agent tools from the same process.
- Redis stores survey specs and answers with TTLs.
- Public survey URLs expire after one hour by default.
- Completed surveys stay readable for three hours by default.

## Run with Docker

```bash
cp .env.example .env
docker compose up -d --build
```

Check `http://127.0.0.1:18173/health`. Survey pages open at `/s/{survey_id}`.
The MCP endpoint is mounted at `/mcp`. Redis runs inside Compose and keeps no
disk persistence because surveys are intentionally short-lived.

For local development without Docker:

```bash
uv sync --extra dev
REDIS_URL=redis://localhost:6379/0 uv run mcp-surveys
```

## Environment

| Variable | Default | Purpose |
| --- | --- | --- |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection string |
| `PUBLIC_BASE_URL` | `https://mcp.voevoda-sailing.ru` | Base URL used in links returned to agents |
| `MCP_AUTH_TOKEN` | empty | Optional bearer token required for `/mcp` |
| `SURVEY_LINK_TTL_SECONDS` | `3600` | Active survey lifetime before completion |
| `SURVEY_COMPLETED_TTL_SECONDS` | `10800` | Result lifetime after completion |
| `REDIS_KEY_PREFIX` | `mcp-surveys` | Redis key prefix |
| `CREATE_SURVEY_RATE_LIMIT_PER_HOUR` | `60` | Max surveys created per client IP per hour |
| `MAX_CREATE_SURVEY_BYTES` | `131072` | Max serialized create-survey payload size |

Do not share `result_token` with the person answering the survey. The public
URL is enough for answering; the result token is only for the agent.

Creation is rate-limited by client IP. When running behind Caddy, keep the app
bound to localhost so `X-Forwarded-For` is only accepted from your proxy.

## MCP tools

- `create_survey` creates a survey and returns `survey_id`, `public_url`,
  `result_token`, and expiry data.
- `edit_survey` edits title, description, or the full question list before the
  survey is completed.
- `get_survey` returns the current survey spec and progress.
- `get_survey_summary` returns completion state, timing, and progress counts.
- `get_survey_answers` returns all answers with labels resolved.
- `get_question_answer` returns one answer by question id.
- `get_survey_export` returns a compact JSON or Markdown export.

Question types:

- `single_choice`
- `multiple_choice`
- `ranking`
- `matching`
- `text`

Use `text` only when the answer cannot be represented by the other formats.
The point of this project is fast, tappable decision capture, not long-form
forms.

Surveys are capped at 50 questions and 128 KiB per create request by default.
That is deliberately generous for agent-generated decision capture while still
small enough for a single Redis-backed instance.

## Deploy behind Caddy

```caddyfile
mcp.voevoda-sailing.ru {
    request_body {
        max_size 256KB
    }

    reverse_proxy 127.0.0.1:18173
}
```

Set `PUBLIC_BASE_URL=https://mcp.voevoda-sailing.ru` and set `MCP_AUTH_TOKEN`
when the MCP endpoint is internet-facing. Point DNS for `mcp.voevoda-sailing.ru`
to the server running Caddy before expecting TLS issuance to succeed.

## Roadmap

The next layer is a `uvx` installable CLI that calls the same HTTP API and
ships with an agent skill. It should stay thin: create surveys, read results,
and avoid occupying MCP context.
