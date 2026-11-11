"""Dynamic prompt sections — customer-specific context, not cached."""

from __future__ import annotations


def build_dynamic_context(
    customer_info: dict[str, str] | None = None,
    recent_tickets: list[dict[str, str]] | None = None,
    active_orders: list[dict[str, str]] | None = None,
) -> str:
    """Assemble customer-specific context that changes per conversation."""
    sections: list[str] = []

    if customer_info:
        sections.append(
            "## Current customer\n"
            f"- ID: {customer_info.get('customer_id', 'unknown')}\n"
            f"- Name: {customer_info.get('name', 'unknown')}\n"
            f"- Plan: {customer_info.get('plan', 'unknown')}\n"
            f"- Status: {customer_info.get('status', 'unknown')}"
        )

    if recent_tickets:
        lines = ["## Recent tickets"]
        for ticket in recent_tickets[:5]:
            lines.append(
                f"- {ticket.get('ticket_id', '?')}: "
                f"{ticket.get('subject', '?')} "
                f"[{ticket.get('status', '?')}]"
            )
        sections.append("\n".join(lines))

    if active_orders:
        lines = ["## Active orders"]
        for order in active_orders[:5]:
            lines.append(
                f"- {order.get('order_id', '?')}: "
                f"{order.get('status', '?')}"
            )
        sections.append("\n".join(lines))

    return "\n\n".join(sections)
