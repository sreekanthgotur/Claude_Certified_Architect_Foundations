"""Integration tests for the escalation engine."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.orchestrator.escalation import EscalationEngine
from src.orchestrator.models import (
    ClassificationResult,
    ConversationState,
    EscalationPayload,
    Intent,
    Tier,
)


@pytest.fixture
def escalation_engine(mock_anthropic_client: MagicMock) -> EscalationEngine:
    return EscalationEngine(client=mock_anthropic_client)


# ------------------------------------------------------------------
# Escalation triggers
# ------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_low_confidence_triggers_escalation(
    escalation_engine: EscalationEngine,
) -> None:
    """Confidence below 0.6 should trigger immediate escalation."""
    classification = ClassificationResult(
        intent=Intent.UNKNOWN,
        confidence=0.45,
        tier=Tier.TIER_1,
        entities=[],
    )
    state = ConversationState(
        session_id="sess_001",
        customer_id="cust_12345",
        messages=[{"role": "user", "content": "garbled request"}],
        current_tier=Tier.TIER_1,
    )

    should_escalate = escalation_engine.should_escalate(
        classification=classification,
        conversation_state=state,
    )

    assert should_escalate is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_negative_sentiment_triggers_escalation(
    escalation_engine: EscalationEngine,
) -> None:
    """Detected customer frustration should trigger escalation."""
    state = ConversationState(
        session_id="sess_001",
        customer_id="cust_12345",
        messages=[
            {"role": "user", "content": "This is the THIRD time I'm calling about this!"},
            {"role": "assistant", "content": "I understand your frustration..."},
            {
                "role": "user",
                "content": "I want to speak to a manager RIGHT NOW. "
                "This is completely unacceptable!",
            },
        ],
        current_tier=Tier.TIER_2,
        sentiment_score=-0.8,
    )
    classification = ClassificationResult(
        intent=Intent.ORDER_STATUS,
        confidence=0.85,
        tier=Tier.TIER_2,
        entities=[],
    )

    should_escalate = escalation_engine.should_escalate(
        classification=classification,
        conversation_state=state,
    )

    assert should_escalate is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_policy_gated_action_triggers_escalation(
    escalation_engine: EscalationEngine,
) -> None:
    """Account deletion is policy-gated — always escalate."""
    classification = ClassificationResult(
        intent=Intent.ACCOUNT_DELETION,
        confidence=0.99,
        tier=Tier.TIER_2,
        entities=["account", "delete"],
    )
    state = ConversationState(
        session_id="sess_001",
        customer_id="cust_12345",
        messages=[{"role": "user", "content": "Delete my account."}],
        current_tier=Tier.TIER_2,
    )

    should_escalate = escalation_engine.should_escalate(
        classification=classification,
        conversation_state=state,
    )

    assert should_escalate is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_task_budget_exhaustion_triggers_escalation(
    escalation_engine: EscalationEngine,
) -> None:
    """Budget near exhaustion without resolution should trigger escalation."""
    state = ConversationState(
        session_id="sess_001",
        customer_id="cust_12345",
        messages=[{"role": "user", "content": "Complex issue"}],
        current_tier=Tier.TIER_3,
        budget_used=19_500,
        budget_total=20_000,
    )
    classification = ClassificationResult(
        intent=Intent.COMPLEX_INVESTIGATION,
        confidence=0.90,
        tier=Tier.TIER_3,
        entities=[],
    )

    should_escalate = escalation_engine.should_escalate(
        classification=classification,
        conversation_state=state,
    )

    assert should_escalate is True


# ------------------------------------------------------------------
# Escalation payload completeness
# ------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_escalation_payload_contains_required_fields(
    escalation_engine: EscalationEngine,
    mock_anthropic_client: MagicMock,
) -> None:
    """Escalation payload must contain all handoff context."""
    mock_anthropic_client.messages.create = AsyncMock(
        return_value=MagicMock(
            content=[MagicMock(type="text", text="Summary of the conversation...")],
            usage=MagicMock(input_tokens=500, output_tokens=100),
        )
    )

    state = ConversationState(
        session_id="sess_001",
        customer_id="cust_12345",
        messages=[
            {"role": "user", "content": "I need to delete my account."},
        ],
        current_tier=Tier.TIER_2,
        tool_history=[
            {
                "tool": "lookup_account",
                "input": {"customer_id": "cust_12345"},
                "result": {"tier": "gold"},
            }
        ],
        retrieved_documents=[
            {"title": "Account Policy", "content": "Accounts can be..."}
        ],
        customer_profile={"customer_id": "cust_12345", "tier": "gold"},
    )

    payload = await escalation_engine.build_payload(
        conversation_state=state,
        reason="policy_gated",
    )

    assert isinstance(payload, EscalationPayload)
    assert payload.session_id == "sess_001"
    assert payload.customer_id == "cust_12345"
    assert payload.reason == "policy_gated"
    assert payload.summary is not None and len(payload.summary) > 0
    assert payload.conversation_history is not None
    assert payload.tool_history is not None
    assert payload.customer_profile is not None
    assert payload.agent_assessment is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_no_escalation_on_normal_request(
    escalation_engine: EscalationEngine,
) -> None:
    """Normal high-confidence request should NOT trigger escalation."""
    classification = ClassificationResult(
        intent=Intent.ORDER_STATUS,
        confidence=0.95,
        tier=Tier.TIER_2,
        entities=["ORD-123"],
    )
    state = ConversationState(
        session_id="sess_001",
        customer_id="cust_12345",
        messages=[{"role": "user", "content": "Where is my order?"}],
        current_tier=Tier.TIER_2,
    )

    should_escalate = escalation_engine.should_escalate(
        classification=classification,
        conversation_state=state,
    )

    assert should_escalate is False
