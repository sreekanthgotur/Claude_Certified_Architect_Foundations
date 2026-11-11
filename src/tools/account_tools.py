"""Account management tools — lookup and subscription changes."""

from __future__ import annotations

import logging

from anthropic import beta_tool

logger = logging.getLogger(__name__)


@beta_tool(
    strict=True,
    eager_input_streaming=True,
)
def lookup_account(customer_id: str) -> str:
    """Retrieve customer profile, subscription status, and account history.

    Args:
        customer_id: The unique customer identifier (e.g., CUST-00001).
    """
    logger.info("tool=lookup_account customer_id=%s", customer_id)
    return (
        f'{{"customer_id": "{customer_id}", '
        f'"name": "Jane Doe", '
        f'"email": "jane@example.com", '
        f'"plan": "pro", '
        f'"account_age_days": 365, '
        f'"status": "active"}}'
    )


@beta_tool(
    strict=True,
    eager_input_streaming=True,
)
def update_subscription(
    customer_id: str,
    new_plan: str,
) -> str:
    """Modify a customer's subscription plan (upgrade, downgrade, or cancel).

    This is a HIGH-RISK write operation and always requires human approval.

    Args:
        customer_id: The customer whose subscription to modify.
        new_plan: The target plan name (e.g., "basic", "pro", "enterprise",
            or "cancel").
    """
    logger.info(
        "tool=update_subscription customer_id=%s new_plan=%s",
        customer_id,
        new_plan,
    )
    return (
        f'{{"customer_id": "{customer_id}", '
        f'"previous_plan": "pro", '
        f'"new_plan": "{new_plan}", '
        f'"status": "pending_approval", '
        f'"effective_date": "2026-12-01"}}'
    )
