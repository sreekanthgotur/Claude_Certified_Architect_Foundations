"""Knowledge base MCP server configuration."""

from __future__ import annotations

import os


def knowledge_server_config() -> dict[str, object]:
    """Return the MCP server config for the knowledge base."""
    return {
        "url": os.getenv("MCP_KNOWLEDGE_URL", "http://localhost:3003/mcp"),
        "name": "knowledge",
        "tool_configuration": {
            "enabled": True,
            "allowed_tools": [
                "search_articles",
                "get_article",
                "list_categories",
            ],
        },
    }
