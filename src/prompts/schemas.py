"""JSON schemas for structured output via output_config."""

from __future__ import annotations

INTENT_SCHEMA: dict[str, object] = {
    "type": "json_schema",
    "json_schema": {
        "name": "intent_classification",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": [
                        "billing",
                        "shipping",
                        "general",
                        "returns",
                        "account",
                        "technical",
                        "complex",
                    ],
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                },
                "tier": {
                    "type": "integer",
                    "enum": [1, 2, 3],
                },
                "reasoning": {
                    "type": "string",
                },
            },
            "required": ["category", "confidence", "tier", "reasoning"],
            "additionalProperties": False,
        },
    },
}

RESPONSE_SCHEMA: dict[str, object] = {
    "type": "json_schema",
    "json_schema": {
        "name": "support_response",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                },
                "tier": {
                    "type": "integer",
                    "enum": [1, 2, 3],
                },
                "tools_used": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                },
                "needs_escalation": {
                    "type": "boolean",
                },
                "suggested_actions": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": [
                "content",
                "tier",
                "tools_used",
                "confidence",
                "needs_escalation",
                "suggested_actions",
            ],
            "additionalProperties": False,
        },
    },
}
