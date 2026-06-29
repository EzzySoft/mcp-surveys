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


def test_cli_template_prints_payload(capsys):
    assert cli.main(["template", "decision"]) == 0

    payload = json.loads(capsys.readouterr().out)

    assert payload["title"] == "Decision capture"
    assert payload["questions"][0]["type"] == "single_choice"


def test_cli_wait_exports_when_completed(monkeypatch, capsys):
    calls = []

    def fake_request(method, url, body=None, raw=False):
        calls.append((method, url, body, raw))
        if url.endswith("/summary"):
            return {"status": "completed"}
        return "# Done\n"

    monkeypatch.setattr(cli, "request", fake_request)

    assert cli.main(["--base-url", "https://survey.test", "wait", "s1", "tok", "--format", "markdown"]) == 0

    assert capsys.readouterr().out == "# Done\n"
    assert calls[-1] == (
        "POST",
        "https://survey.test/api/agent/surveys/s1/export",
        {"result_token": "tok", "format": "markdown"},
        True,
    )


def test_cli_install_skill_writes_file(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))

    assert cli.main(["install-skill", "--target", "agents"]) == 0

    installed = json.loads(capsys.readouterr().out)["installed"][0]
    assert installed == str(tmp_path / ".agents" / "skills" / "mcp-surveys-cli" / "SKILL.md")
    assert "uvx mcp-surveys-cli template decision" in Path(installed).read_text(encoding="utf-8")
