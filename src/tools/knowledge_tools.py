"""Knowledge base search tool with citation support."""

from __future__ import annotations

import logging

from anthropic import beta_tool

logger = logging.getLogger(__name__)


@beta_tool(
    strict=True,
    eager_input_streaming=True,
)
def search_knowledge_base(
    query: str,
    category: str = "",
) -> str:
    """Search product documentation, FAQs, and company policies.

    Returns document content blocks suitable for the Citations API.
    The results are injected as document content blocks so Claude can
    cite them with ``cited_text``, ``document_index``, and source location.

    Args:
        query: The natural-language search query.
        category: Optional category filter (e.g., "shipping",
            "returns", "billing"). Empty string means search all.
    """
    logger.info(
        "tool=search_knowledge_base query=%s category=%s",
        query,
        category,
    )
    return (
        '[{"title": "Returns Policy", '
        '"content": "Items may be returned within 30 days of delivery '
        'for a full refund. Items must be in original packaging.", '
        '"source": "policies/returns.md", '
        '"relevance_score": 0.95}]'
    )
