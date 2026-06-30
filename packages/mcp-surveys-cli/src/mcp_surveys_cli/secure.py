from __future__ import annotations

import base64
import json
import os
import re
import secrets
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


ENCRYPTED_ANSWER_MARKER = "__mcp_surveys_encrypted_answer_v1__"
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * ((4 - len(value) % 4) % 4))


def _slug(value: str, fallback: str) -> str:
    slug = _SLUG_RE.sub("-", value.lower()).strip("-")
    return slug[:48] or fallback


def _unique(value: str, used: set[str], fallback: str) -> str:
    base = _slug(value, fallback)
    candidate = base
    index = 2
    while candidate in used:
        candidate = f"{base}-{index}"
        index += 1
    used.add(candidate)
    return candidate


def _normalize_options(options: list[dict[str, Any]], prefix: str) -> list[dict[str, Any]]:
    used: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, option in enumerate(options, start=1):
        next_option = dict(option)
        next_option["id"] = _unique(str(option.get("id") or option.get("text") or ""), used, f"{prefix}{index}")
        normalized.append(next_option)
    return normalized


def normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    used: set[str] = set()
    questions: list[dict[str, Any]] = []
    for index, question in enumerate(payload.get("questions") or [], start=1):
        next_question = dict(question)
        next_question["id"] = _unique(str(question.get("id") or question.get("prompt") or ""), used, f"q{index}")
        next_question["options"] = _normalize_options(list(question.get("options") or []), "o")
        next_question["left"] = _normalize_options(list(question.get("left") or []), "l")
        next_question["right"] = _normalize_options(list(question.get("right") or []), "r")
        questions.append(next_question)
    normalized["questions"] = questions
    return normalized


def encrypt_json(value: dict[str, Any], key: bytes | None = None) -> tuple[bytes, dict[str, str]]:
    aes_key = key or secrets.token_bytes(32)
    nonce = secrets.token_bytes(12)
    plaintext = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ciphertext = AESGCM(aes_key).encrypt(nonce, plaintext, None)
    return aes_key, {"v": 1, "alg": "A256GCM", "nonce": b64url_encode(nonce), "ciphertext": b64url_encode(ciphertext)}


def decrypt_json(blob: dict[str, Any], key: bytes) -> dict[str, Any]:
    if blob.get("alg") != "A256GCM":
        raise ValueError("unsupported encrypted blob")
    plaintext = AESGCM(key).decrypt(b64url_decode(blob["nonce"]), b64url_decode(blob["ciphertext"]), None)
    value = json.loads(plaintext.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("encrypted JSON is not an object")
    return value


def generate_rsa_keypair() -> tuple[str, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    public_spki = private_key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, b64url_encode(public_spki)


def encrypted_create_body(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized = normalize_payload(payload)
    view_key, encrypted_spec = encrypt_json(normalized)
    private_key_pem, public_key_spki = generate_rsa_keypair()
    question_ids = [question["id"] for question in normalized["questions"]]
    required_question_ids = [question["id"] for question in normalized["questions"] if question.get("required", True)]
    body = {
        "crypto": {
            "v": 1,
            "mode": "e2ee_full",
            "revision": 1,
            "spec": encrypted_spec,
            "answer_public_key_spki": public_key_spki,
            "question_ids": question_ids,
            "required_question_ids": required_question_ids,
        }
    }
    receipt = {
        "v": 1,
        "mode": "e2ee_full",
        "view_key": b64url_encode(view_key),
        "answer_private_key_pem": private_key_pem,
        "survey": normalized,
    }
    return body, receipt


def receipt_root() -> Path:
    override = os.getenv("MCP_SURVEYS_RECEIPT_DIR")
    if override:
        return Path(override).expanduser()
    xdg = os.getenv("XDG_CONFIG_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    return base / "mcp-surveys" / "receipts"


def receipt_path(survey_id: str) -> Path:
    return receipt_root() / f"{survey_id}.json"


def save_receipt(survey_id: str, receipt: dict[str, Any]) -> Path:
    path = receipt_path(survey_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def load_receipt(survey_id: str, path: str | None = None) -> dict[str, Any]:
    receipt_file = Path(path).expanduser() if path else receipt_path(survey_id)
    try:
        value = json.loads(receipt_file.read_text(encoding="utf-8"))
    except OSError as error:
        raise FileNotFoundError(f"receipt not found for {survey_id}; expected {receipt_file}") from error
    if not isinstance(value, dict) or value.get("mode") != "e2ee_full":
        raise ValueError(f"{receipt_file} is not an e2ee_full receipt")
    return value


def decrypt_answer(envelope: dict[str, Any], private_key_pem: str) -> dict[str, Any]:
    if envelope.get("marker") != ENCRYPTED_ANSWER_MARKER:
        raise ValueError("answer is not an encrypted mcp-surveys envelope")
    private_key = serialization.load_pem_private_key(private_key_pem.encode("ascii"), password=None)
    answer_key = private_key.decrypt(
        b64url_decode(envelope["encrypted_key"]),
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    )
    plaintext = AESGCM(answer_key).decrypt(b64url_decode(envelope["nonce"]), b64url_decode(envelope["ciphertext"]), None)
    value = json.loads(plaintext.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("decrypted answer is not an object")
    return value


def resolve_answer(question: dict[str, Any], answer: dict[str, Any]) -> Any:
    value = answer.get("value")
    custom_options = answer.get("custom_options") or {}
    labels = {option.get("id"): option.get("text") for option in question.get("options") or []}
    labels.update({item.get("id"): item.get("text") for item in question.get("left") or []})
    labels.update({item.get("id"): item.get("text") for item in question.get("right") or []})
    labels.update(custom_options)
    colors = {option.get("id"): option.get("color") for option in question.get("options") or [] if option.get("color")}
    question_type = question.get("type")
    if question_type == "single_choice":
        return {"id": value, "text": labels.get(value, value)}
    if question_type == "color_choice":
        return {"id": value, "text": labels.get(value, value), "color": colors.get(value)}
    if question_type in {"multiple_choice", "ranking"}:
        return [{"id": item, "text": labels.get(item, item)} for item in value]
    if question_type == "matching":
        return [
            {
                "left_id": left_id,
                "left_text": labels.get(left_id, left_id),
                "right_id": right_id,
                "right_text": labels.get(right_id, right_id),
            }
            for left_id, right_id in value.items()
        ]
    if question_type == "binary_tradeoff":
        left = question.get("left", [{}])[0]
        right = question.get("right", [{}])[0]
        abs_value = abs(value)
        strength = "balanced" if value == 0 else "mild" if abs_value < 35 else "clear" if abs_value < 70 else "strong"
        return {
            "value": value,
            "lean": "left" if value < 0 else "right" if value > 0 else "balanced",
            "strength": strength,
            "left": {"id": left.get("id"), "text": left.get("text")},
            "right": {"id": right.get("id"), "text": right.get("text")},
        }
    return value


def decrypt_answers_response(encrypted_response: dict[str, Any], receipt: dict[str, Any]) -> dict[str, Any]:
    survey = receipt["survey"]
    questions = {question["id"]: question for question in survey["questions"]}
    result_answers: list[dict[str, Any]] = []
    for item in encrypted_response.get("answers") or []:
        question_id = item["question_id"]
        question = questions.get(question_id)
        if question is None:
            continue
        if not item.get("answered"):
            result_answers.append(
                {
                    "question_id": question_id,
                    "prompt": question.get("prompt", question_id),
                    "type": question.get("type"),
                    "answered": False,
                }
            )
            continue
        decrypted = decrypt_answer(item["answer"], receipt["answer_private_key_pem"])
        result_answers.append(
            {
                "question_id": question_id,
                "prompt": question.get("prompt", question_id),
                "type": question.get("type"),
                "answered": True,
                "answer": resolve_answer(question, decrypted),
                "answered_at": item.get("answered_at"),
            }
        )
    summary = dict(encrypted_response.get("summary") or {})
    summary["title"] = survey.get("title", summary.get("title", "Private encrypted survey"))
    return {
        "survey_id": encrypted_response.get("survey_id"),
        "title": survey.get("title", encrypted_response.get("title")),
        "summary": summary,
        "answers": result_answers,
    }


def markdown_export(answers: dict[str, Any]) -> str:
    lines = [f"# {answers.get('title', 'Survey')}", "", f"Status: {answers.get('summary', {}).get('status', 'unknown')}", ""]
    for answer in answers.get("answers") or []:
        lines.append(f"## {answer['prompt']}")
        if not answer.get("answered"):
            lines.append("_Unanswered_")
        elif isinstance(answer.get("answer"), str):
            lines.append(answer["answer"])
        else:
            lines.append("```json")
            lines.append(json.dumps(answer.get("answer"), ensure_ascii=False, indent=2))
            lines.append("```")
        lines.append("")
    return "\n".join(lines).strip() + "\n"
