"""Duplicate ticket detection — two-pass: exact match then semantic similarity."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import anthropic

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.85


@dataclass
class DedupResult:
    is_duplicate: bool
    duplicate_of: str | None
    similarity_score: float
    match_type: str | None  # "exact" | "semantic" | None
    customer_override: bool


async def check_duplicate(
    customer_id: str,
    category: str,
    description: str,
    existing_tickets: list[dict[str, str]],
    *,
    customer_override: bool = False,
) -> DedupResult:
    """Two-pass duplicate detection.

    Pass 1 — exact match on customer_id + category among open tickets.
    Pass 2 — semantic similarity via Haiku 5.5 embeddings (threshold >= 0.85).

    If customer_override is True, the ticket is created regardless but
    flagged for audit.
    """
    if customer_override:
        logger.info("dedup: customer override — skipping duplicate check")
        return DedupResult(
            is_duplicate=False,
            duplicate_of=None,
            similarity_score=0.0,
            match_type=None,
            customer_override=True,
        )

    # Pass 1: exact match
    for ticket in existing_tickets:
        if (
            ticket.get("customer_id") == customer_id
            and ticket.get("category") == category
            and ticket.get("status") in ("open", "in_progress")
        ):
            logger.info(
                "dedup: exact match found ticket_id=%s",
                ticket.get("ticket_id"),
            )
            return DedupResult(
                is_duplicate=True,
                duplicate_of=ticket.get("ticket_id"),
                similarity_score=1.0,
                match_type="exact",
                customer_override=False,
            )

    # Pass 2: semantic similarity via Haiku 5.5
    if not existing_tickets:
        return DedupResult(
            is_duplicate=False,
            duplicate_of=None,
            similarity_score=0.0,
            match_type=None,
            customer_override=False,
        )

    best_score = 0.0
    best_ticket_id: str | None = None

    client = anthropic.AsyncAnthropic()

    for ticket in existing_tickets:
        existing_desc = ticket.get("description", "")
        if not existing_desc:
            continue

        try:
            response = await client.messages.create(
                model="claude-haiku-5-5",
                max_tokens=50,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "Rate the semantic similarity between these two "
                            "support tickets on a scale of 0.0 to 1.0. "
                            "Reply with ONLY a decimal number.\n\n"
                            f"Ticket A: {description}\n\n"
                            f"Ticket B: {existing_desc}"
                        ),
                    }
                ],
            )
            score_text = response.content[0].text.strip()
            score = float(score_text)
            if score > best_score:
                best_score = score
                best_ticket_id = ticket.get("ticket_id")
        except (ValueError, IndexError, anthropic.APIError) as exc:
            logger.warning("dedup: semantic scoring failed: %s", exc)
            continue

    if best_score >= SIMILARITY_THRESHOLD:
        logger.info(
            "dedup: semantic match found ticket_id=%s score=%.2f",
            best_ticket_id,
            best_score,
        )
        return DedupResult(
            is_duplicate=True,
            duplicate_of=best_ticket_id,
            similarity_score=best_score,
            match_type="semantic",
            customer_override=False,
        )

    return DedupResult(
        is_duplicate=False,
        duplicate_of=None,
        similarity_score=best_score,
        match_type=None,
        customer_override=False,
    )
