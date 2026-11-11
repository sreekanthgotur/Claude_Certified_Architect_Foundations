"""Orders MCP server configuration."""

from __future__ import annotations

import os


def orders_server_config() -> dict[str, object]:
    """Return the MCP server config for the orders system."""
    return {
        "url": os.getenv("MCP_ORDERS_URL", "http://localhost:3002/mcp"),
        "name": "orders",
        "authorization_token": os.getenv("MCP_ORDERS_API_KEY", ""),
        "tool_configuration": {
            "enabled": True,
            "allowed_tools": [
                "get_order",
                "list_orders",
                "track_shipment",
                "process_return",
            ],
        },
    }
