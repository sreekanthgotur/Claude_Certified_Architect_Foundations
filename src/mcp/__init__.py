"""MCP server configurations for external service integration."""

from src.mcp.crm_server import crm_server_config
from src.mcp.orders_server import orders_server_config
from src.mcp.knowledge_server import knowledge_server_config
from src.mcp.billing_server import billing_server_config

MCP_SERVERS: dict[str, dict[str, object]] = {
    "crm": crm_server_config(),
    "orders": orders_server_config(),
    "knowledge": knowledge_server_config(),
    "billing": billing_server_config(),
}

__all__ = [
    "MCP_SERVERS",
    "crm_server_config",
    "orders_server_config",
    "knowledge_server_config",
    "billing_server_config",
]
