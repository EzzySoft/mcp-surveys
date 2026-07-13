import assert from "node:assert/strict";
import { test } from "node:test";

import { tokenizeLinks, firstUrl } from "../assets/text.mjs";

test("tokenizeLinks: plain text with no URL returns a single text token", () => {
  assert.deepEqual(tokenizeLinks("hello world"), [{ type: "text", value: "hello world" }]);
});

test("tokenizeLinks: empty / non-string returns []", () => {
  assert.deepEqual(tokenizeLinks(""), []);
  assert.deepEqual(tokenizeLinks(null), []);
  assert.deepEqual(tokenizeLinks(undefined), []);
  assert.deepEqual(tokenizeLinks(42), []);
});

test("tokenizeLinks: a single bare URL becomes one link token", () => {
  assert.deepEqual(tokenizeLinks("https://example.com"), [
    { type: "link", href: "https://example.com", text: "https://example.com" },
  ]);
});

test("tokenizeLinks: URL surrounded by text is split into three tokens", () => {
  assert.deepEqual(tokenizeLinks("see https://example.com for details"), [
    { type: "text", value: "see " },
    { type: "link", href: "https://example.com", text: "https://example.com" },
    { type: "text", value: " for details" },
  ]);
});

test("tokenizeLinks: trailing period is stripped from the URL and left as prose", () => {
  assert.deepEqual(tokenizeLinks("Visit https://example.com."), [
    { type: "text", value: "Visit " },
    { type: "link", href: "https://example.com", text: "https://example.com" },
    { type: "text", value: "." },
  ]);
});

test("tokenizeLinks: trailing comma, semicolon, colon, exclamation, question marks are stripped", () => {
  for (const punct of [",", ";", ":", "!", "?"]) {
    const out = tokenizeLinks(`https://example.com${punct}`);
    assert.equal(out.length, 2, `punct ${punct}`);
    assert.deepEqual(out[0], { type: "link", href: "https://example.com", text: "https://example.com" });
    assert.deepEqual(out[1], { type: "text", value: punct });
  }
});

test("tokenizeLinks: trailing closing bracket without matching opener is prose", () => {
  assert.deepEqual(tokenizeLinks("(see https://example.com)"), [
    { type: "text", value: "(see " },
    { type: "link", href: "https://example.com", text: "https://example.com" },
    { type: "text", value: ")" },
  ]);
});

test("tokenizeLinks: balanced parens inside the URL are kept", () => {
  // The "(" has a matching ")", so the whole URL survives.
  assert.deepEqual(tokenizeLinks("https://en.wikipedia.org/wiki/Foo_(bar)"), [
    { type: "link", href: "https://en.wikipedia.org/wiki/Foo_(bar)", text: "https://en.wikipedia.org/wiki/Foo_(bar)" },
  ]);
});

test("tokenizeLinks: multiple URLs in one string all become links", () => {
  const out = tokenizeLinks("first https://a.com then https://b.com end");
  assert.equal(out.filter((t) => t.type === "link").length, 2);
  assert.equal(out[1].href, "https://a.com");
  assert.equal(out[3].href, "https://b.com");
  assert.equal(out[out.length - 1].value, " end");
});

test("tokenizeLinks: javascript: scheme is NOT linkified", () => {
  // The regex requires the https scheme, so this stays plain text.
  assert.deepEqual(tokenizeLinks("javascript:alert(1)"), [{ type: "text", value: "javascript:alert(1)" }]);
});

test("tokenizeLinks: http URLs are also linkified (scheme check)", () => {
  // The implementation supports both http and https.
  assert.deepEqual(tokenizeLinks("http://example.com"), [
    { type: "link", href: "http://example.com", text: "http://example.com" },
  ]);
});

test("firstUrl: returns null for empty / non-string / no URL", () => {
  assert.equal(firstUrl(""), null);
  assert.equal(firstUrl(null), null);
  assert.equal(firstUrl("plain text"), null);
});

test("firstUrl: returns the first URL with trailing punctuation trimmed", () => {
  assert.equal(firstUrl("see https://example.com."), "https://example.com");
  assert.equal(firstUrl("a https://a.com b https://b.com"), "https://a.com");
});

test("firstUrl: trims an unmatched closing paren", () => {
  assert.equal(firstUrl("(https://example.com)"), "https://example.com");
});

test("firstUrl: ignores javascript: scheme", () => {
  assert.equal(firstUrl("javascript:alert(1)"), null);
});
