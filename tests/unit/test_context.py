"""Tests for context management (src/context/)."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.context.cache_manager import CacheManager
from src.context.compaction import CompactionHandler
from src.context.editor import ContextEditor


# ------------------------------------------------------------------
# Cache manager
# ------------------------------------------------------------------

@pytest.fixture
def cache_manager() -> CacheManager:
    return CacheManager()


@pytest.mark.unit
def test_cache_hit_detected(cache_manager: CacheManager) -> None:
    """A response with cache_read_input_tokens > 0 is a cache hit."""
    usage = MagicMock()
    usage.cache_read_input_tokens = 4500
    usage.cache_creation_input_tokens = 0

    assert cache_manager.is_cache_hit(usage) is True


@pytest.mark.unit
def test_cache_miss_detected(cache_manager: CacheManager) -> None:
    """A response with cache_read_input_tokens == 0 is a cache miss."""
    usage = MagicMock()
    usage.cache_read_input_tokens = 0
    usage.cache_creation_input_tokens = 4500

    assert cache_manager.is_cache_hit(usage) is False


@pytest.mark.unit
def test_cache_miss_alert_threshold(cache_manager: CacheManager) -> None:
    """Alert when cache miss rate exceeds 5%."""
    hits = [True] * 94 + [False] * 6
    for hit in hits:
        cache_manager.record(hit)

    assert cache_manager.miss_rate > 0.05
    assert cache_manager.should_alert() is True


@pytest.mark.unit
def test_cache_healthy_no_alert(cache_manager: CacheManager) -> None:
    """No alert when cache is healthy (< 5% miss rate)."""
    hits = [True] * 98 + [False] * 2
    for hit in hits:
        cache_manager.record(hit)

    assert cache_manager.miss_rate <= 0.05
    assert cache_manager.should_alert() is False


@pytest.mark.unit
def test_deterministic_serialization() -> None:
    """Tool definitions must serialize deterministically for stable cache keys."""
    tool_a = {"name": "lookup_order", "description": "Look up order", "z_field": 1, "a_field": 2}
    tool_b = {"a_field": 2, "name": "lookup_order", "z_field": 1, "description": "Look up order"}

    assert (
        json.dumps(tool_a, sort_keys=True)
        == json.dumps(tool_b, sort_keys=True)
    )


# ------------------------------------------------------------------
# Compaction
# ------------------------------------------------------------------

@pytest.fixture
def compaction_handler() -> CompactionHandler:
    return CompactionHandler(token_threshold=150_000)


@pytest.mark.unit
def test_compaction_triggers_at_threshold(compaction_handler: CompactionHandler) -> None:
    """Compaction should trigger when total tokens approach 150K."""
    assert compaction_handler.should_compact(total_input_tokens=155_000) is True


@pytest.mark.unit
def test_compaction_does_not_trigger_below_threshold(
    compaction_handler: CompactionHandler,
) -> None:
    assert compaction_handler.should_compact(total_input_tokens=100_000) is False


@pytest.mark.unit
def test_compaction_preserves_response_content() -> None:
    """Compaction must append response.content, not just response.text."""
    handler = CompactionHandler(token_threshold=150_000)
    response = MagicMock()
    response.content = [
        {"type": "text", "text": "Here is the summary..."},
        {"type": "compaction", "summary": "Prior conversation covered order issues."},
    ]

    messages = handler.build_compacted_messages(
        original_messages=[
            {"role": "user", "content": "msg1"},
            {"role": "assistant", "content": "reply1"},
            {"role": "user", "content": "msg2"},
        ],
        compaction_response=response,
    )

    assistant_msg = next(m for m in messages if m["role"] == "assistant")
    assert isinstance(assistant_msg["content"], list)


# ------------------------------------------------------------------
# Context editor
# ------------------------------------------------------------------

@pytest.fixture
def context_editor() -> ContextEditor:
    return ContextEditor()


@pytest.mark.unit
def test_context_editing_reduces_tokens(context_editor: ContextEditor) -> None:
    """Stripping old tool results should reduce token count by >30%."""
    messages = [
        {"role": "user", "content": "Check my order"},
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "tu_1", "name": "lookup_order", "input": {"order_id": "ORD-1"}},
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "tu_1",
                    "content": "A" * 5000,
                },
            ],
        },
        {"role": "assistant", "content": "Your order is on its way."},
        {"role": "user", "content": "What about my other order?"},
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "tu_2", "name": "lookup_order", "input": {"order_id": "ORD-2"}},
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "tu_2",
                    "content": "B" * 5000,
                },
            ],
        },
        {"role": "assistant", "content": "That order was delivered yesterday."},
    ]

    original_size = sum(len(json.dumps(m)) for m in messages)
    edited = context_editor.clear_old_tool_results(messages, keep_last_n=1)
    edited_size = sum(len(json.dumps(m)) for m in edited)

    reduction = 1 - (edited_size / original_size)
    assert reduction > 0.30, f"Only {reduction:.0%} reduction (need >30%)"


@pytest.mark.unit
def test_context_editing_keeps_latest_tool_result(
    context_editor: ContextEditor,
) -> None:
    """The most recent tool result should be preserved."""
    messages = [
        {"role": "user", "content": "q1"},
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "tu_old", "name": "lookup_order", "input": {}}],
        },
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "tu_old", "content": "old data"}]},
        {"role": "assistant", "content": "noted"},
        {"role": "user", "content": "q2"},
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "tu_new", "name": "lookup_order", "input": {}}],
        },
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "tu_new", "content": "new data"}]},
    ]

    edited = context_editor.clear_old_tool_results(messages, keep_last_n=1)
    all_text = json.dumps(edited)
    assert "new data" in all_text
    assert "old data" not in all_text
