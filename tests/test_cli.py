from __future__ import annotations

import json
import secrets
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "mcp-surveys-cli" / "src"))

import mcp_surveys_cli.main as cli  # noqa: E402
import mcp_surveys_cli.secure as secure  # noqa: E402


@pytest.fixture(autouse=True)
def skip_version_check(monkeypatch):
    monkeypatch.setenv("MCP_SURVEYS_SKIP_VERSION_CHECK", "1")


def test_cli_create_posts_payload(monkeypatch, tmp_path, capsys):
    payload = tmp_path / "survey.json"
    payload.write_text('{"title":"Lunch","questions":[]}', encoding="utf-8")
    calls = []

    def fake_request(method, url, body=None, raw=False, extra_headers=None):
        calls.append((method, url, body, raw))
        return {"survey_id": "s1"}

    monkeypatch.setattr(cli, "request", fake_request)

    assert cli.main(["--base-url", "https://survey.test", "create", str(payload), "--mode", "plaintext"]) == 0

    assert json.loads(capsys.readouterr().out) == {"survey_id": "s1"}
    assert calls == [
        (
            "POST",
            "https://survey.test/api/agent/surveys",
            {"title": "Lunch", "questions": []},
            False,
        )
    ]


def test_cli_create_secure_encrypts_payload_and_writes_receipt(monkeypatch, tmp_path, capsys):
    payload = tmp_path / "survey.json"
    payload.write_text(
        json.dumps(
            {
                "title": "Lunch",
                "questions": [
                    {
                        "type": "single_choice",
                        "prompt": "Where?",
                        "options": [{"text": "Ramen"}, {"text": "Pizza"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MCP_SURVEYS_RECEIPT_DIR", str(tmp_path / "receipts"))
    calls = []

    def fake_request(method, url, body=None, raw=False, extra_headers=None):
        calls.append((method, url, body, raw, extra_headers))
        return {
            "survey_id": "s1",
            "public_url": "https://survey.test/s/s1",
            "result_token": "tok",
            "expires_at": "2030-01-01T00:00:00Z",
            "expires_in_seconds": 3600,
        }

    monkeypatch.setattr(cli, "request", fake_request)

    assert cli.main(["--base-url", "https://survey.test", "create", str(payload)]) == 0

    out = json.loads(capsys.readouterr().out)
    assert out["survey_id"] == "s1"
    assert out["public_url"].startswith("https://survey.test/s/s1#k=")
    assert out["receipt_path"].endswith("s1.json")
    body = calls[0][2]
    headers = calls[0][4]
    serialized_body = json.dumps(body)
    assert headers["x-mcp-surveys-client"] == "python-cli"
    assert headers["x-mcp-surveys-version"] == cli.VERSION
    assert headers["x-mcp-surveys-mode"] == "e2ee_full"
    assert body["crypto"]["mode"] == "e2ee_full"
    assert "Lunch" not in serialized_body
    assert "Ramen" not in serialized_body
    receipt = json.loads(Path(out["receipt_path"]).read_text(encoding="utf-8"))
    assert receipt["result_token"] == "tok"
    assert receipt["survey"]["title"] == "Lunch"


def test_secure_receipt_decrypts_answer_envelope():
    payload = {
        "title": "Lunch",
        "questions": [
            {
                "type": "single_choice",
                "prompt": "Where?",
                "options": [{"text": "Ramen"}, {"text": "Pizza"}],
            }
        ],
    }
    body, receipt = secure.encrypted_create_body(payload)
    answer_key = secrets.token_bytes(32)
    nonce = secrets.token_bytes(12)
    answer_plaintext = json.dumps(
        {"question_id": "where", "revision": 1, "value": "ramen", "custom_options": {}},
        separators=(",", ":"),
    ).encode("utf-8")
    ciphertext = AESGCM(answer_key).encrypt(nonce, answer_plaintext, None)
    public_key = serialization.load_der_public_key(secure.b64url_decode(body["crypto"]["answer_public_key_spki"]))
    encrypted_key = public_key.encrypt(
        answer_key,
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    )
    encrypted_response = {
        "survey_id": "s1",
        "title": "Private encrypted survey",
        "summary": {"status": "completed"},
        "answers": [
            {
                "question_id": "where",
                "answered": True,
                "answered_at": "2030-01-01T00:00:00Z",
                "answer": {
                    "marker": secure.ENCRYPTED_ANSWER_MARKER,
                    "v": 1,
                    "alg": "RSA-OAEP-256+A256GCM",
                    "question_id": "where",
                    "revision": 1,
                    "encrypted_key": secure.b64url_encode(encrypted_key),
                    "nonce": secure.b64url_encode(nonce),
                    "ciphertext": secure.b64url_encode(ciphertext),
                },
            }
        ],
    }

    decrypted = secure.decrypt_answers_response(encrypted_response, receipt)

    assert decrypted["title"] == "Lunch"
    assert decrypted["answers"][0]["answer"] == {"id": "ramen", "text": "Ramen"}


def test_cli_reports_request_errors(monkeypatch, capsys):
    def fail(method, url, body=None, raw=False, extra_headers=None):
        raise cli.CliError("HTTP 422: bad payload")

    monkeypatch.setattr(cli, "request", fail)

    assert cli.main(["summary", "survey-id", "token"]) == 1
    assert "HTTP 422: bad payload" in capsys.readouterr().err


def test_cli_template_prints_payload(capsys):
    assert cli.main(["template", "decision"]) == 0

    payload = json.loads(capsys.readouterr().out)

    assert payload["title"] == "Decision capture"
    assert payload["questions"][0]["type"] == "single_choice"


def test_cli_palette_template_prints_color_choice(capsys):
    assert cli.main(["template", "palette"]) == 0

    payload = json.loads(capsys.readouterr().out)

    assert payload["questions"][0]["type"] == "color_choice"
    assert payload["questions"][0]["options"][0]["color"] == "#2563eb"


def test_cli_wait_exports_when_completed(monkeypatch, capsys):
    calls = []

    def fake_request(method, url, body=None, raw=False, extra_headers=None):
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
    assert "mcp-surveys-cli template decision" in Path(installed).read_text(encoding="utf-8")


def test_cli_warns_when_version_is_outdated(monkeypatch, capsys):
    monkeypatch.delenv("MCP_SURVEYS_SKIP_VERSION_CHECK", raising=False)
    monkeypatch.setattr(cli, "VERSION", "0.2.0")
    monkeypatch.setattr(cli, "latest_version", lambda: "9.0.0")

    assert cli.main(["template", "confidence"]) == 0

    err = capsys.readouterr().err
    assert "mcp-surveys-cli 0.2.0 is outdated" in err
    assert "E2EE secure surveys" in err


def test_cli_ignores_version_check_errors(monkeypatch, capsys):
    monkeypatch.delenv("MCP_SURVEYS_SKIP_VERSION_CHECK", raising=False)

    def fail():
        raise RuntimeError("registry nap")

    monkeypatch.setattr(cli, "latest_version", fail)

    assert cli.main(["template", "confidence"]) == 0
    assert "registry nap" not in capsys.readouterr().err
