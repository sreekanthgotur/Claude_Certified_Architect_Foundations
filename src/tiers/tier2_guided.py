from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import anthropic

from src.orchestrator.models import (
    AgentResponse,
    ConversationState,
    TierEnum,
    ToolCallRecord,
)

logger = logging.getLogger(__name__)

MODEL = "claude-opus-5-5"
MAX_TOKENS = 8192
REFUND_THRESHOLD = 100.0
MAX_ACCOUNT_MODIFICATIONS = 3

HIGH_RISK_TOOLS = frozenset({
    "initiate_return",
    "update_subscription",
})

MEDIUM_RISK_TOOLS = frozenset({
    "create_ticket",
    "escalate_to_human",
})

DEDUP_REQUIRED_TOOLS = frozenset({"create_ticket"})


class ApprovalRequired(Exception):
    def __init__(self, tool_name: str, reason: str) -> None:
        self.tool_name = tool_name
        self.reason = reason
        super().__init__(f"Approval required for {tool_name}: {reason}")


class Tier2Handler:
    def __init__(
        self,
        client: anthropic.AsyncAnthropic | None = None,
        tools: list[Any] | None = None,
        system_prompt_stable: str = "",
        system_prompt_dynamic_builder: Any = None,
        refund_threshold: float = REFUND_THRESHOLD,
        max_account_modifications: int = MAX_ACCOUNT_MODIFICATIONS,
    ) -> None:
        self._client = client or anthropic.AsyncAnthropic()
        self._tools = tools or []
        self._system_prompt_stable = system_prompt_stable
        self._dynamic_builder = system_prompt_dynamic_builder
        self._refund_threshold = refund_threshold
        self._max_account_modifications = max_account_modifications
        self._pending_approvals: dict[str, dict[str, Any]] = {}

    async def handle(self, state: ConversationState) -> AgentResponse:
        system_blocks = self._build_system(state)
        messages = [
            {"role": m["role"], "content": m["content"]}
            for m in state.messages
        ]

        tool_calls_log: list[ToolCallRecord] = []

        async def on_tool_call(
            tool_name: str,
            tool_input: dict[str, Any],
        ) -> dict[str, Any] | None:
            self._check_approval_gate(tool_name, tool_input, state)

            if tool_name in DEDUP_REQUIRED_TOOLS:
                dedup_result = await self._run_dedup_check(
                    tool_input, state
                )
                if dedup_result is not None:
                    return dedup_result

            return None

        async def on_tool_result(
            tool_name: str,
            tool_input: dict[str, Any],
            result: Any,
            is_error: bool,
        ) -> None:
            record = ToolCallRecord(
                tool_name=tool_name,
                tool_input=tool_input,
                tool_result=result if not is_error else str(result),
                is_error=is_error,
                timestamp=datetime.now(timezone.utc),
            )
            tool_calls_log.append(record)
            state.tool_history.append(record)

            if tool_name in (
                "update_subscription",
                "initiate_return",
                "account_management",
            ):
                state.account_modifications_count += 1

            logger.info(
                "Tool call: session=%s tool=%s error=%s",
                state.session_id,
                tool_name,
                is_error,
            )

        response = await self._client.beta.messages.tool_runner(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            effort="high",
            system=system_blocks,
            messages=messages,
            tools=self._tools,
        )

        state.turn_count += 1
        content = _extract_text(response)
        usage = _extract_usage(response)

        state.token_count += usage.get("input_tokens", 0)
        state.token_count += usage.get("output_tokens", 0)

        return AgentResponse(
            content=content,
            tool_calls=tool_calls_log,
            tier_used=TierEnum.TIER_2,
            token_usage=usage,
            model_used=MODEL,
        )

    def _build_system(
        self, state: ConversationState
    ) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        if self._system_prompt_stable:
            blocks.append({
                "type": "text",
                "text": self._system_prompt_stable,
                "cache_control": {"type": "ephemeral"},
            })
        dynamic_text = ""
        if self._dynamic_builder:
            dynamic_text = self._dynamic_builder(state)
        if dynamic_text:
            blocks.append({"type": "text", "text": dynamic_text})
        return blocks

    def _check_approval_gate(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        state: ConversationState,
    ) -> None:
        if tool_name in HIGH_RISK_TOOLS:
            if tool_name == "initiate_return":
                amount = tool_input.get("refund_amount", 0)
                if isinstance(amount, (int, float)) and amount > self._refund_threshold:
                    raise ApprovalRequired(
                        tool_name,
                        f"Refund amount ${amount:.2f} exceeds "
                        f"threshold ${self._refund_threshold:.2f}",
                    )

            if tool_name == "update_subscription":
                raise ApprovalRequired(
                    tool_name,
                    "Subscription changes always require approval",
                )

        if (
            state.account_modifications_count
            >= self._max_account_modifications
        ):
            raise ApprovalRequired(
                tool_name,
                f"Account modification limit reached "
                f"({self._max_account_modifications} per session)",
            )

    async def _run_dedup_check(
        self,
        tool_input: dict[str, Any],
        state: ConversationState,
    ) -> dict[str, Any] | None:
        customer_id = tool_input.get(
            "customer_id", state.customer_id
        )
        category = tool_input.get("category", "")

        logger.info(
            "Running dedup check: customer=%s category=%s",
            customer_id,
            category,
        )

        # Dedup logic delegated to src.tools.dedup module
        # Returns None to proceed with ticket creation, or a
        # dict to return as the tool result (existing ticket info)
        return None

    def register_approval(
        self, tool_name: str, approved: bool, session_id: str
    ) -> None:
        key = f"{session_id}:{tool_name}"
        self._pending_approvals[key] = {
            "approved": approved,
            "timestamp": datetime.now(timezone.utc),
        }


def _extract_text(response: Any) -> str:
    parts: list[str] = []
    content = getattr(response, "content", [])
    for block in content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    return "".join(parts)


def _extract_usage(response: Any) -> dict[str, int]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}
    return {
        "input_tokens": getattr(usage, "input_tokens", 0),
        "output_tokens": getattr(usage, "output_tokens", 0),
        "cache_read_input_tokens": getattr(
            usage, "cache_read_input_tokens", 0
        ) or 0,
        "cache_creation_input_tokens": getattr(
            usage, "cache_creation_input_tokens", 0
        ) or 0,
    }
