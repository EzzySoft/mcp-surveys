from __future__ import annotations

from typing import Any


def question_schema() -> dict[str, Any]:
    return {
        "single_choice": {"value": "option_id", "custom_options": {"custom:id": "text"}},
        "multiple_choice": {"value": ["option_id"], "custom_options": {"custom:id": "text"}},
        "ranking": {"value": ["first_option_id", "second_option_id"]},
        "matching": {"left_item_id": "right_item_id"},
        "scale": {"value": 75, "fields": {"min": 0, "max": 100, "step": 5, "min_label": "Guess", "max_label": "Certain"}},
        "color_choice": {
            "value": "option_id",
            "fields": {"options": [{"id": "blue", "text": "Ocean blue", "color": "#2563eb"}]},
        },
        "binary_tradeoff": {
            "value": 35,
            "fields": {
                "left": [{"id": "A", "text": "Ship this week"}],
                "right": [{"id": "B", "text": "Reduce launch risk"}],
                "theme": "signal | mono | calm | custom; custom requires both colors",
                "left_color": "#c6533d",
                "right_color": "#126a74",
            },
        },
        "text": "Use only when other types cannot express the answer.",
        "limits": {
            "questions": 50,
            "options_per_list": 50,
            "create_payload_bytes": "configured by MAX_CREATE_SURVEY_BYTES",
        },
    }
