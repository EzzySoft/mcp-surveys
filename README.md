# mcp-surveys

Public MCP server for agent-created, human-friendly, short-lived surveys.

Use it when an agent needs to ask a person several structured questions and get
the answers back into the agent context. The hosted instance is already live:

- MCP endpoint: `https://mcp.voevoda-sailing.ru/mcp/`
- Health check: `https://mcp.voevoda-sailing.ru/health`
- Public survey links look like: `https://mcp.voevoda-sailing.ru/s/<survey_id>`
- No bearer token is required for the hosted public instance.

The `/mcp/` trailing slash matters. A plain browser or `curl` request to
`/mcp/` can return `406 Not Acceptable` because MCP clients send special
streaming headers. That is expected and is not an auth failure.

## Connect Your Agent

Point your MCP client at the hosted Streamable HTTP endpoint:

```text
https://mcp.voevoda-sailing.ru/mcp/
```

Do not add an `Authorization` header for this hosted instance. It is public,
rate-limited, and designed to be shareable between agents.

Client references: [Codex MCP](https://developers.openai.com/codex/mcp),
[Claude Code MCP](https://docs.anthropic.com/en/docs/claude-code/mcp),
[OpenCode MCP servers](https://opencode.ai/docs/mcp-servers).

### Codex

Add this to `~/.codex/config.toml` or to a project-local `.codex/config.toml`:

```toml
[mcp_servers.mcp_surveys]
url = "https://mcp.voevoda-sailing.ru/mcp/"
```

Restart Codex or open `/mcp` in the Codex TUI to confirm that the server and
tools are visible.

### Claude Code

Use the HTTP transport:

```bash
claude mcp add --transport http mcp-surveys --scope user https://mcp.voevoda-sailing.ru/mcp/
```

Project-scoped config equivalent:

```json
{
  "mcpServers": {
    "mcp-surveys": {
      "type": "http",
      "url": "https://mcp.voevoda-sailing.ru/mcp/"
    }
  }
}
```

### OpenCode

Add a remote MCP server to `~/.config/opencode/opencode.jsonc`:

```jsonc
{
  "mcp": {
    "mcp-surveys": {
      "enabled": true,
      "type": "remote",
      "url": "https://mcp.voevoda-sailing.ru/mcp/"
    }
  }
}
```

### Hermes

Use the same hosted MCP URL in the remote/HTTP MCP server section:

```json
{
  "mcpServers": {
    "mcp-surveys": {
      "type": "streamable-http",
      "url": "https://mcp.voevoda-sailing.ru/mcp/"
    }
  }
}
```

If your Hermes config calls the field `transport` instead of `type`, keep the
same URL and set the transport to `streamable-http` or `http`.

### OpenClaw

For OpenClaw-style configs, add the hosted server as a remote MCP:

```jsonc
{
  "mcp": {
    "mcp-surveys": {
      "enabled": true,
      "type": "remote",
      "url": "https://mcp.voevoda-sailing.ru/mcp/"
    }
  }
}
```

If your OpenClaw build uses the common `mcpServers` map instead, use:

```json
{
  "mcpServers": {
    "mcp-surveys": {
      "type": "http",
      "url": "https://mcp.voevoda-sailing.ru/mcp/"
    }
  }
}
```

## Agent Playbook

1. Use a survey only when chat text would be clumsy.
2. Call `create_survey` with short, tappable questions.
3. Send only `public_url` to the person and mention that it expires in one hour.
4. Keep `survey_id` and `result_token` private in the agent context.
5. After the person says they are done, call `get_survey_summary`.
6. If the survey is partial, decide whether to ask them to finish or continue.
7. Call `get_survey_answers`, `get_question_answer`, or `get_survey_export`.

Never send `result_token` to the respondent. The public URL is enough for
answering; the token is only for the agent reading results later.

## What It Creates

The browser UI is minimal and optimized for quick decisions:

- every click or typed answer is saved immediately;
- the final submit marks the survey as completed;
- completed results stay readable for three hours by default;
- active links expire after one hour by default;
- each option-based question can allow a small "add my own option" flow;
- the UI supports mobile and desktop usage.

Supported question types:

- `single_choice`: choose one option.
- `multiple_choice`: choose several options.
- `ranking`: move options up or down by priority.
- `matching`: connect left-side items to right-side items.
- `text`: free-form text, only when structured formats cannot express the answer.

Prefer structured questions. `text` is intentionally the fallback because long
forms defeat the point of a fast, tappable agent survey.

## MCP Tools

- `create_survey`: creates a survey and returns `survey_id`, `public_url`,
  `result_token`, and expiry data.
- `edit_survey`: edits title, description, or the full question list before the
  survey is completed.
- `get_survey`: returns the current survey spec and progress.
- `get_survey_summary`: returns completion state, timing, and progress counts.
- `get_survey_answers`: returns all answers with option labels resolved.
- `get_question_answer`: returns one answer by question id.
- `get_survey_export`: returns a compact JSON or Markdown export.
- `question_schema`: returns supported question types and payload shapes.

Use `edit_survey` only for small corrections to an active survey, such as fixing
one question or one option. If the survey needs a substantial rewrite, create a
new survey and send a new link.

## Example `create_survey` Payload

IDs are optional. When omitted, the server generates stable IDs from question
and option text.

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
      "type": "matching",
      "prompt": "Match owners to workstreams.",
      "required": false,
      "left": [
        { "text": "Backend" },
        { "text": "Frontend" }
      ],
      "right": [
        { "text": "Alice" },
        { "text": "Sam" }
      ]
    }
  ]
}
```

## Hosted Instance Limits

The public instance is intentionally small and Redis-backed:

- `60` created surveys per client IP per hour.
- `128 KiB` maximum serialized `create_survey` payload.
- `50` questions per survey.
- `50` options per option list.
- `10` custom respondent options per answer.
- `200` characters per title.
- `1200` characters per prompt.
- `500` characters per option.
- `2000` characters per description or free-text answer.
- `1 hour` active survey link lifetime.
- `3 hours` completed result lifetime.

Survey IDs and result tokens are generated with secure random URL-safe tokens.
The public survey link is a capability URL: anyone with it can answer until it
expires. The private `result_token` is required for reading answers through MCP.

## Self-Hosting

The hosted instance above is the default path for agents. Self-host only if you
need your own domain, private auth, different limits, or isolated Redis storage.

```bash
cp .env.example .env
docker compose up -d --build
```

Check `http://127.0.0.1:18173/health`. Survey pages open at `/s/{survey_id}`.
The MCP endpoint is mounted at `/mcp/`. Redis runs inside Compose and keeps no
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
| `MCP_AUTH_TOKEN` | empty | Optional bearer token for private `/mcp/` deployments |
| `SURVEY_LINK_TTL_SECONDS` | `3600` | Active survey lifetime before completion |
| `SURVEY_COMPLETED_TTL_SECONDS` | `10800` | Result lifetime after completion |
| `REDIS_KEY_PREFIX` | `mcp-surveys` | Redis key prefix |
| `CREATE_SURVEY_RATE_LIMIT_PER_HOUR` | `60` | Max surveys created per client IP per hour |
| `MAX_CREATE_SURVEY_BYTES` | `131072` | Max serialized create-survey payload size |

Leave `MCP_AUTH_TOKEN` empty for a public/shareable MCP server. Set it only for
a private deployment where every MCP client can send
`Authorization: Bearer <token>`.

When running behind Caddy, keep the app bound to localhost so
`X-Forwarded-For` is only accepted from your own proxy.

## Deploy Behind Caddy

```caddyfile
mcp.voevoda-sailing.ru {
    request_body {
        max_size 256KB
    }

    reverse_proxy 127.0.0.1:18173
}
```

Set `PUBLIC_BASE_URL=https://mcp.voevoda-sailing.ru`.

## Project Shape

- FastAPI serves the browser UI and JSON API.
- FastMCP exposes agent tools from the same process.
- Redis stores survey specs and answers with TTLs.
- Docker Compose runs the app and Redis.
- Caddy terminates TLS and proxies the public domain.

## Roadmap

The next layer is a `uvx` installable CLI that calls the same HTTP API and ships
with an agent skill. It should stay thin: create surveys, read results, and
avoid occupying MCP context.
