from __future__ import annotations

import logging

from src.orchestrator.models import (
    ConversationState,
    EscalationPayload,
    POLICY_GATED_INTENTS,
)

logger = logging.getLogger(__name__)

LOW_CONFIDENCE_AFTER_TOOLS_THRESHOLD = 2
BUDGET_EXHAUSTION_RATIO = 0.9


class EscalationEngine:
    def should_escalate(
        self,
        state: ConversationState,
        confidence: float | None = None,
        sentiment_negative: bool = False,
        budget_used: int | None = None,
        budget_total: int | None = None,
    ) -> str | None:
        if confidence is not None and len(state.tool_history) >= LOW_CONFIDENCE_AFTER_TOOLS_THRESHOLD:
            if confidence < 0.6:
                return (
                    f"Low confidence ({confidence:.2f}) after "
                    f"{len(state.tool_history)} tool calls"
                )

        if sentiment_negative:
            return "Negative customer sentiment detected"

        if state.tier and any(
            tc.tool_name in ("account_deletion", "legal_request")
            for tc in state.tool_history
        ):
            return "Policy-gated action attempted"

        if (
            budget_used is not None
            and budget_total is not None
            and budget_total > 0
        ):
            ratio = budget_used / budget_total
            if ratio >= BUDGET_EXHAUSTION_RATIO:
                return (
                    f"Task budget near exhaustion "
                    f"({budget_used}/{budget_total} tokens used)"
                )

        return None

    def build_payload(
        self,
        reason: str,
        state: ConversationState,
        assessment: str = "",
    ) -> EscalationPayload:
        logger.info(
            "Building escalation payload: session=%s reason=%s",
            state.session_id,
            reason,
        )

        summary = self._build_summary(state)

        return EscalationPayload(
            reason=reason,
            summary=summary,
            tool_history=list(state.tool_history),
            customer_profile=state.customer_profile,
            assessment=assessment or self._auto_assessment(state, reason),
            conversation_messages=list(state.messages),
        )

    def _build_summary(self, state: ConversationState) -> str:
        user_messages = [
            m["content"]
            for m in state.messages
            if m.get("role") == "user" and isinstance(m.get("content"), str)
        ]

        if not user_messages:
            return "No customer messages recorded."

        first = user_messages[0]
        last = user_messages[-1] if len(user_messages) > 1 else None
        tool_names = [tc.tool_name for tc in state.tool_history]

        parts = [f"Customer initially asked: {first[:200]}"]
        if last:
            parts.append(f"Most recent message: {last[:200]}")
        if tool_names:
            parts.append(f"Tools used: {', '.join(tool_names)}")
        parts.append(f"Turns: {state.turn_count}")

        return " | ".join(parts)

    def _auto_assessment(
        self, state: ConversationState, reason: str
    ) -> str:
        errors = [tc for tc in state.tool_history if tc.is_error]
        if errors:
            return (
                f"Escalation due to: {reason}. "
                f"{len(errors)} tool call(s) failed. "
                "Human review recommended."
            )
        return f"Escalation due to: {reason}. No tool errors encountered."
