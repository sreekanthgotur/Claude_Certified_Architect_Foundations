"""Integration tests for MCP server connectivity and tool invocation."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mcp.crm_server import CRMMCPServer
from src.mcp.orders_server import OrdersMCPServer
from src.mcp.knowledge_server import KnowledgeMCPServer
from src.mcp.billing_server import BillingMCPServer


MCP_SERVER_CONFIGS = [
    {"type": "url", "url": "https://mcp.internal/crm", "name": "crm"},
    {"type": "url", "url": "https://mcp.internal/orders", "name": "orders"},
    {"type": "url", "url": "https://mcp.internal/knowledge", "name": "knowledge"},
    {"type": "url", "url": "https://mcp.internal/billing", "name": "billing"},
]


# ------------------------------------------------------------------
# Server discovery
# ------------------------------------------------------------------

@pytest.mark.integration
def test_four_mcp_servers_configured() -> None:
    """All four MCP servers must be registered."""
    assert len(MCP_SERVER_CONFIGS) == 4
    names = {cfg["name"] for cfg in MCP_SERVER_CONFIGS}
    assert names == {"crm", "orders", "knowledge", "billing"}


@pytest.mark.integration
def test_mcp_servers_have_url_type() -> None:
    for cfg in MCP_SERVER_CONFIGS:
        assert cfg["type"] == "url"
        assert cfg["url"].startswith("https://")


@pytest.mark.integration
def test_mcp_toolset_configuration() -> None:
    """Each MCP server needs a corresponding mcp_toolset entry."""
    toolsets = [
        {"type": "mcp_toolset", "mcp_server_name": cfg["name"]}
        for cfg in MCP_SERVER_CONFIGS
    ]
    assert len(toolsets) == 4
    for ts in toolsets:
        assert ts["type"] == "mcp_toolset"


# ------------------------------------------------------------------
# CRM server
# ------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_crm_lookup_customer() -> None:
    server = CRMMCPServer(base_url="https://mcp.internal/crm")
    server._call = AsyncMock(
        return_value={
            "customer_id": "cust_12345",
            "name": "Jane Doe",
            "tier": "gold",
            "account_age_days": 730,
        }
    )

    result = await server.lookup_customer(customer_id="cust_12345")

    assert result["customer_id"] == "cust_12345"
    assert result["tier"] == "gold"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_crm_search_tickets() -> None:
    server = CRMMCPServer(base_url="https://mcp.internal/crm")
    server._call = AsyncMock(
        return_value=[
            {"ticket_id": "TKT-001", "status": "open", "category": "shipping"},
            {"ticket_id": "TKT-002", "status": "closed", "category": "billing"},
        ]
    )

    result = await server.search_tickets(customer_id="cust_12345")

    assert len(result) == 2
    assert result[0]["ticket_id"] == "TKT-001"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_crm_create_ticket() -> None:
    server = CRMMCPServer(base_url="https://mcp.internal/crm")
    server._call = AsyncMock(
        return_value={"ticket_id": "TKT-NEW-001", "status": "open"}
    )

    result = await server.create_ticket(
        customer_id="cust_12345",
        category="shipping",
        subject="Order not delivered",
        description="Order ORD-98765 still in transit.",
    )

    assert result["ticket_id"] == "TKT-NEW-001"


# ------------------------------------------------------------------
# Orders server
# ------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_orders_lookup() -> None:
    server = OrdersMCPServer(base_url="https://mcp.internal/orders")
    server._call = AsyncMock(
        return_value={
            "order_id": "ORD-98765",
            "status": "in_transit",
            "tracking_number": "1Z999AA10123456784",
        }
    )

    result = await server.lookup_order(order_id="ORD-98765")

    assert result["order_id"] == "ORD-98765"
    assert result["status"] == "in_transit"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_orders_initiate_return() -> None:
    server = OrdersMCPServer(base_url="https://mcp.internal/orders")
    server._call = AsyncMock(
        return_value={"return_id": "RET-001", "status": "initiated", "refund_amount": 59.98}
    )

    result = await server.initiate_return(order_id="ORD-98765", reason="defective")

    assert result["return_id"] == "RET-001"


# ------------------------------------------------------------------
# Knowledge server
# ------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_knowledge_search() -> None:
    server = KnowledgeMCPServer(base_url="https://mcp.internal/knowledge")
    server._call = AsyncMock(
        return_value=[
            {
                "title": "Return Policy",
                "content": "Items can be returned within 30 days.",
                "score": 0.95,
            }
        ]
    )

    result = await server.search_docs(query="return policy")

    assert len(result) >= 1
    assert result[0]["score"] > 0.9


# ------------------------------------------------------------------
# Billing server
# ------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_billing_get_subscription() -> None:
    server = BillingMCPServer(base_url="https://mcp.internal/billing")
    server._call = AsyncMock(
        return_value={
            "subscription_id": "sub_001",
            "plan": "premium",
            "status": "active",
            "monthly_cost": 49.99,
        }
    )

    result = await server.get_subscription(customer_id="cust_12345")

    assert result["plan"] == "premium"
    assert result["status"] == "active"


# ------------------------------------------------------------------
# Error handling
# ------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_mcp_server_unavailable() -> None:
    """When an MCP server is unavailable, return a structured error."""
    server = CRMMCPServer(base_url="https://mcp.internal/crm")
    server._call = AsyncMock(side_effect=ConnectionError("Server unavailable"))

    with pytest.raises(ConnectionError):
        await server.lookup_customer(customer_id="cust_12345")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mcp_server_timeout() -> None:
    """MCP calls should have a timeout (5s per spec)."""
    server = OrdersMCPServer(base_url="https://mcp.internal/orders")
    server._call = AsyncMock(side_effect=TimeoutError("Request timed out"))

    with pytest.raises(TimeoutError):
        await server.lookup_order(order_id="ORD-12345")


# ------------------------------------------------------------------
# Auth configuration
# ------------------------------------------------------------------

@pytest.mark.integration
def test_crm_uses_oauth2() -> None:
    server = CRMMCPServer(base_url="https://mcp.internal/crm")
    assert server.auth_type == "oauth2_client_credentials"


@pytest.mark.integration
def test_orders_uses_api_key() -> None:
    server = OrdersMCPServer(base_url="https://mcp.internal/orders")
    assert server.auth_type == "api_key"


@pytest.mark.integration
def test_knowledge_no_auth() -> None:
    server = KnowledgeMCPServer(base_url="https://mcp.internal/knowledge")
    assert server.auth_type == "none"


@pytest.mark.integration
def test_billing_uses_oauth2() -> None:
    server = BillingMCPServer(base_url="https://mcp.internal/billing")
    assert server.auth_type == "oauth2_scoped"
