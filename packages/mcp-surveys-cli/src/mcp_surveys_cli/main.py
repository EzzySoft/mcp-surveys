from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "https://mcp.voevoda-sailing.ru"


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

    sub.add_parser("schema")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
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
        elif args.command == "schema":
            print_json(request("GET", endpoint(base, "/api/agent/question-schema")))
    except CliError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


def entrypoint() -> None:
    raise SystemExit(main())
