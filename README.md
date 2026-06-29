# mcp-surveys

<p align="center">
  <strong>Agent field manual for tiny human button rituals.</strong><br>
  CLI-first short-lived surveys, with MCP waiting quietly in the side pocket.
</p>

<p align="center">
  <a href="https://pypi.org/project/mcp-surveys-cli/"><img alt="PyPI" src="https://img.shields.io/pypi/v/mcp-surveys-cli?label=uvx"></a>
  <a href="https://www.npmjs.com/package/mcp-surveys-cli"><img alt="npm" src="https://img.shields.io/npm/v/mcp-surveys-cli?label=npx"></a>
  <a href="https://github.com/EzzySoft/mcp-surveys/releases"><img alt="release" src="https://img.shields.io/github/v/release/EzzySoft/mcp-surveys?filter=cli-v*"></a>
  <a href="https://mcp.voevoda-sailing.ru/health"><img alt="hosted" src="https://img.shields.io/badge/hosted-online-16a34a"></a>
</p>

Give your human a tiny page with buttons instead of another paragraph that says
"pick one of these fourteen things, spiritually".

You are an agent. Your human has fingers, opinions, and limited patience for
paragraph archaeology. Install the skill, run the tiny CLI with `uvx` or `npx`,
send the returned link, then fetch the answers back as JSON or Markdown.

There is also a public MCP endpoint for agents that already want remote MCP.
Most agents should start with the CLI plus skill setup: less context rent,
fewer moving parts, same button portal for the human.

## The Hosted Button Portal

Use this one first. It is already running and wearing a tiny production hat.

- CLI/API base URL: `https://mcp.voevoda-sailing.ru`
- Optional MCP endpoint: `https://mcp.voevoda-sailing.ru/mcp/`
- Health check: `https://mcp.voevoda-sailing.ru/health`
- Human links look like: `https://mcp.voevoda-sailing.ru/s/<survey_id>`
- No bearer token. Do not invent one.

## Default Agent Setup

Teach yourself the CLI skill:

```bash
uvx mcp-surveys-cli install-skill
npx mcp-surveys-cli install-skill
```

Other skill pockets, if your host reads them:

```bash
uvx mcp-surveys-cli install-skill --target claude
uvx mcp-surveys-cli install-skill --target both
```

The skill is the little operating manual; the CLI is fetched on demand like a
very small intern.

Then do the whole button ritual:

```bash
uvx mcp-surveys-cli template decision > survey.json
uvx mcp-surveys-cli create survey.json
uvx mcp-surveys-cli wait <survey_id> <result_token> --format markdown
```

Same trick through `npx`:

```bash
npx mcp-surveys-cli template decision > survey.json
npx mcp-surveys-cli create survey.json
npx mcp-surveys-cli wait <survey_id> <result_token> --format markdown
```

Useful side buttons:

```bash
uvx mcp-surveys-cli schema
uvx mcp-surveys-cli template confidence
uvx mcp-surveys-cli template prioritization
uvx mcp-surveys-cli stats
uvx mcp-surveys-cli export <survey_id> <result_token> --format markdown
```

`create` prints `survey_id`, `public_url`, `result_token`, and expiry data.
Hand only `public_url` to the human. Keep `result_token` in your private agent
pocket.

Packages, for agents who like receipts and little official-looking labels:

- PyPI: `mcp-surveys-cli`
- npm: `mcp-surveys-cli`
- releases: `cli-v*` tags on GitHub

Running from a checkout still works for local tinkering, but published packages
are the normal path now. Be modern. Hydrate occasionally.

The CLI prints JSON except `export`, which prints Markdown by default. If it
spots a newer CLI release, it emits a non-blocking stderr notice for agents who
enjoy not being ancient.

## Optional: Remote MCP

Use MCP when your host already supports remote MCP and you want tools instead
of shell commands. Point the MCP client at:

```text
https://mcp.voevoda-sailing.ru/mcp/
```

No `Authorization` header is needed for the hosted instance. It is public,
rate-limited, and meant for agent-to-agent sharing without the secret-token
sock drawer.

Client syntax receipts:
[Codex MCP](https://developers.openai.com/codex/mcp),
[Claude Code MCP](https://docs.anthropic.com/en/docs/claude-code/mcp),
[OpenCode MCP servers](https://opencode.ai/docs/mcp-servers).

Keep the trailing slash in `/mcp/`. A normal browser or plain `curl` can get
`406 Not Acceptable` there because it is not speaking MCP streaming protocol.
That means "wrong client", not "server sad".

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
little incident report with a clipboard and a sigh.

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
- `binary_tradeoff`: place a marker between option A and option B when both
  theses are true enough to argue. Use `signal`, `mono`, or `calm` presets, or
  `custom` with both `left_color` and `right_color` as `#RRGGBB`.
- `text`: the emergency hatch for answers that cannot be structured.

Prefer buttons, lists, ranking, matching, scales, and tradeoffs. Use `text` only
when the answer refuses to become one of those. The point is less typing for the
human and less interpretive dance for you.

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
- `get_stats`: get tiny public counters for the hosted instance.

Use `edit_survey` for tiny repairs. If you are rewriting the whole thing,
create a new survey. Your future self will thank you by not needing a corkboard.

CLI equivalents:

```bash
mcp-surveys-cli install-skill --target both
mcp-surveys-cli template decision
mcp-surveys-cli create survey.json
mcp-surveys-cli wait <survey_id> <result_token> --format markdown
mcp-surveys-cli edit <survey_id> <result_token> patch.json
mcp-surveys-cli get <survey_id> <result_token>
mcp-surveys-cli question <survey_id> <result_token> <question_id>
mcp-surveys-cli stats
```

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
      "type": "binary_tradeoff",
      "prompt": "Where should this release lean?",
      "required": true,
      "left": [
        { "id": "ship", "text": "Ship this week" }
      ],
      "right": [
        { "id": "safe", "text": "Reduce launch risk" }
      ],
      "theme": "signal",
      "left_color": "#c6533d",
      "right_color": "#126a74"
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

Not implemented yet, but still good future shapes for agents who want richer
human signals without summoning an essay swamp:

- `budget_split`: divide 100 points across options.
- `matrix_rating`: rate several items against the same small scale.
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
`result_token` is your answer-reading badge for MCP or the CLI.

## Self-Hosting, If You Must

The hosted instance is the normal path. Self-host when your mission demands its
own domain, private auth, different limits, or isolated Redis storage.

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

### Publishing the CLI

Package target: `mcp-surveys-cli`.

One-time PyPI setup:

- create or claim the `mcp-surveys-cli` PyPI project;
- add a Trusted Publisher for `EzzySoft/mcp-surveys`;
- workflow: `.github/workflows/publish-cli.yml`;
- environment: leave empty unless PyPI asks for one.

Release:

```bash
git tag cli-vX.Y.Z
git push origin cli-vX.Y.Z
```

The workflow builds `packages/mcp-surveys-cli` and publishes with trusted
publishing. No PyPI token goes into this repo.

One-time npm setup:

- create or claim the `mcp-surveys-cli` npm package;
- add trusted publishing for `EzzySoft/mcp-surveys`;
- workflow: `.github/workflows/publish-npm.yml`.

The npm workflow publishes `packages/mcp-surveys-npx` with provenance. No npm
token goes into this repo.

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

## What Is Inside

- FastAPI serves the human UI and JSON API.
- FastMCP exposes the agent tools.
- Stdlib-only `uvx` and dependency-free `npx` CLIs talk to the same hosted API.
- Redis stores specs and answers with TTLs.
- Docker Compose runs app plus Redis.
