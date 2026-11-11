"""Tests for tool definitions and approval hooks (src/tools/)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from src.tools.approval import ApprovalGate, ApprovalRequired
from src.tools.order_tools import LOOKUP_ORDER_SCHEMA, INITIATE_RETURN_SCHEMA
from src.tools.account_tools import LOOKUP_ACCOUNT_SCHEMA, UPDATE_SUBSCRIPTION_SCHEMA
from src.tools.knowledge_tools import SEARCH_KNOWLEDGE_BASE_SCHEMA
from src.tools.support_tools import (
    CREATE_TICKET_SCHEMA,
    ESCALATE_TO_HUMAN_SCHEMA,
    SEARCH_TICKETS_SCHEMA,
)


# ------------------------------------------------------------------
# Schema validation
# ------------------------------------------------------------------

ALL_TOOL_SCHEMAS: list[dict[str, Any]] = [
    LOOKUP_ORDER_SCHEMA,
    LOOKUP_ACCOUNT_SCHEMA,
    SEARCH_KNOWLEDGE_BASE_SCHEMA,
    SEARCH_TICKETS_SCHEMA,
    CREATE_TICKET_SCHEMA,
    INITIATE_RETURN_SCHEMA,
    UPDATE_SUBSCRIPTION_SCHEMA,
    ESCALATE_TO_HUMAN_SCHEMA,
]


@pytest.mark.unit
@pytest.mark.parametrize("schema", ALL_TOOL_SCHEMAS, ids=lambda s: s["name"])
def test_tool_schema_has_strict_mode(schema: dict[str, Any]) -> None:
    """Every tool definition must have strict: true."""
    assert schema.get("strict") is True, f"{schema['name']} missing strict: true"


@pytest.mark.unit
@pytest.mark.parametrize("schema", ALL_TOOL_SCHEMAS, ids=lambda s: s["name"])
def test_tool_schema_no_additional_properties(schema: dict[str, Any]) -> None:
    """Every input_schema must set additionalProperties: false."""
    input_schema = schema.get("input_schema", {})
    assert input_schema.get("additionalProperties") is False, (
        f"{schema['name']} input_schema missing additionalProperties: false"
    )


@pytest.mark.unit
@pytest.mark.parametrize("schema", ALL_TOOL_SCHEMAS, ids=lambda s: s["name"])
def test_tool_schema_has_required_fields(schema: dict[str, Any]) -> None:
    """Every input_schema must have an explicit required array."""
    input_schema = schema.get("input_schema", {})
    assert "required" in input_schema, (
        f"{schema['name']} input_schema missing required array"
    )


# ------------------------------------------------------------------
# Risk levels
# ------------------------------------------------------------------

@pytest.mark.unit
def test_read_tools_are_low_risk(mock_tool_registry: dict[str, dict[str, Any]]) -> None:
    read_tools = ["lookup_order", "lookup_account", "search_knowledge_base", "search_tickets"]
    for tool_name in read_tools:
        assert mock_tool_registry[tool_name]["risk"] == "low"
        assert mock_tool_registry[tool_name]["approval_required"] is False


@pytest.mark.unit
def test_write_tools_have_correct_risk(mock_tool_registry: dict[str, dict[str, Any]]) -> None:
    assert mock_tool_registry["initiate_return"]["risk"] == "high"
    assert mock_tool_registry["update_subscription"]["risk"] == "high"
    assert mock_tool_registry["create_ticket"]["risk"] == "medium"
    assert mock_tool_registry["escalate_to_human"]["risk"] == "medium"


# ------------------------------------------------------------------
# Approval gate
# ------------------------------------------------------------------

@pytest.fixture
def approval_gate() -> ApprovalGate:
    return ApprovalGate(
        dollar_threshold=100.0,
        max_account_mutations_per_session=3,
    )


@pytest.mark.unit
def test_high_risk_write_requires_approval(approval_gate: ApprovalGate) -> None:
    result = approval_gate.check(
        tool_name="update_subscription",
        tool_input={"action": "cancel"},
        risk_level="high",
        session_mutations=0,
    )
    assert result.requires_approval is True


@pytest.mark.unit
def test_low_risk_read_bypasses_approval(approval_gate: ApprovalGate) -> None:
    result = approval_gate.check(
        tool_name="lookup_order",
        tool_input={"order_id": "ORD-123"},
        risk_level="low",
        session_mutations=0,
    )
    assert result.requires_approval is False


@pytest.mark.unit
def test_refund_above_threshold_requires_approval(approval_gate: ApprovalGate) -> None:
    result = approval_gate.check(
        tool_name="initiate_return",
        tool_input={"order_id": "ORD-123", "refund_amount": 150.00},
        risk_level="high",
        session_mutations=0,
    )
    assert result.requires_approval is True
    assert "dollar_threshold" in result.reason


@pytest.mark.unit
def test_refund_at_or_below_threshold_passes(approval_gate: ApprovalGate) -> None:
    result = approval_gate.check(
        tool_name="initiate_return",
        tool_input={"order_id": "ORD-123", "refund_amount": 100.00},
        risk_level="high",
        session_mutations=0,
    )
    assert result.requires_approval is True  # still high-risk write


@pytest.mark.unit
def test_refund_small_amount_no_dollar_gate(approval_gate: ApprovalGate) -> None:
    result = approval_gate.check(
        tool_name="initiate_return",
        tool_input={"order_id": "ORD-123", "refund_amount": 25.00},
        risk_level="high",
        session_mutations=0,
    )
    assert result.requires_approval is True  # high-risk always needs approval
    assert "dollar_threshold" not in (result.reason or "")


@pytest.mark.unit
def test_rate_limiting_blocks_fourth_mutation(approval_gate: ApprovalGate) -> None:
    """Max 3 account mutations per session. The 4th is blocked outright."""
    result = approval_gate.check(
        tool_name="update_subscription",
        tool_input={"action": "upgrade"},
        risk_level="high",
        session_mutations=3,
    )
    assert result.blocked is True
    assert "rate_limit" in result.reason


@pytest.mark.unit
def test_rate_limiting_allows_third_mutation(approval_gate: ApprovalGate) -> None:
    result = approval_gate.check(
        tool_name="update_subscription",
        tool_input={"action": "upgrade"},
        risk_level="high",
        session_mutations=2,
    )
    assert result.blocked is False


@pytest.mark.unit
def test_medium_risk_write_no_approval(approval_gate: ApprovalGate) -> None:
    """Medium-risk writes (create_ticket, escalate) are audit-logged, not approval-gated."""
    result = approval_gate.check(
        tool_name="create_ticket",
        tool_input={"subject": "Help needed"},
        risk_level="medium",
        session_mutations=0,
    )
    assert result.requires_approval is False
    assert result.audit_log is True
