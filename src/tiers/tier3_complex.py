from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import anthropic

from src.orchestrator.escalation import EscalationEngine
from src.orchestrator.models import (
    AgentResponse,
    ConversationState,
    TierEnum,
    ToolCallRecord,
)

logger = logging.getLogger(__name__)

MODEL = "claude-opus-5-5"
MAX_TOKENS = 16384
MIN_TASK_BUDGET = 20_000
DEFAULT_TASK_BUDGET = 50_000
BUDGET_EXHAUSTION_RATIO = 0.9


class Tier3Handler:
    def __init__(
        self,
        client: anthropic.AsyncAnthropic | None = None,
        tools: list[Any] | None = None,
        system_prompt_stable: str = "",
        system_prompt_dynamic_builder: Any = None,
        escalation_engine: EscalationEngine | None = None,
        task_budget: int = DEFAULT_TASK_BUDGET,
    ) -> None:
        self._client = client or anthropic.AsyncAnthropic()
        self._tools = tools or []
        self._system_prompt_stable = system_prompt_stable
        self._dynamic_builder = system_prompt_dynamic_builder
        self._escalation = escalation_engine or EscalationEngine()
        self._task_budget = max(task_budget, MIN_TASK_BUDGET)

    async def handle(self, state: ConversationState) -> AgentResponse:
        system_blocks = self._build_system(state)
        messages = [
            {"role": m["role"], "content": m["content"]}
            for m in state.messages
        ]
        tool_calls_log: list[ToolCallRecord] = []
        tokens_used = 0

        async def on_tool_result(
            tool_name: str,
            tool_input: dict[str, Any],
            result: Any,
            is_error: bool,
        ) -> None:
            nonlocal tokens_used
            record = ToolCallRecord(
                tool_name=tool_name,
                tool_input=tool_input,
                tool_result=result if not is_error else str(result),
                is_error=is_error,
                timestamp=datetime.now(timezone.utc),
            )
            tool_calls_log.append(record)
            state.tool_history.append(record)

        response = await self._client.beta.messages.tool_runner(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            effort="xhigh",
            system=system_blocks,
            messages=messages,
            tools=self._tools,
            output_config={
                "task_budget": {"max_tokens": self._task_budget},
            },
            betas=["task-budgets-2026-03-13"],
        )

        state.turn_count += 1
        content = _extract_text(response)
        usage = _extract_usage(response)
        tokens_used = usage.get("input_tokens", 0) + usage.get(
            "output_tokens", 0
        )
        state.token_count += tokens_used

        escalation_reason = self._escalation.should_escalate(
            state,
            budget_used=tokens_used,
            budget_total=self._task_budget,
        )

        escalation_payload = None
        if escalation_reason:
            escalation_payload = self._escalation.build_payload(
                reason=escalation_reason,
                state=state,
                assessment=(
                    f"Tier 3 investigation used {tokens_used} tokens. "
                    f"{escalation_reason}"
                ),
            )
            if not content:
                content = (
                    "I've been investigating your issue but need to "
                    "bring in a specialist to help further. "
                    "I'm transferring you now with all the context "
                    "I've gathered."
                )

        return AgentResponse(
            content=content,
            tool_calls=tool_calls_log,
            escalation=escalation_payload,
            tier_used=TierEnum.TIER_3,
            token_usage=usage,
            model_used=MODEL,
        )

    async def handle_streaming(
        self, state: ConversationState
    ) -> AsyncIterator[str]:
        system_blocks = self._build_system(state)
        messages = [
            {"role": m["role"], "content": m["content"]}
            for m in state.messages
        ]

        async with self._client.messages.stream(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            effort="xhigh",
            system=system_blocks,
            messages=messages,
            tools=self._tools,
            output_config={
                "task_budget": {"max_tokens": self._task_budget},
            },
            betas=["task-budgets-2026-03-13"],
        ) as stream:
            async for text in stream.text_stream:
                yield text

        state.turn_count += 1

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
