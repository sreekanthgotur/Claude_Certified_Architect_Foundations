"""Stub duplicate detection — keyword overlap instead of Haiku 5.5 semantic similarity."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.85


@dataclass
class DedupResult:
    is_duplicate: bool
    duplicate_of: str | None
    similarity_score: float
    match_type: str | None  # "exact" | "semantic_stub" | None
    customer_override: bool


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"\w{3,}", text.lower()))


def _keyword_similarity(text_a: str, text_b: str) -> float:
    tokens_a = _tokenize(text_a)
    tokens_b = _tokenize(text_b)
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


async def check_duplicate_stub(
    customer_id: str,
    category: str,
    description: str,
    existing_tickets: list[dict[str, str]],
    *,
    customer_override: bool = False,
) -> DedupResult:
    """Two-pass duplicate detection (stub mode — no API key needed).

    Pass 1 — exact match on customer_id + category among open tickets.
    Pass 2 — keyword overlap similarity (Jaccard) as stand-in for semantic.
    """
    if customer_override:
        logger.info("dedup-stub: customer override — skipping duplicate check")
        return DedupResult(
            is_duplicate=False,
            duplicate_of=None,
            similarity_score=0.0,
            match_type=None,
            customer_override=True,
        )

    # Pass 1: exact match on customer_id + category
    for ticket in existing_tickets:
        if (
            ticket.get("customer_id") == customer_id
            and ticket.get("category") == category
            and ticket.get("status") in ("open", "in_progress")
        ):
            logger.info(
                "dedup-stub: EXACT MATCH found — ticket_id=%s (same customer + category)",
                ticket.get("ticket_id"),
            )
            return DedupResult(
                is_duplicate=True,
                duplicate_of=ticket.get("ticket_id"),
                similarity_score=1.0,
                match_type="exact",
                customer_override=False,
            )

    # Pass 2: keyword similarity (simulates Haiku 5.5 semantic scoring)
    best_score = 0.0
    best_ticket_id: str | None = None

    for ticket in existing_tickets:
        existing_desc = ticket.get("description", "")
        if not existing_desc:
            continue
        if ticket.get("status") not in ("open", "in_progress"):
            continue

        score = _keyword_similarity(description, existing_desc)
        logger.info(
            "dedup-stub: comparing with ticket_id=%s — similarity=%.2f",
            ticket.get("ticket_id"),
            score,
        )
        if score > best_score:
            best_score = score
            best_ticket_id = ticket.get("ticket_id")

    if best_score >= SIMILARITY_THRESHOLD:
        logger.info(
            "dedup-stub: SEMANTIC MATCH found — ticket_id=%s score=%.2f (>= %.2f threshold)",
            best_ticket_id,
            best_score,
            SIMILARITY_THRESHOLD,
        )
        return DedupResult(
            is_duplicate=True,
            duplicate_of=best_ticket_id,
            similarity_score=best_score,
            match_type="semantic_stub",
            customer_override=False,
        )

    logger.info(
        "dedup-stub: no duplicate found — best_score=%.2f (< %.2f threshold)",
        best_score,
        SIMILARITY_THRESHOLD,
    )
    return DedupResult(
        is_duplicate=False,
        duplicate_of=None,
        similarity_score=best_score,
        match_type=None,
        customer_override=False,
    )
