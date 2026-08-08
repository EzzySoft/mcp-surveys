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
    assert body["crypto"]["v"] == 2
    assert body["crypto"]["spec"]["v"] == 2
    assert "Lunch" not in serialized_body
    assert "Ramen" not in serialized_body
    receipt = json.loads(Path(out["receipt_path"]).read_text(encoding="utf-8"))
    assert receipt["v"] == 2
    assert receipt["result_token"] == "tok"
    assert receipt["survey"]["title"] == "Lunch"
    decoded = secure.decrypt_json(
        body["crypto"]["spec"],
        secure.b64url_decode(receipt["view_key"]),
        additional_data=secure.spec_aad(),
    )
    assert decoded["marker"] == "__mcp_surveys_encrypted_spec_v2__"
    assert decoded["context"]["context_id"] == body["crypto"]["context_id"]
    assert decoded["survey"] == receipt["survey"]


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
    survey_id = "s1"
    question_id = "where"
    receipt["survey_id"] = survey_id
    answer_key = secrets.token_bytes(32)
    nonce = secrets.token_bytes(12)
    answer_plaintext = json.dumps(
        {
            "v": 2,
            "context_id": receipt["context_id"],
            "survey_id": survey_id,
            "question_id": question_id,
            "revision": receipt["revision"],
            "value": "ramen",
            "custom_options": {},
        },
        separators=(",", ":"),
    ).encode("utf-8")
    ciphertext = AESGCM(answer_key).encrypt(
        nonce,
        answer_plaintext,
        secure.answer_aad(receipt["context_id"], survey_id, receipt["revision"], question_id),
    )
    public_key = serialization.load_der_public_key(secure.b64url_decode(body["crypto"]["answer_public_key_spki"]))
    encrypted_key = public_key.encrypt(
        answer_key,
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    )
    encrypted_response = {
        "survey_id": survey_id,
        "title": "Private encrypted survey",
        "summary": {"status": "completed"},
        "answers": [
            {
                "question_id": question_id,
                "answered": True,
                "answered_at": "2030-01-01T00:00:00Z",
                "answer": {
                    "marker": secure.ENCRYPTED_ANSWER_MARKER,
                    "v": 2,
                    "alg": "RSA-OAEP-256+A256GCM",
                    "context_id": receipt["context_id"],
                    "survey_id": survey_id,
                    "question_id": question_id,
                    "revision": receipt["revision"],
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

    forged_survey_id = "s2"
    forged_plaintext = {
        **json.loads(answer_plaintext),
        "survey_id": forged_survey_id,
    }
    forged_nonce = secrets.token_bytes(12)
    forged_ciphertext = AESGCM(answer_key).encrypt(
        forged_nonce,
        json.dumps(forged_plaintext, separators=(",", ":")).encode("utf-8"),
        secure.answer_aad(receipt["context_id"], forged_survey_id, receipt["revision"], question_id),
    )
    forged_envelope = {
        **encrypted_response["answers"][0]["answer"],
        "survey_id": forged_survey_id,
        "nonce": secure.b64url_encode(forged_nonce),
        "ciphertext": secure.b64url_encode(forged_ciphertext),
    }
    forged_response = {
        **encrypted_response,
        "survey_id": forged_survey_id,
        "answers": [{**encrypted_response["answers"][0], "answer": forged_envelope}],
    }
    with pytest.raises(ValueError, match="receipt survey id does not match"):
        secure.decrypt_answers_response(forged_response, receipt)


def test_legacy_receipt_rejects_ciphertext_swapped_between_questions():
    private_key_pem, public_key_spki = secure.generate_rsa_keypair()
    answer_key = secrets.token_bytes(32)
    nonce = secrets.token_bytes(12)
    plaintext = json.dumps(
        {
            "marker": secure.LEGACY_ENCRYPTED_ANSWER_MARKER,
            "question_id": "q2",
            "value": "swapped",
            "custom_options": {},
        },
        separators=(",", ":"),
    ).encode("utf-8")
    ciphertext = AESGCM(answer_key).encrypt(nonce, plaintext, None)
    public_key = serialization.load_der_public_key(secure.b64url_decode(public_key_spki))
    encrypted_key = public_key.encrypt(
        answer_key,
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    )
    receipt = {
        "v": 1,
        "survey_id": "s1",
        "answer_private_key_pem": private_key_pem,
        "survey": {
            "title": "Legacy",
            "description": "",
            "questions": [
                {"id": "q1", "type": "text", "prompt": "One?", "required": True},
                {"id": "q2", "type": "text", "prompt": "Two?", "required": True},
            ],
        },
    }
    response = {
        "survey_id": "s1",
        "title": "Private encrypted survey",
        "summary": {"status": "completed"},
        "answers": [
            {
                "question_id": "q1",
                "answered": True,
                "answered_at": "2030-01-01T00:00:00Z",
                "answer": {
                    "marker": secure.LEGACY_ENCRYPTED_ANSWER_MARKER,
                    "v": 1,
                    "alg": "RSA-OAEP-256+A256GCM",
                    "question_id": "q1",
                    "revision": 1,
                    "encrypted_key": secure.b64url_encode(encrypted_key),
                    "nonce": secure.b64url_encode(nonce),
                    "ciphertext": secure.b64url_encode(ciphertext),
                },
            }
        ],
    }

    with pytest.raises(ValueError, match="decrypted answer question id does not match"):
        secure.decrypt_answers_response(response, receipt)


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
