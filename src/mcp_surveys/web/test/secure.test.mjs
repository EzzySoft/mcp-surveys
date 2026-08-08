import assert from "node:assert/strict";
import { test } from "node:test";

import {
  answerAad,
  assertPublicSecureMetadata,
  assertSecureContext,
  secureProtocolVersion,
  specAad,
} from "../assets/secure.mjs";

const context = {
  protocol: "mcp-surveys/e2ee/v2",
  mode: "e2ee_full",
  context_id: "c".repeat(43),
  revision: 1,
  answer_public_key_spki: "public-key",
  question_ids: ["q1"],
  required_question_ids: ["q1"],
};

const crypto = {
  v: 2,
  mode: "e2ee_full",
  context_id: context.context_id,
  revision: 1,
  answer_public_key_spki: context.answer_public_key_spki,
  question_ids: ["q1"],
  required_question_ids: ["q1"],
  spec: { v: 2, alg: "A256GCM", nonce: "nonce", ciphertext: "ciphertext" },
};

const decoded = {
  marker: "__mcp_surveys_encrypted_spec_v2__",
  v: 2,
  context,
  survey: { title: "Private", questions: [{ id: "q1", required: true }] },
};

test("secure v2 context authenticates matching public metadata", () => {
  assert.equal(secureProtocolVersion, 2);
  assert.deepEqual(new TextDecoder().decode(specAad()), "mcp-surveys/spec/v2");
  assert.equal(assertSecureContext(decoded, crypto).survey.title, "Private");
  assert.doesNotThrow(() => assertPublicSecureMetadata(crypto, context, "s1", "s1"));
});

test("secure v2 context rejects metadata substitution", () => {
  assert.throws(
    () => assertSecureContext(decoded, { ...crypto, context_id: "x".repeat(43) }),
    /integrity check failed/,
  );
  assert.throws(
    () => assertPublicSecureMetadata(crypto, context, "s1", "s2"),
    /metadata changed/,
  );
});

test("answer AAD commits to survey and question identity", () => {
  const aad = new TextDecoder().decode(answerAad(context.context_id, "s1", 1, "q1"));
  assert.equal(aad, JSON.stringify(["mcp-surveys/answer/v2", context.context_id, "s1", 1, "q1"]));
});
