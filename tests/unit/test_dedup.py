"""Tests for duplicate ticket detection (src/tools/dedup.py)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.tools.dedup import DedupChecker, DedupResult


@pytest.fixture
def mock_search_tickets() -> AsyncMock:
    """Mock for the search_tickets tool function."""
    return AsyncMock()


@pytest.fixture
def mock_similarity_scorer() -> AsyncMock:
    """Mock for the Haiku 5.5 semantic similarity scorer."""
    return AsyncMock()


@pytest.fixture
def dedup_checker(
    mock_search_tickets: AsyncMock,
    mock_similarity_scorer: AsyncMock,
) -> DedupChecker:
    return DedupChecker(
        search_tickets_fn=mock_search_tickets,
        similarity_scorer_fn=mock_similarity_scorer,
        similarity_threshold=0.85,
    )


# ------------------------------------------------------------------
# Pass 1: Exact match (customer_id + category)
# ------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
async def test_exact_match(
    dedup_checker: DedupChecker,
    mock_search_tickets: AsyncMock,
    sample_ticket: dict[str, Any],
) -> None:
    """Same customer_id + same category + open ticket -> duplicate detected."""
    mock_search_tickets.return_value = [sample_ticket]

    result = await dedup_checker.check(
        customer_id="cust_12345",
        category="shipping",
        subject="My order hasn't arrived",
        description="Order ORD-98765 still not delivered.",
    )

    assert result.is_duplicate is True
    assert result.match_type == "exact"
    assert result.existing_ticket_id == "TKT-54321"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_different_category_no_match(
    dedup_checker: DedupChecker,
    mock_search_tickets: AsyncMock,
    sample_ticket: dict[str, Any],
) -> None:
    """Same customer_id + different category -> no duplicate."""
    mock_search_tickets.return_value = [sample_ticket]  # category="shipping"

    result = await dedup_checker.check(
        customer_id="cust_12345",
        category="billing",
        subject="Wrong charge on my card",
        description="I was charged twice.",
    )

    assert result.is_duplicate is False


# ------------------------------------------------------------------
# Pass 2: Semantic similarity
# ------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
async def test_semantic_match_above_threshold(
    dedup_checker: DedupChecker,
    mock_search_tickets: AsyncMock,
    mock_similarity_scorer: AsyncMock,
) -> None:
    """Same customer + similar description (score > 0.85) -> duplicate."""
    open_ticket = {
        "ticket_id": "TKT-99999",
        "customer_id": "cust_12345",
        "category": "product_quality",
        "subject": "Widget is broken",
        "status": "open",
        "description": "The premium widget I received is cracked and doesn't work.",
    }
    mock_search_tickets.return_value = [open_ticket]
    mock_similarity_scorer.return_value = 0.92

    result = await dedup_checker.check(
        customer_id="cust_12345",
        category="returns",
        subject="Broken widget needs replacement",
        description="My premium widget arrived damaged and is non-functional.",
    )

    assert result.is_duplicate is True
    assert result.match_type == "semantic"
    assert result.similarity_score == 0.92
    assert result.existing_ticket_id == "TKT-99999"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_below_similarity_threshold(
    dedup_checker: DedupChecker,
    mock_search_tickets: AsyncMock,
    mock_similarity_scorer: AsyncMock,
) -> None:
    """Same customer + somewhat similar (score < 0.85) -> no duplicate."""
    open_ticket = {
        "ticket_id": "TKT-77777",
        "customer_id": "cust_12345",
        "category": "shipping",
        "subject": "Late delivery last month",
        "status": "open",
        "description": "My October order was delivered a week late.",
    }
    mock_search_tickets.return_value = [open_ticket]
    mock_similarity_scorer.return_value = 0.62

    result = await dedup_checker.check(
        customer_id="cust_12345",
        category="billing",
        subject="Overcharged on shipping",
        description="I was charged express shipping but got standard delivery.",
    )

    assert result.is_duplicate is False
    assert result.similarity_score == 0.62


# ------------------------------------------------------------------
# Customer override
# ------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
async def test_customer_override(
    dedup_checker: DedupChecker,
    mock_search_tickets: AsyncMock,
) -> None:
    """Duplicate found but customer requests new ticket -> creates new, logs override."""
    open_ticket = {
        "ticket_id": "TKT-54321",
        "customer_id": "cust_12345",
        "category": "shipping",
        "subject": "Order stuck in transit",
        "status": "open",
        "description": "Order hasn't moved in days.",
    }
    mock_search_tickets.return_value = [open_ticket]

    # First check finds duplicate
    result = await dedup_checker.check(
        customer_id="cust_12345",
        category="shipping",
        subject="Still waiting for order",
        description="Order ORD-98765 still not arrived.",
    )
    assert result.is_duplicate is True

    # Customer overrides
    override_result = dedup_checker.apply_override(
        dedup_result=result,
        override_reason="This is a different order than the one in the existing ticket.",
    )

    assert override_result.overridden is True
    assert override_result.override_reason is not None
    assert override_result.override_logged is True


# ------------------------------------------------------------------
# Closed ticket exclusion
# ------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
async def test_closed_ticket_excluded(
    dedup_checker: DedupChecker,
    mock_search_tickets: AsyncMock,
    sample_closed_ticket: dict[str, Any],
) -> None:
    """Same customer + same category but ticket is CLOSED -> no duplicate."""
    mock_search_tickets.return_value = [sample_closed_ticket]

    result = await dedup_checker.check(
        customer_id="cust_12345",
        category="shipping",
        subject="Another shipping delay",
        description="New order is also delayed.",
    )

    assert result.is_duplicate is False


# ------------------------------------------------------------------
# Multiple open tickets
# ------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
async def test_multiple_tickets_matches_correct_one(
    dedup_checker: DedupChecker,
    mock_search_tickets: AsyncMock,
) -> None:
    """When multiple open tickets exist, match the one with the right category."""
    tickets = [
        {
            "ticket_id": "TKT-AAA",
            "customer_id": "cust_12345",
            "category": "billing",
            "subject": "Billing question",
            "status": "open",
            "description": "About my invoice.",
        },
        {
            "ticket_id": "TKT-BBB",
            "customer_id": "cust_12345",
            "category": "shipping",
            "subject": "Order delayed",
            "status": "open",
            "description": "Order hasn't arrived.",
        },
    ]
    mock_search_tickets.return_value = tickets

    result = await dedup_checker.check(
        customer_id="cust_12345",
        category="shipping",
        subject="Where is my package?",
        description="Still waiting for delivery.",
    )

    assert result.is_duplicate is True
    assert result.existing_ticket_id == "TKT-BBB"


# ------------------------------------------------------------------
# No open tickets
# ------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
async def test_no_open_tickets(
    dedup_checker: DedupChecker,
    mock_search_tickets: AsyncMock,
) -> None:
    """No open tickets at all -> no duplicate."""
    mock_search_tickets.return_value = []

    result = await dedup_checker.check(
        customer_id="cust_12345",
        category="shipping",
        subject="Order not delivered",
        description="Need help with my order.",
    )

    assert result.is_duplicate is False
    assert result.existing_ticket_id is None
