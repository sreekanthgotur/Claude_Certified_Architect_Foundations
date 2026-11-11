"""Server-side tool definitions for Claude's built-in capabilities."""

from __future__ import annotations

web_search_tool: dict[str, object] = {
    "type": "web_search_20260209",
    "name": "web_search",
    "max_uses": 5,
    "allowed_domains": ["support.example.com", "docs.example.com"],
}

web_fetch_tool: dict[str, object] = {
    "type": "web_fetch_20260209",
    "name": "web_fetch",
    "max_uses": 3,
    "allowed_domains": ["support.example.com", "docs.example.com"],
}

code_execution_tool: dict[str, object] = {
    "type": "code_execution_20250522",
    "name": "code_execution",
}
