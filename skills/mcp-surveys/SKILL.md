---
name: mcp-surveys
description: Use this skill when an agent needs to ask a human several structured questions and receive answers back through MCP.
---

# MCP Surveys

Use `mcp-surveys` when chat text is a poor fit for collecting human input. Prefer compact, tappable survey questions.

## When to Use

- Use `single_choice` for one decision.
- Use `multiple_choice` when several options may apply.
- Use `ranking` when order matters.
- Use `matching` when the person should connect left-side items to right-side items.
- Use `scale` when the person should express confidence, intensity, risk, fit, or any other degree.
- Use `binary_tradeoff` when two competing theses are both valid and the human should lean between A and B. Pick `signal`, `mono`, or `calm`, or use `custom` with both hex colors.
- Use `text` only when the answer cannot be represented by the structured formats above.

Do not create a survey for one simple yes/no question unless the user experience clearly benefits from a link.

## Flow

1. Call `create_survey`.
2. Send only `public_url` to the human and mention that the link expires.
3. Keep `survey_id` and `result_token` private.
4. After the human says they are done, call `get_survey_summary`.
5. If completion is partial, decide whether to ask them to finish or use the available answers.
6. Call `get_survey_answers`, `get_question_answer`, or `get_survey_export` as needed.

## Editing

Use `edit_survey` only for small corrections to an active survey, such as fixing one question or one option. If the survey needs a substantial rewrite, call `create_survey` again and send a new link.

## Limits

Default limits are 60 created surveys per client IP per hour, 50 questions per survey, and 128 KiB per create request. Keep surveys short anyway; the UI is optimized for quick decisions.
