from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "mcp-surveys-cli" / "src"))

import mcp_surveys_cli.main as cli  # noqa: E402


def test_cli_create_posts_payload(monkeypatch, tmp_path, capsys):
    payload = tmp_path / "survey.json"
    payload.write_text('{"title":"Lunch","questions":[]}', encoding="utf-8")
    calls = []

    def fake_request(method, url, body=None, raw=False):
        calls.append((method, url, body, raw))
        return {"survey_id": "s1"}

    monkeypatch.setattr(cli, "request", fake_request)

    assert cli.main(["--base-url", "https://survey.test", "create", str(payload)]) == 0

    assert json.loads(capsys.readouterr().out) == {"survey_id": "s1"}
    assert calls == [
        (
            "POST",
            "https://survey.test/api/agent/surveys",
            {"title": "Lunch", "questions": []},
            False,
        )
    ]


def test_cli_reports_request_errors(monkeypatch, capsys):
    def fail(method, url, body=None, raw=False):
        raise cli.CliError("HTTP 422: bad payload")

    monkeypatch.setattr(cli, "request", fail)

    assert cli.main(["summary", "survey-id", "token"]) == 1
    assert "HTTP 422: bad payload" in capsys.readouterr().err
