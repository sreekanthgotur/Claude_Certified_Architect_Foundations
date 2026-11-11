"""Shared pytest fixtures for the Enterprise AI Customer Support Agent."""

from __future__ import annotations

import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.orchestrator.models import (
    ClassificationResult,
    ConversationState,
    EscalationPayload,
    Intent,
    Tier,
)


@pytest.fixture
def mock_anthropic_client() -> MagicMock:
    """Mock anthropic.Anthropic client with common method stubs."""
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock()
    client.messages.stream = MagicMock()
    client.messages.parse = AsyncMock()
    client.messages.count_tokens = AsyncMock(
        return_value=MagicMock(input_tokens=1500)
    )
    client.beta = MagicMock()
    client.beta.messages = MagicMock()
    client.beta.messages.tool_runner = AsyncMock()
    return client


@pytest.fixture
def mock_conversation_state() -> ConversationState:
    """A mid-conversation state with 3 prior messages."""
    return ConversationState(
        session_id="sess_test_001",
        customer_id="cust_12345",
        messages=[
            {"role": "user", "content": "Hi, I need help with my order."},
            {
                "role": "assistant",
                "content": "Hello! I'd be happy to help. Could you provide your order number?",
            },
            {"role": "user", "content": "It's ORD-98765."},
        ],
        current_tier=Tier.TIER_2,
        tool_calls_this_session=1,
        account_mutations_this_session=0,
        total_input_tokens=2400,
    )


@pytest.fixture
def sample_customer_message() -> dict[str, str]:
    """A typical customer support message."""
    return {
        "role": "user",
        "content": "I placed an order last week and it still hasn't arrived. "
        "The tracking number shows it's stuck in transit. Can you help?",
    }


@pytest.fixture
def sample_classification_result() -> ClassificationResult:
    """A high-confidence Tier 2 classification."""
    return ClassificationResult(
        intent=Intent.ORDER_STATUS,
        confidence=0.94,
        tier=Tier.TIER_2,
        entities=["order", "tracking", "transit"],
    )


@pytest.fixture
def sample_order() -> dict[str, Any]:
    """A mock order object as returned by the CRM/orders MCP server."""
    return {
        "order_id": "ORD-98765",
        "customer_id": "cust_12345",
        "status": "in_transit",
        "items": [
            {
                "sku": "WIDGET-001",
                "name": "Premium Widget",
                "quantity": 2,
                "price": 29.99,
            }
        ],
        "total": 59.98,
        "placed_at": "2026-11-04T10:30:00Z",
        "tracking_number": "1Z999AA10123456784",
        "carrier": "UPS",
        "estimated_delivery": "2026-11-12",
    }


@pytest.fixture
def sample_ticket() -> dict[str, Any]:
    """A mock support ticket as stored in the CRM."""
    return {
        "ticket_id": "TKT-54321",
        "customer_id": "cust_12345",
        "category": "shipping",
        "subject": "Order stuck in transit",
        "status": "open",
        "created_at": "2026-11-10T14:00:00Z",
        "priority": "medium",
        "description": "Customer reports order ORD-98765 has not arrived. "
        "Tracking shows stuck in transit since Nov 8.",
    }


@pytest.fixture
def sample_closed_ticket() -> dict[str, Any]:
    """A closed support ticket — should be excluded from dedup matching."""
    return {
        "ticket_id": "TKT-11111",
        "customer_id": "cust_12345",
        "category": "shipping",
        "subject": "Previous shipping delay",
        "status": "closed",
        "created_at": "2026-10-01T09:00:00Z",
        "resolved_at": "2026-10-03T11:00:00Z",
        "priority": "low",
        "description": "Resolved shipping delay from October.",
    }


@pytest.fixture
def sample_escalation_payload(
    mock_conversation_state: ConversationState,
) -> EscalationPayload:
    """A complete escalation payload for handoff to a human agent."""
    return EscalationPayload(
        session_id=mock_conversation_state.session_id,
        customer_id=mock_conversation_state.customer_id,
        reason="low_confidence",
        summary="Customer asking about a complex billing dispute involving "
        "multiple orders and a promotional discount that was not applied.",
        conversation_history=mock_conversation_state.messages,
        tool_history=[
            {
                "tool": "lookup_order",
                "input": {"order_id": "ORD-98765"},
                "result": {"status": "delivered"},
            }
        ],
        retrieved_documents=[],
        customer_profile={
            "customer_id": "cust_12345",
            "tier": "gold",
            "account_age_days": 730,
        },
        agent_assessment="Unable to resolve with available tools. "
        "Customer's situation involves cross-order promotional credit "
        "that requires manual review.",
    )


@pytest.fixture
def mock_tool_registry() -> dict[str, dict[str, Any]]:
    """Tool registry matching config/tools.yaml."""
    return {
        "lookup_order": {
            "type": "read",
            "risk": "low",
            "approval_required": False,
        },
        "lookup_account": {
            "type": "read",
            "risk": "low",
            "approval_required": False,
        },
        "search_knowledge_base": {
            "type": "read",
            "risk": "low",
            "approval_required": False,
        },
        "search_tickets": {
            "type": "read",
            "risk": "low",
            "approval_required": False,
        },
        "create_ticket": {
            "type": "write",
            "risk": "medium",
            "approval_required": False,
        },
        "initiate_return": {
            "type": "write",
            "risk": "high",
            "approval_required": True,
            "dollar_threshold": 100,
        },
        "update_subscription": {
            "type": "write",
            "risk": "high",
            "approval_required": True,
        },
        "escalate_to_human": {
            "type": "write",
            "risk": "medium",
            "approval_required": False,
        },
    }
