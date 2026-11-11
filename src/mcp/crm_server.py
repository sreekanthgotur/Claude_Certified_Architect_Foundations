"""CRM MCP server configuration."""

from __future__ import annotations

import os


def crm_server_config() -> dict[str, object]:
    """Return the MCP server config for the CRM system."""
    return {
        "url": os.getenv("MCP_CRM_URL", "http://localhost:3001/mcp"),
        "name": "crm",
        "authorization_token": os.getenv("MCP_CRM_API_KEY", ""),
        "tool_configuration": {
            "enabled": True,
            "allowed_tools": [
                "get_customer",
                "update_customer",
                "list_interactions",
            ],
        },
    }
