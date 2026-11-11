"""Billing MCP server configuration."""

from __future__ import annotations

import os


def billing_server_config() -> dict[str, object]:
    """Return the MCP server config for the billing system."""
    return {
        "url": os.getenv("MCP_BILLING_URL", "http://localhost:3004/mcp"),
        "name": "billing",
        "authorization_token": os.getenv("MCP_BILLING_API_KEY", ""),
        "tool_configuration": {
            "enabled": True,
            "allowed_tools": [
                "get_invoice",
                "list_charges",
                "apply_credit",
                "get_subscription",
            ],
        },
    }
