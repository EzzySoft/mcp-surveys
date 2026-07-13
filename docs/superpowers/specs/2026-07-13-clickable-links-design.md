# Clickable links on the survey page

**Date:** 2026-07-13
**Status:** Implemented
**Scope:** Client-side only (browser UI for `/s/{survey_id}`)

## Problem

When an agent embeds an `http(s)://…` URL into any text field of a survey
(title, description, question prompt, option text, scale labels, tradeoff
theses), the survey page rendered that URL as inert plain text. Users could
not click through to the referenced resource.

Root cause: every user-visible string was assigned via `Element.textContent`
in `src/mcp_surveys/web/assets/app.js`, which by definition cannot produce
clickable anchors.

## Goal

Any `http(s)://…` URL that appears in survey text must render as a clickable
link that opens in a new tab. `javascript:` / `data:` URIs must never become
links. Existing interactive controls (choice buttons, ranking rows, matching
selects) must keep working unchanged.

## Design

### Layer

Pure client-side change. The server, API, models, storage, CLI, and skill
text are not touched — the same field payloads flow from the server (and for
E2EE surveys, are decrypted in the browser before render), so linkifying in
the render layer covers both plaintext and E2EE modes with one code path.

### Where links appear

Inline linkification (text rendered as a mix of text nodes and `<a>`):

- Survey title (`#title`)
- Survey description (`#description`)
- Question prompt (`.question h2`)
- Ranking option labels (`.rank-label`)
- Matching left-side labels (`.match-row strong`)
- Scale min/max labels (`.scale-value-row span`)
- Tradeoff definition titles (`.tradeoff-definition-copy strong`)
- Tradeoff axis titles (`.tradeoff-axis-title`)

### Where an icon-link is used instead

Inside `<button>` elements, nesting an `<a>` is invalid HTML and a full link
would conflict with the click that selects the option. For these we keep the
label as plain text and, when the label contains a URL, append a small `↗`
icon-link beside it:

- `single_choice` and `multiple_choice` option buttons (`.choice`)

The icon-link:

- Opens the first URL found in the option text in a new tab.
- Calls `event.stopPropagation()` on click so selecting the option is not
  triggered when the user clicks the icon.
- Gets class `choice--has-link` on the parent button, which switches the
  button grid from `minmax(0,1fr) 24px` to `minmax(0,1fr) auto 24px` so the
  icon, label, and selection mark each get their own column.

### Where links are deliberately not rendered

- `color_choice` option labels — these name colors; a URL there is
  meaningless noise.
- Matching right-side `<option>` elements — they live inside a `<select>`
  and an `<a>` cannot be embedded there. The right-side text stays plain.

### Text processing — `assets/text.mjs`

A new dependency-free ES module with two pure functions:

- `tokenizeLinks(text)` → ordered array of
  `{ type: "text", value }` and `{ type: "link", href, text }` tokens.
  Only `http(s)://` URLs match (regex `https?:\/\/…`), so `javascript:` and
  `data:` schemes cannot become links. Trailing prose punctuation
  (`. , ; : ! ? ' "`) and unbalanced closing brackets (`) ] }`) are peeled
  off the URL and left as text. Balanced brackets inside the URL
  (e.g. `https://en.wikipedia.org/wiki/Foo_(bar)`) are preserved.
- `firstUrl(text)` → the first URL found (same trimming rules), or `null`.
  Used to decide whether to render the `↗` icon next to a button label.

The module is `.mjs` so Node treats it as ESM without a `package.json`
(which the web `assets/` directory does not have) and browsers load it as
a module via `import`. Starlette's static frontend serves `.mjs` with the
`text/javascript` MIME type, so both runtimes are satisfied.

### XSS safety

No `innerHTML` is used for user-controlled text. Link and text tokens are
both created via `document.createTextNode` and `document.createElement("a")`,
which auto-escape. The URL regex requires an `http(s)` scheme, so
`javascript:` URIs cannot become clickable. The link's `href` is the exact
substring matched by the regex (after trailing-punctuation trimming), never
an attacker-controlled attribute string.

### E2EE interaction

For encrypted surveys, the spec is decrypted in
`decryptSecureSurvey()` which overwrites `state.survey.title`,
`description`, and `questions` with plaintext *before* `renderSurvey()` /
`renderQuestion()` run. Linkification happens in the render step, so it
sees plaintext in both modes. No crypto code changed.

### Files

- new `src/mcp_surveys/web/assets/text.mjs` — pure tokenizers.
- new `src/mcp_surveys/web/test/text.test.mjs` — `node --test` unit tests.
- edit `src/mcp_surveys/web/assets/app.js` — `import` from `text.mjs`,
  `renderLinkified(el, text)` helper, replacement of `textContent`
  assignments for all inline-linkified fields, rewrite of `optionButton`
  to add the `↗` icon-link with `stopPropagation`.
- edit `src/mcp_surveys/web/assets/styles.css` — base `<a>` styling,
  `overflow-wrap: anywhere` for linkified text containers, `.choice-link`
  and `.choice--has-link` rules.

### Tests

- `node --test src/mcp_surveys/web/test/text.test.mjs` — 15 tests covering
  tokenize/firstUrl: plain text, empty input, single URL, URL in prose,
  trailing punctuation (`. , ; : ! ?`), unbalanced closing bracket,
  balanced parens inside URL, multiple URLs, `javascript:` rejection,
  `http://` acceptance, `firstUrl` null cases.
- `uv run --extra dev pytest` — existing 22 tests stay green (no server
  contract changed).
- Manual Playwright verification on a mock page: 8 links render across
  title/description/prompt/ranking/scale, icon-link in choice button
  opens a new tab, `stopPropagation` prevents the option from being
  selected on icon click, grid layout switches to 3 columns.

### Out of scope

- Markdown link syntax (`[label](url)`) — the link text equals the URL.
- Email addresses or `tel:` links.
- Linkifying the agent's chat output or the CLI's stdout JSON — this
  change is strictly about the human-facing survey page.
- Color-choice labels and matching right-side options (see above).
