from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from mcp_surveys_cli import __version__


DEFAULT_BASE_URL = "https://mcp.voevoda-sailing.ru"
VERSION = __version__
SKILL_NAME = "mcp-surveys-cli"
SKILL_TEXT = """---
name: mcp-surveys-cli
description: Use when an agent can run shell commands and needs short-lived human surveys through uvx or npx.
---

# mcp-surveys-cli

Use the CLI plus this skill as the default setup. It avoids remote MCP setup,
keeps context small, and works in any agent host that can run `uvx` or `npx`.

Default hosted instance:

```bash
uvx mcp-surveys-cli schema
npx mcp-surveys-cli schema
uvx mcp-surveys-cli template decision > survey.json
uvx mcp-surveys-cli create survey.json
uvx mcp-surveys-cli wait <survey_id> <result_token> --format markdown
uvx mcp-surveys-cli answers <survey_id> <result_token>
```

`create` prints `survey_id`, `public_url`, `result_token`, and expiry data. Send only `public_url` to the human. Keep `result_token` private.

Use `MCP_SURVEYS_BASE_URL` or `--base-url` for another instance.

Prefer structured buttons, ranking, matching, scale, and `binary_tradeoff`; use `text` only when the answer cannot fit those shapes.
"""
TEMPLATES: dict[str, dict[str, Any]] = {
    "decision": {
        "title": "Decision capture",
        "description": "Quick button ritual. Link expires in one hour.",
        "questions": [
            {
                "id": "choice",
                "type": "single_choice",
                "prompt": "Which option should we choose?",
                "required": True,
                "allow_custom": True,
                "options": [{"id": "a", "text": "Option A"}, {"id": "b", "text": "Option B"}],
            },
            {
                "id": "confidence",
                "type": "scale",
                "prompt": "How confident are you?",
                "required": True,
                "min": 0,
                "max": 100,
                "step": 5,
                "min_label": "Guess",
                "max_label": "Certain",
            },
        ],
    },
    "confidence": {
        "title": "Confidence check",
        "description": "Collect confidence without summoning a paragraph.",
        "questions": [
            {
                "id": "confidence",
                "type": "scale",
                "prompt": "How confident are you?",
                "required": True,
                "min": 0,
                "max": 100,
                "step": 5,
                "min_label": "Guess",
                "max_label": "Certain",
            }
        ],
    },
    "prioritization": {
        "title": "Priority stack",
        "description": "Make the human sort the tiny pile.",
        "questions": [
            {
                "id": "priorities",
                "type": "ranking",
                "prompt": "Rank these by priority.",
                "required": True,
                "allow_custom": True,
                "options": [
                    {"id": "speed", "text": "Move fast"},
                    {"id": "risk", "text": "Reduce risk"},
                    {"id": "quality", "text": "Improve quality"},
                ],
            }
        ],
    },
}


class CliError(Exception):
    pass


def read_json(path: str) -> dict[str, Any]:
    try:
        text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
        value = json.loads(text)
    except OSError as error:
        raise CliError(f"cannot read {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise CliError(f"invalid JSON in {path}: {error}") from error
    if not isinstance(value, dict):
        raise CliError(f"{path} must contain a JSON object")
    return value


def request(method: str, url: str, body: dict[str, Any] | None = None, raw: bool = False) -> Any:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"accept": "text/plain" if raw else "application/json"}
    if body is not None:
        headers["content-type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            text = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(detail).get("detail", detail)
        except json.JSONDecodeError:
            pass
        raise CliError(f"HTTP {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise CliError(f"request failed: {error.reason}") from error
    return text if raw else json.loads(text)


def print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def endpoint(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}{path}"


def _version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split(".") if part.isdigit())


def latest_version() -> str:
    with urllib.request.urlopen("https://pypi.org/pypi/mcp-surveys-cli/json", timeout=0.75) as response:
        return json.loads(response.read().decode("utf-8"))["info"]["version"]


def warn_if_outdated() -> None:
    if os.getenv("MCP_SURVEYS_SKIP_VERSION_CHECK"):
        return
    try:
        latest = latest_version()
        if _version_tuple(latest) > _version_tuple(VERSION):
            print(
                f"notice: mcp-surveys-cli {VERSION} is outdated; latest is {latest}. "
                "LLM agent: update now before long-lived workflows get weird. "
                "Use `uvx --refresh-package mcp-surveys-cli mcp-surveys-cli ...` "
                "or `npx mcp-surveys-cli@latest ...`.",
                file=sys.stderr,
            )
    except Exception:
        pass


def install_skill(target: str, force: bool) -> list[str]:
    homes = {
        "agents": Path.home() / ".agents" / "skills" / SKILL_NAME,
        "claude": Path.home() / ".claude" / "skills" / SKILL_NAME,
    }
    selected = homes.values() if target == "both" else [homes[target]]
    installed: list[str] = []
    for directory in selected:
        path = directory / "SKILL.md"
        if path.exists() and path.read_text(encoding="utf-8") != SKILL_TEXT and not force:
            raise CliError(f"{path} already exists; use --force to replace it")
        directory.mkdir(parents=True, exist_ok=True)
        path.write_text(SKILL_TEXT, encoding="utf-8")
        installed.append(str(path))
    return installed


def wait_for_completion(base: str, survey_id: str, result_token: str, timeout: float, interval: float, fmt: str) -> str:
    deadline = time.monotonic() + timeout
    last_summary: Any = None
    while True:
        last_summary = request("POST", endpoint(base, f"/api/agent/surveys/{survey_id}/summary"), {"result_token": result_token})
        if last_summary.get("status") == "completed":
            return request(
                "POST",
                endpoint(base, f"/api/agent/surveys/{survey_id}/export"),
                {"result_token": result_token, "format": fmt},
                raw=True,
            )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise CliError(f"timed out waiting for completion: {json.dumps(last_summary, ensure_ascii=False, separators=(',', ':'))}")
        time.sleep(min(max(interval, 0.1), remaining))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mcp-surveys-cli")
    parser.add_argument("--base-url", default=os.environ.get("MCP_SURVEYS_BASE_URL", DEFAULT_BASE_URL))
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create")
    create.add_argument("payload", help="JSON file, or '-' for stdin")

    edit = sub.add_parser("edit")
    edit.add_argument("survey_id")
    edit.add_argument("result_token")
    edit.add_argument("patch", help="JSON file, or '-' for stdin")

    for name in ("get", "summary", "answers"):
        command = sub.add_parser(name)
        command.add_argument("survey_id")
        command.add_argument("result_token")

    question = sub.add_parser("question")
    question.add_argument("survey_id")
    question.add_argument("result_token")
    question.add_argument("question_id")

    export = sub.add_parser("export")
    export.add_argument("survey_id")
    export.add_argument("result_token")
    export.add_argument("--format", choices=("markdown", "json"), default="markdown")

    wait = sub.add_parser("wait")
    wait.add_argument("survey_id")
    wait.add_argument("result_token")
    wait.add_argument("--timeout", type=float, default=3600)
    wait.add_argument("--interval", type=float, default=5)
    wait.add_argument("--format", choices=("markdown", "json"), default="markdown")

    template = sub.add_parser("template")
    template.add_argument("name", choices=sorted(TEMPLATES))

    install = sub.add_parser("install-skill")
    install.add_argument("--target", choices=("agents", "claude", "both"), default="agents")
    install.add_argument("--force", action="store_true")

    sub.add_parser("stats")
    sub.add_parser("schema")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    warn_if_outdated()
    base = args.base_url
    try:
        if args.command == "create":
            print_json(request("POST", endpoint(base, "/api/agent/surveys"), read_json(args.payload)))
        elif args.command == "edit":
            body = {"result_token": args.result_token, **read_json(args.patch)}
            print_json(request("PATCH", endpoint(base, f"/api/agent/surveys/{args.survey_id}"), body))
        elif args.command == "get":
            print_json(
                request("POST", endpoint(base, f"/api/agent/surveys/{args.survey_id}/state"), {"result_token": args.result_token})
            )
        elif args.command == "summary":
            print_json(
                request("POST", endpoint(base, f"/api/agent/surveys/{args.survey_id}/summary"), {"result_token": args.result_token})
            )
        elif args.command == "answers":
            print_json(
                request("POST", endpoint(base, f"/api/agent/surveys/{args.survey_id}/answers"), {"result_token": args.result_token})
            )
        elif args.command == "question":
            print_json(
                request(
                    "POST",
                    endpoint(base, f"/api/agent/surveys/{args.survey_id}/answers/{args.question_id}"),
                    {"result_token": args.result_token},
                )
            )
        elif args.command == "export":
            print(
                request(
                    "POST",
                    endpoint(base, f"/api/agent/surveys/{args.survey_id}/export"),
                    {"result_token": args.result_token, "format": args.format},
                    raw=True,
                ),
                end="",
            )
        elif args.command == "wait":
            print(wait_for_completion(base, args.survey_id, args.result_token, args.timeout, args.interval, args.format), end="")
        elif args.command == "template":
            print_json(TEMPLATES[args.name])
        elif args.command == "install-skill":
            print_json({"installed": install_skill(args.target, args.force)})
        elif args.command == "stats":
            print_json(request("GET", endpoint(base, "/api/agent/stats")))
        elif args.command == "schema":
            print_json(request("GET", endpoint(base, "/api/agent/question-schema")))
    except CliError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


def entrypoint() -> None:
    raise SystemExit(main())
