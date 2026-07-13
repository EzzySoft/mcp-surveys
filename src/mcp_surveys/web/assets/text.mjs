// Pure text helpers for linkifying URLs in survey strings.
// No DOM, no side effects — safe to unit-test in Node.

// Matches http(s) URLs starting at a non-whitespace boundary. We intentionally
// require an http/https scheme so things like `javascript:` or `data:`
// cannot become links. We allow a generous set of URL characters and then
// trim trailing punctuation that is almost never part of the URL itself.
const URL_PATTERN = /https?:\/\/[^\s<>"']+/gi;

// Plain trailing punctuation that is almost always prose, not part of the URL.
// Brackets are handled separately because they may be balanced inside the URL.
const TRAILING_PLAIN = ".,;:!?'\"";

// Map a closing bracket to its opener for balance checking.
const OPENER_FOR = { ")": "(", "]": "[", "}": "{" };

/**
 * Trim trailing punctuation off a URL while respecting balanced brackets.
 *
 * Returns { href, trimmed } where `trimmed` is the number of characters peeled
 * off the end so the caller can keep the prose in the text stream.
 *
 * Algorithm:
 *   1. Peel plain punctuation (period, comma, semicolon, colon, bang, question,
 *      quotes) — these are almost never part of the URL.
 *   2. If the last character is a closing bracket, count openers vs closers in
 *      the remaining href. If closers outnumber openers, the trailing bracket
 *      is prose — peel it and loop (there may be another run of plain punct
 *      behind it, e.g. "https://x.com)." ).
 *   3. Stop when nothing peeled in a pass.
 */
function peelTrailing(href) {
  let trimmed = 0;
  let changed = true;
  while (changed && href.length > 0) {
    changed = false;

    while (href.length > 0 && TRAILING_PLAIN.includes(href[href.length - 1])) {
      href = href.slice(0, -1);
      trimmed += 1;
      changed = true;
    }

    const closing = href[href.length - 1];
    if (closing && closing in OPENER_FOR) {
      const opener = OPENER_FOR[closing];
      const openerCount = (href.match(new RegExp(`\\${opener}`, "g")) || []).length;
      const closerCount = (href.match(new RegExp(`\\${closing}`, "g")) || []).length;
      // If there is no matching opener inside the URL, this trailing closer is
      // prose (e.g. "(see https://x.com)"). Peel it.
      if (closerCount > openerCount) {
        href = href.slice(0, -1);
        trimmed += 1;
        changed = true;
      }
    }
  }
  return { href, trimmed };
}

/**
 * Split a string into ordered tokens: plain text and links.
 *
 * Link tokens only ever have an http(s) href (the regex enforces this), so
 * `javascript:` / `data:` URIs cannot slip through. Trailing punctuation that
 * is almost certainly prose (periods, commas, unbalanced closing brackets,
 * quotes) is pulled out of the URL and left as plain text so the link target
 * stays clean.
 *
 * Returns an array of { type: "text", value } | { type: "link", href, text }.
 * The `text` of a link equals its `href` (no markdown label support yet).
 */
export function tokenizeLinks(text) {
  if (typeof text !== "string" || text.length === 0) return [];

  const tokens = [];
  let last = 0;
  // Reset state on the shared global regex to make the function reentrant.
  URL_PATTERN.lastIndex = 0;
  let match = URL_PATTERN.exec(text);

  while (match !== null) {
    const rawStart = match.index;
    const { href, trimmed } = peelTrailing(match[0]);
    const end = rawStart + match[0].length - trimmed;

    // Edge case: a URL reduced to just the scheme "https://" / "http://"
    // (no host) — drop it entirely and treat the whole match as text to
    // avoid emitting an empty link. Rare but keeps the contract tidy.
    if (href.replace(/^https?:\/\//, "").length === 0) {
      match = URL_PATTERN.exec(text);
      continue;
    }

    if (rawStart > last) tokens.push({ type: "text", value: text.slice(last, rawStart) });
    tokens.push({ type: "link", href, text: href });
    last = end;
    match = URL_PATTERN.exec(text);
  }

  if (last < text.length) tokens.push({ type: "text", value: text.slice(last) });
  return tokens;
}

/**
 * Return the first http(s) URL found in `text`, with the same trailing
 * punctuation trimming as `tokenizeLinks`, or null when there is none.
 *
 * Used to decide whether to render the small "open in new tab" icon next to
 * a button-shaped option whose label happens to contain a URL.
 */
export function firstUrl(text) {
  if (typeof text !== "string" || text.length === 0) return null;
  URL_PATTERN.lastIndex = 0;
  const match = URL_PATTERN.exec(text);
  if (!match) return null;
  const { href } = peelTrailing(match[0]);
  return href.replace(/^https?:\/\//, "").length > 0 ? href : null;
}
