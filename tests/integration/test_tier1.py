"""Integration tests for Tier 1 — FAQ / RAG with Citations."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.orchestrator.models import ClassificationResult, Intent, Tier
from src.tiers.tier1_instant import Tier1Handler


@pytest.fixture
def mock_rag_retriever() -> AsyncMock:
    """Mock RAG retrieval pipeline (hybrid vector + BM25)."""
    retriever = AsyncMock()
    retriever.search.return_value = [
        {
            "document_index": 0,
            "title": "Return Policy",
            "content": "Items can be returned within 30 days of purchase. "
            "The item must be in its original packaging. "
            "Refunds are processed within 5-7 business days.",
            "source": "help/returns.html",
            "score": 0.94,
        },
        {
            "document_index": 1,
            "title": "Shipping FAQ",
            "content": "Standard shipping takes 5-7 business days. "
            "Express shipping takes 2-3 business days.",
            "source": "help/shipping.html",
            "score": 0.72,
        },
    ]
    return retriever


@pytest.fixture
def tier1_handler(
    mock_anthropic_client: MagicMock,
    mock_rag_retriever: AsyncMock,
) -> Tier1Handler:
    return Tier1Handler(
        client=mock_anthropic_client,
        retriever=mock_rag_retriever,
    )


def _make_cited_response() -> MagicMock:
    """Build a mock Claude response with citations."""
    citation_block = MagicMock()
    citation_block.type = "cite"
    citation_block.cited_text = "Items can be returned within 30 days of purchase."
    citation_block.document_index = 0
    citation_block.start_char_index = 0
    citation_block.end_char_index = 51

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "You can return items within 30 days of purchase."

    response = MagicMock()
    response.content = [text_block, citation_block]
    response.stop_reason = "end_turn"
    response.usage = MagicMock(
        input_tokens=2500,
        output_tokens=150,
        cache_read_input_tokens=2200,
        cache_creation_input_tokens=0,
    )
    response.model = "claude-sonnet-5-5"
    return response


@pytest.mark.integration
@pytest.mark.asyncio
async def test_faq_query_returns_cited_response(
    tier1_handler: Tier1Handler,
    mock_anthropic_client: MagicMock,
    mock_rag_retriever: AsyncMock,
) -> None:
    """FAQ query -> RAG retrieval -> cited response with valid citations."""
    mock_anthropic_client.messages.create = AsyncMock(
        return_value=_make_cited_response()
    )

    result = await tier1_handler.handle(
        message="What is your return policy?",
        customer_context={"customer_id": "cust_001"},
    )

    assert result.response_text is not None
    assert len(result.citations) > 0

    citation = result.citations[0]
    assert citation.cited_text is not None
    assert citation.document_index == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tier1_uses_sonnet_with_citations(
    tier1_handler: Tier1Handler,
    mock_anthropic_client: MagicMock,
) -> None:
    """Tier 1 must use Sonnet 5.5 with citations enabled."""
    mock_anthropic_client.messages.create = AsyncMock(
        return_value=_make_cited_response()
    )

    await tier1_handler.handle(
        message="How long does shipping take?",
        customer_context={"customer_id": "cust_001"},
    )

    call_kwargs = mock_anthropic_client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-sonnet-5-5"
    assert call_kwargs.get("citations", {}).get("enabled") is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tier1_uses_prompt_caching(
    tier1_handler: Tier1Handler,
    mock_anthropic_client: MagicMock,
) -> None:
    """Documents should be injected with cache_control on the last block."""
    mock_anthropic_client.messages.create = AsyncMock(
        return_value=_make_cited_response()
    )

    await tier1_handler.handle(
        message="What is your return policy?",
        customer_context={"customer_id": "cust_001"},
    )

    call_kwargs = mock_anthropic_client.messages.create.call_args.kwargs
    system_blocks = call_kwargs.get("system", [])
    if system_blocks:
        last_block = system_blocks[-1] if isinstance(system_blocks, list) else system_blocks
        if isinstance(last_block, dict):
            assert last_block.get("cache_control") == {"type": "ephemeral"}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_no_documents_found_offers_escalation(
    tier1_handler: Tier1Handler,
    mock_anthropic_client: MagicMock,
    mock_rag_retriever: AsyncMock,
) -> None:
    """When no relevant documents are found, agent should offer escalation."""
    mock_rag_retriever.search.return_value = []

    no_doc_response = MagicMock()
    no_doc_response.content = [
        MagicMock(
            type="text",
            text="I don't have specific information about that. "
            "Would you like me to connect you with a specialist?",
        )
    ]
    no_doc_response.stop_reason = "end_turn"
    no_doc_response.usage = MagicMock(
        input_tokens=800, output_tokens=40,
        cache_read_input_tokens=0, cache_creation_input_tokens=0,
    )
    mock_anthropic_client.messages.create = AsyncMock(return_value=no_doc_response)

    result = await tier1_handler.handle(
        message="What is the airspeed velocity of an unladen swallow?",
        customer_context={"customer_id": "cust_001"},
    )

    assert result.citations == []
    assert "escalat" in result.response_text.lower() or "specialist" in result.response_text.lower()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tier1_uses_effort_medium(
    tier1_handler: Tier1Handler,
    mock_anthropic_client: MagicMock,
) -> None:
    mock_anthropic_client.messages.create = AsyncMock(
        return_value=_make_cited_response()
    )

    await tier1_handler.handle(
        message="How do I reset my password?",
        customer_context={"customer_id": "cust_001"},
    )

    call_kwargs = mock_anthropic_client.messages.create.call_args.kwargs
    assert call_kwargs.get("effort") == "medium"
