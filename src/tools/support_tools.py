"""Support ticket tools — create, search, and escalate."""

from __future__ import annotations

import logging
import uuid

from anthropic import beta_tool

logger = logging.getLogger(__name__)


@beta_tool(
    strict=True,
    eager_input_streaming=True,
)
def create_ticket(
    customer_id: str,
    category: str,
    subject: str,
    description: str,
    priority: str = "medium",
) -> str:
    """Create a new support ticket for a customer issue.

    Duplicate detection runs automatically before creation. If a potential
    duplicate is found (exact match on customer_id+category, or semantic
    similarity >= 0.85), the ticket is created with a duplicate_of reference
    and a flag for human review.

    Args:
        customer_id: The customer filing the ticket.
        category: Issue category (e.g., "billing", "shipping", "technical",
            "returns", "account").
        subject: Short summary of the issue.
        description: Full description from the customer.
        priority: Ticket priority — "low", "medium", "high", or "urgent".
    """
    ticket_id = f"TKT-{uuid.uuid4().hex[:8].upper()}"
    logger.info(
        "tool=create_ticket customer_id=%s category=%s priority=%s ticket_id=%s",
        customer_id,
        category,
        priority,
        ticket_id,
    )
    return (
        f'{{"ticket_id": "{ticket_id}", '
        f'"customer_id": "{customer_id}", '
        f'"category": "{category}", '
        f'"subject": "{subject}", '
        f'"priority": "{priority}", '
        f'"status": "open", '
        f'"duplicate_of": null}}'
    )


@beta_tool(
    strict=True,
    eager_input_streaming=True,
)
def search_tickets(
    customer_id: str = "",
    category: str = "",
    status: str = "",
    query: str = "",
) -> str:
    """Search existing support tickets with filters.

    Used by the duplicate detection pipeline to find potential matches
    before creating a new ticket.

    Args:
        customer_id: Filter by customer. Empty string means all customers.
        category: Filter by category. Empty string means all categories.
        status: Filter by status ("open", "in_progress", "resolved",
            "closed"). Empty string means all statuses.
        query: Free-text search across subject and description.
    """
    logger.info(
        "tool=search_tickets customer_id=%s category=%s status=%s query=%s",
        customer_id,
        category,
        status,
        query,
    )
    return "[]"


@beta_tool(
    strict=True,
    eager_input_streaming=True,
)
def escalate_to_human(
    ticket_id: str,
    reason: str,
    context_summary: str,
) -> str:
    """Escalate a conversation or ticket to a human support agent.

    This should be used when: the issue is too complex for automated
    resolution, the customer explicitly requests a human, a high-risk
    action needs approval, or the agent has low confidence in its response.

    Args:
        ticket_id: The ticket to escalate (or empty string if no ticket
            exists yet).
        reason: Why the escalation is needed.
        context_summary: Summary of the conversation so far, including
            what was tried and what information was gathered.
    """
    logger.info(
        "tool=escalate_to_human ticket_id=%s reason=%s",
        ticket_id,
        reason,
    )
    return (
        f'{{"escalation_id": "ESC-{uuid.uuid4().hex[:8].upper()}", '
        f'"ticket_id": "{ticket_id}", '
        f'"status": "pending_human", '
        f'"estimated_wait_minutes": 5}}'
    )
