"""Tests for the intent classifier / router (src/orchestrator/router.py)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.orchestrator.models import ClassificationResult, Intent, Tier
from src.orchestrator.router import IntentClassifier


def _make_classification_response(
    intent: str,
    confidence: float,
    tier: int,
    entities: list[str] | None = None,
) -> MagicMock:
    """Build a mock Claude response carrying structured output."""
    parsed = MagicMock()
    parsed.intent = intent
    parsed.confidence = confidence
    parsed.tier = tier
    parsed.entities = entities or []

    response = MagicMock()
    response.parsed = parsed
    response.usage = MagicMock(input_tokens=120, output_tokens=30)
    return response


@pytest.fixture
def classifier(mock_anthropic_client: MagicMock) -> IntentClassifier:
    return IntentClassifier(client=mock_anthropic_client)


# ------------------------------------------------------------------
# Routing accuracy tests
# ------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
async def test_simple_faq_routes_to_tier1(
    classifier: IntentClassifier,
    mock_anthropic_client: MagicMock,
) -> None:
    """A straightforward product question should route to Tier 1."""
    mock_anthropic_client.messages.parse = AsyncMock(
        return_value=_make_classification_response(
            intent="product_info",
            confidence=0.95,
            tier=1,
            entities=["widget", "dimensions"],
        )
    )

    result = await classifier.classify("What are the dimensions of the Premium Widget?")

    assert result.tier == Tier.TIER_1
    assert result.intent == Intent.PRODUCT_INFO
    assert result.confidence >= 0.85


@pytest.mark.unit
@pytest.mark.asyncio
async def test_order_status_routes_to_tier2(
    classifier: IntentClassifier,
    mock_anthropic_client: MagicMock,
) -> None:
    """Order status query requires tool use — should route to Tier 2."""
    mock_anthropic_client.messages.parse = AsyncMock(
        return_value=_make_classification_response(
            intent="order_status",
            confidence=0.92,
            tier=2,
            entities=["ORD-98765"],
        )
    )

    result = await classifier.classify("Where is my order ORD-98765?")

    assert result.tier == Tier.TIER_2
    assert result.intent == Intent.ORDER_STATUS


@pytest.mark.unit
@pytest.mark.asyncio
async def test_complex_multi_issue_routes_to_tier3(
    classifier: IntentClassifier,
    mock_anthropic_client: MagicMock,
) -> None:
    """A multi-part issue needing investigation should route to Tier 3."""
    mock_anthropic_client.messages.parse = AsyncMock(
        return_value=_make_classification_response(
            intent="complex_investigation",
            confidence=0.88,
            tier=3,
            entities=["billing", "promo", "multiple_orders"],
        )
    )

    result = await classifier.classify(
        "I have three orders from last month and none of them got the "
        "promotional discount I was promised. I also think I was double-charged "
        "on one of them. Can you investigate all three?"
    )

    assert result.tier == Tier.TIER_3
    assert result.intent == Intent.COMPLEX_INVESTIGATION


@pytest.mark.unit
@pytest.mark.asyncio
async def test_low_confidence_triggers_escalation(
    classifier: IntentClassifier,
    mock_anthropic_client: MagicMock,
) -> None:
    """Confidence below 0.6 should trigger immediate escalation."""
    mock_anthropic_client.messages.parse = AsyncMock(
        return_value=_make_classification_response(
            intent="unknown",
            confidence=0.45,
            tier=1,
            entities=[],
        )
    )

    result = await classifier.classify("asdf qwerty gibberish")

    assert result.should_escalate is True
    assert result.confidence < 0.6


@pytest.mark.unit
@pytest.mark.asyncio
async def test_policy_gated_intent_always_escalates(
    classifier: IntentClassifier,
    mock_anthropic_client: MagicMock,
) -> None:
    """Account deletion is policy-gated — always escalate regardless of confidence."""
    mock_anthropic_client.messages.parse = AsyncMock(
        return_value=_make_classification_response(
            intent="account_deletion",
            confidence=0.99,
            tier=2,
            entities=["account", "delete"],
        )
    )

    result = await classifier.classify("I want to delete my account permanently.")

    assert result.should_escalate is True
    assert result.intent == Intent.ACCOUNT_DELETION


@pytest.mark.unit
@pytest.mark.asyncio
async def test_return_request_routes_to_tier2(
    classifier: IntentClassifier,
    mock_anthropic_client: MagicMock,
) -> None:
    """A return request uses initiate_return tool — Tier 2."""
    mock_anthropic_client.messages.parse = AsyncMock(
        return_value=_make_classification_response(
            intent="return_request",
            confidence=0.91,
            tier=2,
            entities=["ORD-11111", "defective"],
        )
    )

    result = await classifier.classify(
        "I received a defective item in order ORD-11111 and I'd like to return it."
    )

    assert result.tier == Tier.TIER_2
    assert result.intent == Intent.RETURN_REQUEST


@pytest.mark.unit
@pytest.mark.asyncio
async def test_classifier_uses_haiku_model(
    classifier: IntentClassifier,
    mock_anthropic_client: MagicMock,
) -> None:
    """The classifier must use Haiku 5.5 with low effort."""
    mock_anthropic_client.messages.parse = AsyncMock(
        return_value=_make_classification_response(
            intent="product_info", confidence=0.9, tier=1
        )
    )

    await classifier.classify("What's your return policy?")

    call_kwargs = mock_anthropic_client.messages.parse.call_args
    assert call_kwargs.kwargs["model"] == "claude-haiku-5-5"
    assert call_kwargs.kwargs.get("effort") == "low"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_classifier_uses_structured_output(
    classifier: IntentClassifier,
    mock_anthropic_client: MagicMock,
) -> None:
    """The classifier must use output_config for structured output."""
    mock_anthropic_client.messages.parse = AsyncMock(
        return_value=_make_classification_response(
            intent="product_info", confidence=0.9, tier=1
        )
    )

    await classifier.classify("Tell me about your products.")

    call_kwargs = mock_anthropic_client.messages.parse.call_args
    assert "output_config" in call_kwargs.kwargs or "response_format" in call_kwargs.kwargs
