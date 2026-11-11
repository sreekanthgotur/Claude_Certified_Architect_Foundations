"""Order management tools — lookup and returns."""

from __future__ import annotations

import logging

from anthropic import beta_tool

logger = logging.getLogger(__name__)


@beta_tool(
    strict=True,
    eager_input_streaming=True,
)
def lookup_order(order_id: str) -> str:
    """Look up order status, tracking information, and line items.

    Args:
        order_id: The unique order identifier (e.g., ORD-12345).
    """
    logger.info("tool=lookup_order order_id=%s", order_id)
    # Delegate to the orders MCP server in production.
    # Stub returns a placeholder for local development.
    return (
        f'{{"order_id": "{order_id}", '
        f'"status": "shipped", '
        f'"tracking_number": "1Z999AA10123456784", '
        f'"items": [{{"sku": "WIDGET-001", "qty": 2, "name": "Widget Pro"}}], '
        f'"total": 49.98}}'
    )


@beta_tool(
    strict=True,
    eager_input_streaming=True,
)
def initiate_return(
    order_id: str,
    reason: str,
    item_skus: list[str],
) -> str:
    """Start a return or refund process for one or more items in an order.

    This is a HIGH-RISK write operation. It requires human approval when
    the refund amount exceeds the configured threshold (default $100).

    Args:
        order_id: The order to return items from.
        reason: Customer-provided reason for the return.
        item_skus: List of SKU strings identifying the items to return.
    """
    logger.info(
        "tool=initiate_return order_id=%s reason=%s skus=%s",
        order_id,
        reason,
        item_skus,
    )
    return (
        f'{{"return_id": "RET-{order_id}", '
        f'"status": "pending_approval", '
        f'"items_accepted": {len(item_skus)}, '
        f'"estimated_refund": 49.98}}'
    )
