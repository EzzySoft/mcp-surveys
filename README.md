# mcp-surveys

Give your human a tiny page with buttons instead of another paragraph that says
"pick one of these fourteen things".

This is a public MCP server for short-lived surveys. You, the agent, create the
survey. Your human taps, ranks, matches, or types a small answer. You fetch the
result back through MCP and continue being useful.

## The Hosted One

Use this one first. It is already running.

- MCP endpoint: `https://mcp.voevoda-sailing.ru/mcp/`
- Health check: `https://mcp.voevoda-sailing.ru/health`
- Human links look like: `https://mcp.voevoda-sailing.ru/s/<survey_id>`
- No bearer token. Do not invent one.

Keep the trailing slash in `/mcp/`. A normal browser or plain `curl` can get
`406 Not Acceptable` there because it is not speaking MCP streaming protocol.
That means "wrong client", not "server sad".

## Settings for You

Point your MCP client at:

```text
https://mcp.voevoda-sailing.ru/mcp/
```

No `Authorization` header is needed for the hosted instance. It is public,
rate-limited, and meant for agent-to-agent sharing.

Client syntax receipts:
[Codex MCP](https://developers.openai.com/codex/mcp),
[Claude Code MCP](https://docs.anthropic.com/en/docs/claude-code/mcp),
[OpenCode MCP servers](https://opencode.ai/docs/mcp-servers).

### Codex

Add this to `~/.codex/config.toml` or project `.codex/config.toml`:

```toml
[mcp_servers.mcp_surveys]
url = "https://mcp.voevoda-sailing.ru/mcp/"
```

Restart Codex, or open `/mcp` in the TUI, and check that `mcp_surveys` is alive.

### Claude Code

Tell Claude Code about the button machine:

```bash
claude mcp add --transport http mcp-surveys --scope user https://mcp.voevoda-sailing.ru/mcp/
```

Project config shape:

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

Use the hosted URL in the remote/HTTP MCP block:

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

If Hermes calls the field `transport`, use `streamable-http` or `http` there.
The URL is the important bit.

### OpenClaw

Remote MCP shape:

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

Common `mcpServers` shape:

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

## How to Operate Your Human

1. Use a survey when chat text would be clumsy.
2. Call `create_survey` with short, tappable questions.
3. Send only `public_url` to the human.
4. Say the link expires in one hour.
5. Keep `survey_id` and `result_token` private in your agent context.
6. When the human says "done", call `get_survey_summary`.
7. If the survey is partial, either ask them to finish or use what you have.
8. Fetch the goods with `get_survey_answers`, `get_question_answer`, or
   `get_survey_export`.

Do not send `result_token` to the human. The public URL lets them answer. The
token lets you read results. Mixing those up is how a simple survey becomes a
little incident report.

## Human Input Shapes

The UI is intentionally small:

- every click or typed answer is saved immediately;
- final submit marks the survey as completed;
- active links expire after one hour;
- completed results stay readable for three hours;
- option questions can let the human add their own option;
- mobile and desktop both work.

Question types:

- `single_choice`: one option.
- `multiple_choice`: several options.
- `ranking`: move options up or down by priority.
- `matching`: connect left-side items to right-side items.
- `scale`: slide to express confidence, risk, intensity, fit, or any other degree.
- `text`: the emergency hatch for answers that cannot be structured.

Prefer buttons, lists, ranking, matching, and scales. Use `text` only when the
answer refuses to become one of those. The point is less typing for the human
and less interpretation for you.

## Tools You Get

- `create_survey`: make the survey and get `survey_id`, `public_url`,
  `result_token`, and expiry data.
- `edit_survey`: make a small correction before completion.
- `get_survey`: inspect the current survey spec and progress.
- `get_survey_summary`: get status, timing, counts, and remaining storage time.
- `get_survey_answers`: get all answers with option labels resolved.
- `get_question_answer`: get one answer by question id.
- `get_survey_export`: get compact Markdown or JSON.
- `question_schema`: ask the server what shapes it accepts.

Use `edit_survey` for tiny repairs. If you are rewriting the whole thing,
create a new survey. Your future self will thank you by not needing a graph.

## Example Payload

IDs are optional. If you skip them, the server makes stable IDs from text.

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

## Interaction Ideas for Later

Not implemented yet, but good future shapes for agents who want richer human
signals without asking for essays:

- `budget_split`: divide 100 points across options.
- `matrix_rating`: rate several items against the same small scale.
- `binary_tradeoff`: drag a marker between two competing statements.
- `timeline_pick`: choose a date or time window on a compact timeline.
- `mood_board`: pick the closest visual/text chip from a small set.

## Limits, Because Public Internet

The hosted instance is intentionally small and Redis-backed:

- `60` created surveys per client IP per hour.
- `128 KiB` maximum serialized `create_survey` payload.
- `50` questions per survey.
- `50` options per option list.
- `10` custom respondent options per answer.
- `200` characters per title.
- `1200` characters per prompt.
- `500` characters per option.
- `2000` characters per description or free-text answer.
- `1 hour` active survey lifetime.
- `3 hours` completed result lifetime.

Survey IDs and result tokens are secure random URL-safe tokens. The public link
is a capability URL: anyone with it can answer until it expires. The private
`result_token` is required to read answers through MCP.

## Self-Hosting, If You Must

The hosted instance is the normal path. Self-host when you need your own domain,
private auth, different limits, or isolated Redis storage.

```bash
cp .env.example .env
docker compose up -d --build
```

Check:

```bash
curl http://127.0.0.1:18173/health
```

Survey pages open at `/s/{survey_id}`. The MCP endpoint is `/mcp/`. Redis runs
inside Compose without disk persistence because these surveys are conversation
artifacts, not a family archive.

Local development without Docker:

```bash
uv sync --extra dev
REDIS_URL=redis://localhost:6379/0 uv run mcp-surveys
```

## Knobs

| Variable | Default | Why you care |
| --- | --- | --- |
| `REDIS_URL` | `redis://redis:6379/0` | Where the short-lived state lives |
| `PUBLIC_BASE_URL` | `https://mcp.voevoda-sailing.ru` | Base URL returned to agents |
| `MCP_AUTH_TOKEN` | empty | Optional bearer token for private `/mcp/` deployments |
| `SURVEY_LINK_TTL_SECONDS` | `3600` | Active survey lifetime |
| `SURVEY_COMPLETED_TTL_SECONDS` | `10800` | Result lifetime after completion |
| `REDIS_KEY_PREFIX` | `mcp-surveys` | Redis key namespace |
| `CREATE_SURVEY_RATE_LIMIT_PER_HOUR` | `60` | Created surveys per client IP per hour |
| `MAX_CREATE_SURVEY_BYTES` | `131072` | Max serialized create payload |

Leave `MCP_AUTH_TOKEN` empty for a public, shareable MCP server. Set it only for
a private deployment where every MCP client can send
`Authorization: Bearer <token>`.

When running behind Caddy, bind the app to localhost so `X-Forwarded-For` only
comes from your proxy.

## Caddy Shape

```caddyfile
mcp.voevoda-sailing.ru {
    request_body {
        max_size 256KB
    }

    reverse_proxy 127.0.0.1:18173
}
```

Set:

```bash
PUBLIC_BASE_URL=https://mcp.voevoda-sailing.ru
```

## What Is Inside

- FastAPI serves the human UI and JSON API.
- FastMCP exposes the agent tools.
- Redis stores specs and answers with TTLs.
- Docker Compose runs app plus Redis.
- Caddy handles TLS and the public domain.

## Later

A thin `uvx` CLI can call the same HTTP API and ship with an agent skill. That
would be useful when MCP context is too expensive for "please ask my human to
choose a thing".
