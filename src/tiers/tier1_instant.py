from __future__ import annotations

import logging
from typing import Any, AsyncIterator

import anthropic

from src.orchestrator.models import AgentResponse, ConversationState, TierEnum

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-5-5"
MAX_TOKENS = 4096


class Tier1Handler:
    def __init__(
        self,
        client: anthropic.AsyncAnthropic | None = None,
        system_prompt_stable: str = "",
        system_prompt_dynamic_builder: Any = None,
    ) -> None:
        self._client = client or anthropic.AsyncAnthropic()
        self._system_prompt_stable = system_prompt_stable
        self._dynamic_builder = system_prompt_dynamic_builder

    async def handle(self, state: ConversationState) -> AgentResponse:
        system_blocks = self._build_system(state)
        documents = await self._retrieve_documents(state)
        messages = self._build_messages(state, documents)

        response = await self._client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            effort="medium",
            system=system_blocks,
            messages=messages,
            citations={"enabled": True},
        )

        state.turn_count += 1
        content = _extract_text(response)
        citations = _extract_citations(response)
        usage = _extract_usage(response)

        state.token_count += usage.get("input_tokens", 0)
        state.token_count += usage.get("output_tokens", 0)

        logger.info(
            "Tier 1 response: session=%s tokens=%d citations=%d",
            state.session_id,
            usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            len(citations),
        )

        return AgentResponse(
            content=content,
            citations=citations,
            tier_used=TierEnum.TIER_1,
            token_usage=usage,
            model_used=MODEL,
        )

    async def handle_streaming(
        self, state: ConversationState
    ) -> AsyncIterator[str]:
        system_blocks = self._build_system(state)
        documents = await self._retrieve_documents(state)
        messages = self._build_messages(state, documents)

        async with self._client.messages.stream(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            effort="medium",
            system=system_blocks,
            messages=messages,
            citations={"enabled": True},
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

    async def _retrieve_documents(
        self, state: ConversationState
    ) -> list[dict[str, Any]]:
        # Placeholder: integrate with knowledge_tools / RAG pipeline
        return []

    def _build_messages(
        self,
        state: ConversationState,
        documents: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []

        for msg in state.messages[:-1]:
            messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })

        last_user = state.messages[-1] if state.messages else None
        if last_user and last_user.get("role") == "user":
            content_blocks: list[dict[str, Any]] = []

            for i, doc in enumerate(documents):
                doc_block: dict[str, Any] = {
                    "type": "document",
                    "source": {
                        "type": "text",
                        "media_type": "text/plain",
                        "data": doc.get("content", ""),
                    },
                    "title": doc.get("title", f"Document {i + 1}"),
                }
                if i == len(documents) - 1:
                    doc_block["cache_control"] = {"type": "ephemeral"}
                content_blocks.append(doc_block)

            content_blocks.append({
                "type": "text",
                "text": (
                    last_user["content"]
                    if isinstance(last_user["content"], str)
                    else str(last_user["content"])
                ),
            })
            messages.append({"role": "user", "content": content_blocks})

        return messages


def _extract_text(response: anthropic.types.Message) -> str:
    parts: list[str] = []
    for block in response.content:
        if block.type == "text":
            parts.append(block.text)
    return "".join(parts)


def _extract_citations(response: anthropic.types.Message) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    for block in response.content:
        if block.type == "text" and hasattr(block, "citations") and block.citations:
            for cite in block.citations:
                citations.append({
                    "cited_text": getattr(cite, "cited_text", ""),
                    "document_index": getattr(cite, "document_index", None),
                    "start_char_index": getattr(cite, "start_char_index", None),
                    "end_char_index": getattr(cite, "end_char_index", None),
                })
    return citations


def _extract_usage(response: anthropic.types.Message) -> dict[str, int]:
    usage = response.usage
    return {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_read_input_tokens": getattr(
            usage, "cache_read_input_tokens", 0
        ) or 0,
        "cache_creation_input_tokens": getattr(
            usage, "cache_creation_input_tokens", 0
        ) or 0,
    }
