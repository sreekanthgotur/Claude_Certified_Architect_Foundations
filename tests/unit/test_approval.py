"""Tests for approval gates (src/tools/approval.py)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.tools.approval import ApprovalGate


@pytest.fixture
def gate() -> ApprovalGate:
    return ApprovalGate(
        dollar_threshold=100.0,
        max_account_mutations_per_session=3,
    )


# ------------------------------------------------------------------
# High-risk writes
# ------------------------------------------------------------------

@pytest.mark.unit
def test_high_risk_write_requires_confirmation(gate: ApprovalGate) -> None:
    result = gate.check(
        tool_name="initiate_return",
        tool_input={"order_id": "ORD-1", "refund_amount": 200.0},
        risk_level="high",
        session_mutations=0,
    )
    assert result.requires_approval is True


@pytest.mark.unit
def test_subscription_cancel_requires_confirmation(gate: ApprovalGate) -> None:
    result = gate.check(
        tool_name="update_subscription",
        tool_input={"action": "cancel"},
        risk_level="high",
        session_mutations=0,
    )
    assert result.requires_approval is True


# ------------------------------------------------------------------
# Dollar threshold
# ------------------------------------------------------------------

@pytest.mark.unit
def test_refund_above_threshold_flagged(gate: ApprovalGate) -> None:
    result = gate.check(
        tool_name="initiate_return",
        tool_input={"order_id": "ORD-1", "refund_amount": 150.0},
        risk_level="high",
        session_mutations=0,
    )
    assert result.requires_approval is True
    assert "dollar_threshold" in result.reason


@pytest.mark.unit
def test_refund_exactly_at_threshold(gate: ApprovalGate) -> None:
    """$100 exactly is at threshold — high-risk still needs approval but no dollar flag."""
    result = gate.check(
        tool_name="initiate_return",
        tool_input={"order_id": "ORD-1", "refund_amount": 100.0},
        risk_level="high",
        session_mutations=0,
    )
    assert result.requires_approval is True


@pytest.mark.unit
def test_refund_below_threshold_still_high_risk(gate: ApprovalGate) -> None:
    """Below dollar threshold but still a high-risk write — needs approval."""
    result = gate.check(
        tool_name="initiate_return",
        tool_input={"order_id": "ORD-1", "refund_amount": 50.0},
        risk_level="high",
        session_mutations=0,
    )
    assert result.requires_approval is True
    assert "dollar_threshold" not in (result.reason or "")


# ------------------------------------------------------------------
# Rate limiting
# ------------------------------------------------------------------

@pytest.mark.unit
def test_first_mutation_allowed(gate: ApprovalGate) -> None:
    result = gate.check(
        tool_name="update_subscription",
        tool_input={"action": "upgrade"},
        risk_level="high",
        session_mutations=0,
    )
    assert result.blocked is False


@pytest.mark.unit
def test_third_mutation_allowed(gate: ApprovalGate) -> None:
    result = gate.check(
        tool_name="update_subscription",
        tool_input={"action": "upgrade"},
        risk_level="high",
        session_mutations=2,
    )
    assert result.blocked is False


@pytest.mark.unit
def test_fourth_mutation_blocked(gate: ApprovalGate) -> None:
    result = gate.check(
        tool_name="update_subscription",
        tool_input={"action": "upgrade"},
        risk_level="high",
        session_mutations=3,
    )
    assert result.blocked is True
    assert "rate_limit" in result.reason


@pytest.mark.unit
def test_fifth_mutation_also_blocked(gate: ApprovalGate) -> None:
    result = gate.check(
        tool_name="update_subscription",
        tool_input={"action": "downgrade"},
        risk_level="high",
        session_mutations=4,
    )
    assert result.blocked is True


# ------------------------------------------------------------------
# Read-only bypass
# ------------------------------------------------------------------

@pytest.mark.unit
def test_read_only_tool_no_approval(gate: ApprovalGate) -> None:
    result = gate.check(
        tool_name="lookup_order",
        tool_input={"order_id": "ORD-1"},
        risk_level="low",
        session_mutations=0,
    )
    assert result.requires_approval is False
    assert result.blocked is False


@pytest.mark.unit
def test_search_tool_no_approval(gate: ApprovalGate) -> None:
    result = gate.check(
        tool_name="search_knowledge_base",
        tool_input={"query": "return policy"},
        risk_level="low",
        session_mutations=0,
    )
    assert result.requires_approval is False


# ------------------------------------------------------------------
# Audit logging
# ------------------------------------------------------------------

@pytest.mark.unit
def test_medium_risk_write_audit_logged(gate: ApprovalGate) -> None:
    """Medium-risk writes are audit-logged but not approval-gated."""
    result = gate.check(
        tool_name="create_ticket",
        tool_input={"subject": "Need help"},
        risk_level="medium",
        session_mutations=0,
    )
    assert result.requires_approval is False
    assert result.audit_log is True


@pytest.mark.unit
def test_escalation_audit_logged(gate: ApprovalGate) -> None:
    result = gate.check(
        tool_name="escalate_to_human",
        tool_input={"reason": "customer_request"},
        risk_level="medium",
        session_mutations=0,
    )
    assert result.requires_approval is False
    assert result.audit_log is True


@pytest.mark.unit
def test_override_logging(gate: ApprovalGate) -> None:
    """When approval is granted (override), it should be logged."""
    result = gate.check(
        tool_name="initiate_return",
        tool_input={"order_id": "ORD-1", "refund_amount": 500.0},
        risk_level="high",
        session_mutations=0,
    )
    assert result.requires_approval is True

    override_record = gate.record_override(
        tool_name="initiate_return",
        tool_input={"order_id": "ORD-1", "refund_amount": 500.0},
        approved_by="customer",
    )
    assert override_record["tool_name"] == "initiate_return"
    assert override_record["approved_by"] == "customer"
    assert "timestamp" in override_record
