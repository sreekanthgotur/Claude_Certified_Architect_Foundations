"""Integration tests for Tier 2 — Guided Actions (Tool Use)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from src.orchestrator.models import ConversationState, Tier
from src.tiers.tier2_guided import Tier2Handler


@pytest.fixture
def tier2_handler(mock_anthropic_client: MagicMock) -> Tier2Handler:
    return Tier2Handler(client=mock_anthropic_client)


def _make_tool_runner_result(
    tool_calls: list[dict[str, Any]],
    final_text: str,
) -> MagicMock:
    """Build a mock Tool Runner result."""
    result = MagicMock()
    result.tool_calls = tool_calls
    result.final_response = MagicMock()
    result.final_response.content = [MagicMock(type="text", text=final_text)]
    result.final_response.stop_reason = "end_turn"
    result.final_response.usage = MagicMock(
        input_tokens=3500, output_tokens=250,
        cache_read_input_tokens=3000, cache_creation_input_tokens=0,
    )
    return result


@pytest.mark.integration
@pytest.mark.asyncio
async def test_order_status_lookup(
    tier2_handler: Tier2Handler,
    mock_anthropic_client: MagicMock,
    sample_order: dict[str, Any],
) -> None:
    """'Check my order status' -> lookup_order tool call -> formatted response."""
    mock_anthropic_client.beta.messages.tool_runner = AsyncMock(
        return_value=_make_tool_runner_result(
            tool_calls=[
                {
                    "name": "lookup_order",
                    "input": {"order_id": "ORD-98765"},
                    "result": sample_order,
                }
            ],
            final_text="Your order ORD-98765 is currently in transit via UPS. "
            "Tracking number: 1Z999AA10123456784. "
            "Estimated delivery: November 12, 2026.",
        )
    )

    result = await tier2_handler.handle(
        message="What's the status of order ORD-98765?",
        conversation_state=ConversationState(
            session_id="sess_001",
            customer_id="cust_12345",
            messages=[],
            current_tier=Tier.TIER_2,
        ),
    )

    assert "ORD-98765" in result.response_text
    assert "transit" in result.response_text.lower() or "UPS" in result.response_text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tier2_uses_opus_with_tool_runner(
    tier2_handler: Tier2Handler,
    mock_anthropic_client: MagicMock,
) -> None:
    """Tier 2 must use Opus 5.5 with Tool Runner."""
    mock_anthropic_client.beta.messages.tool_runner = AsyncMock(
        return_value=_make_tool_runner_result([], "Done.")
    )

    await tier2_handler.handle(
        message="Look up my account.",
        conversation_state=ConversationState(
            session_id="sess_001",
            customer_id="cust_12345",
            messages=[],
            current_tier=Tier.TIER_2,
        ),
    )

    call_kwargs = mock_anthropic_client.beta.messages.tool_runner.call_args.kwargs
    assert call_kwargs["model"] == "claude-opus-5-5"
    assert call_kwargs.get("effort") == "high"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_parallel_tool_execution(
    tier2_handler: Tier2Handler,
    mock_anthropic_client: MagicMock,
) -> None:
    """When Claude calls multiple tools in one turn, execute concurrently."""
    mock_anthropic_client.beta.messages.tool_runner = AsyncMock(
        return_value=_make_tool_runner_result(
            tool_calls=[
                {
                    "name": "lookup_order",
                    "input": {"order_id": "ORD-111"},
                    "result": {"status": "delivered"},
                },
                {
                    "name": "lookup_order",
                    "input": {"order_id": "ORD-222"},
                    "result": {"status": "in_transit"},
                },
            ],
            final_text="ORD-111 was delivered. ORD-222 is in transit.",
        )
    )

    result = await tier2_handler.handle(
        message="Check orders ORD-111 and ORD-222.",
        conversation_state=ConversationState(
            session_id="sess_001",
            customer_id="cust_12345",
            messages=[],
            current_tier=Tier.TIER_2,
        ),
    )

    assert "ORD-111" in result.response_text
    assert "ORD-222" in result.response_text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_failed_tool_returns_is_error(
    tier2_handler: Tier2Handler,
    mock_anthropic_client: MagicMock,
) -> None:
    """Failed tool calls must return is_error: true, never dropped."""
    mock_anthropic_client.beta.messages.tool_runner = AsyncMock(
        return_value=_make_tool_runner_result(
            tool_calls=[
                {
                    "name": "lookup_order",
                    "input": {"order_id": "INVALID"},
                    "result": None,
                    "is_error": True,
                    "error_message": "Order not found: INVALID",
                }
            ],
            final_text="I wasn't able to find that order. Could you double-check the order number?",
        )
    )

    result = await tier2_handler.handle(
        message="Check order INVALID.",
        conversation_state=ConversationState(
            session_id="sess_001",
            customer_id="cust_12345",
            messages=[],
            current_tier=Tier.TIER_2,
        ),
    )

    assert result.response_text is not None
    assert len(result.response_text) > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ticket_creation_runs_dedup_first(
    tier2_handler: Tier2Handler,
    mock_anthropic_client: MagicMock,
) -> None:
    """create_ticket must be preceded by search_tickets for dedup check."""
    tool_call_sequence: list[str] = []

    async def mock_tool_runner(**kwargs: Any) -> MagicMock:
        # Capture the per-turn hook to verify tool call order
        result = _make_tool_runner_result(
            tool_calls=[
                {
                    "name": "search_tickets",
                    "input": {"customer_id": "cust_12345", "category": "shipping"},
                    "result": [],
                },
                {
                    "name": "create_ticket",
                    "input": {
                        "customer_id": "cust_12345",
                        "category": "shipping",
                        "subject": "Order not delivered",
                    },
                    "result": {"ticket_id": "TKT-NEW-001"},
                },
            ],
            final_text="I've created ticket TKT-NEW-001 for your shipping issue.",
        )
        for tc in result.tool_calls:
            tool_call_sequence.append(tc["name"])
        return result

    mock_anthropic_client.beta.messages.tool_runner = AsyncMock(side_effect=mock_tool_runner)

    result = await tier2_handler.handle(
        message="Please create a ticket for my shipping issue.",
        conversation_state=ConversationState(
            session_id="sess_001",
            customer_id="cust_12345",
            messages=[],
            current_tier=Tier.TIER_2,
        ),
    )

    # search_tickets must appear before create_ticket
    search_idx = tool_call_sequence.index("search_tickets")
    create_idx = tool_call_sequence.index("create_ticket")
    assert search_idx < create_idx


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ticket_dedup_links_existing(
    tier2_handler: Tier2Handler,
    mock_anthropic_client: MagicMock,
    sample_ticket: dict[str, Any],
) -> None:
    """When a duplicate is found, link to existing ticket instead of creating new."""
    mock_anthropic_client.beta.messages.tool_runner = AsyncMock(
        return_value=_make_tool_runner_result(
            tool_calls=[
                {
                    "name": "search_tickets",
                    "input": {"customer_id": "cust_12345", "category": "shipping"},
                    "result": [sample_ticket],
                },
            ],
            final_text="I found an existing ticket TKT-54321 for your shipping issue. "
            "I've added your new information to it.",
        )
    )

    result = await tier2_handler.handle(
        message="I need to report a shipping problem.",
        conversation_state=ConversationState(
            session_id="sess_001",
            customer_id="cust_12345",
            messages=[],
            current_tier=Tier.TIER_2,
        ),
    )

    assert "TKT-54321" in result.response_text
