"""Integration tests for Tier 3 — Complex Investigation (Agentic)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.orchestrator.models import ConversationState, Tier
from src.tiers.tier3_complex import Tier3Handler


@pytest.fixture
def tier3_handler(mock_anthropic_client: MagicMock) -> Tier3Handler:
    return Tier3Handler(client=mock_anthropic_client)


def _make_streaming_result(
    tool_calls: list[dict[str, Any]],
    final_text: str,
    budget_used: int = 15_000,
) -> MagicMock:
    """Build a mock streaming Tool Runner result for Tier 3."""
    result = MagicMock()
    result.tool_calls = tool_calls
    result.final_response = MagicMock()
    result.final_response.content = [MagicMock(type="text", text=final_text)]
    result.final_response.stop_reason = "end_turn"
    result.final_response.usage = MagicMock(
        input_tokens=8000,
        output_tokens=2000,
        cache_read_input_tokens=7500,
        cache_creation_input_tokens=0,
    )
    result.budget_used = budget_used
    result.budget_total = 20_000
    return result


@pytest.mark.integration
@pytest.mark.asyncio
async def test_complex_multi_step_resolution(
    tier3_handler: Tier3Handler,
    mock_anthropic_client: MagicMock,
) -> None:
    """Complex query -> multiple tool calls across systems -> resolution."""
    mock_anthropic_client.beta.messages.tool_runner = AsyncMock(
        return_value=_make_streaming_result(
            tool_calls=[
                {
                    "name": "lookup_order",
                    "input": {"order_id": "ORD-111"},
                    "result": {"status": "delivered", "total": 150.0},
                },
                {
                    "name": "lookup_order",
                    "input": {"order_id": "ORD-222"},
                    "result": {"status": "delivered", "total": 89.99},
                },
                {
                    "name": "lookup_account",
                    "input": {"customer_id": "cust_12345"},
                    "result": {"tier": "gold", "promo_code": "HOLIDAY20"},
                },
                {
                    "name": "create_ticket",
                    "input": {
                        "customer_id": "cust_12345",
                        "category": "billing",
                        "subject": "Promo not applied to multiple orders",
                    },
                    "result": {"ticket_id": "TKT-COMPLEX-001"},
                },
            ],
            final_text="I've investigated your three orders and found that the "
            "HOLIDAY20 promotion was not applied to ORD-111 ($150.00) and "
            "ORD-222 ($89.99). I've created ticket TKT-COMPLEX-001 for "
            "the billing team to process the credit.",
            budget_used=18_000,
        )
    )

    result = await tier3_handler.handle(
        message="I have three orders from last month and none of them got "
        "the promotional discount I was promised.",
        conversation_state=ConversationState(
            session_id="sess_001",
            customer_id="cust_12345",
            messages=[],
            current_tier=Tier.TIER_3,
        ),
    )

    assert result.response_text is not None
    assert len(result.tool_calls_made) >= 3


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tier3_uses_task_budget(
    tier3_handler: Tier3Handler,
    mock_anthropic_client: MagicMock,
) -> None:
    """Tier 3 must set task_budget in output_config."""
    mock_anthropic_client.beta.messages.tool_runner = AsyncMock(
        return_value=_make_streaming_result([], "Resolved.", budget_used=5000)
    )

    await tier3_handler.handle(
        message="Investigate my billing discrepancy.",
        conversation_state=ConversationState(
            session_id="sess_001",
            customer_id="cust_12345",
            messages=[],
            current_tier=Tier.TIER_3,
        ),
    )

    call_kwargs = mock_anthropic_client.beta.messages.tool_runner.call_args.kwargs
    output_config = call_kwargs.get("output_config", {})
    assert output_config.get("task_budget", 0) >= 20_000


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tier3_uses_streaming(
    tier3_handler: Tier3Handler,
    mock_anthropic_client: MagicMock,
) -> None:
    """Tier 3 must always use streaming to avoid HTTP timeouts."""
    mock_anthropic_client.beta.messages.tool_runner = AsyncMock(
        return_value=_make_streaming_result([], "Done.")
    )

    await tier3_handler.handle(
        message="Complex investigation needed.",
        conversation_state=ConversationState(
            session_id="sess_001",
            customer_id="cust_12345",
            messages=[],
            current_tier=Tier.TIER_3,
        ),
    )

    call_kwargs = mock_anthropic_client.beta.messages.tool_runner.call_args.kwargs
    assert call_kwargs.get("stream") is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tier3_uses_opus_xhigh_effort(
    tier3_handler: Tier3Handler,
    mock_anthropic_client: MagicMock,
) -> None:
    mock_anthropic_client.beta.messages.tool_runner = AsyncMock(
        return_value=_make_streaming_result([], "Done.")
    )

    await tier3_handler.handle(
        message="Deep investigation.",
        conversation_state=ConversationState(
            session_id="sess_001",
            customer_id="cust_12345",
            messages=[],
            current_tier=Tier.TIER_3,
        ),
    )

    call_kwargs = mock_anthropic_client.beta.messages.tool_runner.call_args.kwargs
    assert call_kwargs["model"] == "claude-opus-5-5"
    assert call_kwargs.get("effort") == "xhigh"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_budget_exhaustion_triggers_escalation(
    tier3_handler: Tier3Handler,
    mock_anthropic_client: MagicMock,
) -> None:
    """When task budget nears exhaustion without resolution, escalate."""
    mock_anthropic_client.beta.messages.tool_runner = AsyncMock(
        return_value=_make_streaming_result(
            tool_calls=[
                {"name": "lookup_order", "input": {"order_id": "ORD-1"}, "result": {}},
                {"name": "lookup_account", "input": {"customer_id": "cust_1"}, "result": {}},
                {"name": "search_knowledge_base", "input": {"query": "complex"}, "result": {}},
            ],
            final_text="I've been unable to fully resolve this within the "
            "investigation budget. Here's what I found so far... "
            "I'm escalating to a specialist for further review.",
            budget_used=19_500,
        )
    )

    result = await tier3_handler.handle(
        message="Extremely complex multi-system issue.",
        conversation_state=ConversationState(
            session_id="sess_001",
            customer_id="cust_12345",
            messages=[],
            current_tier=Tier.TIER_3,
        ),
    )

    assert result.escalated is True or "escalat" in result.response_text.lower()
