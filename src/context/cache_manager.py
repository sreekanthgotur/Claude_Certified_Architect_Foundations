"""Prompt caching orchestration.

Verifies cache hits via usage.cache_read_input_tokens, enforces
deterministic tool serialization, and monitors cache miss rate.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

CACHE_MISS_ALERT_THRESHOLD = 0.05  # 5 %


@dataclass
class CacheStats:
    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    total_cache_read_tokens: int = 0
    total_cache_creation_tokens: int = 0
    total_input_tokens: int = 0

    @property
    def miss_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.cache_misses / self.total_requests


class CacheManager:
    """Manages prompt caching for the Claude API.

    Ensures deterministic serialization of tools and system prompts so
    the prefix stays stable across requests, maximising cache hits.
    """

    def __init__(self) -> None:
        self._stats = CacheStats()
        self._last_alert_time: float = 0.0

    @property
    def stats(self) -> CacheStats:
        return self._stats

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @staticmethod
    def serialize_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return a deterministic copy of the tool list.

        Every dict is round-tripped through ``json.dumps(sort_keys=True)``
        so key ordering is stable across runs.  This prevents accidental
        cache invalidation caused by non-deterministic dict iteration.
        """
        stabilised: list[dict[str, Any]] = []
        for tool in tools:
            canonical = json.loads(json.dumps(tool, sort_keys=True))
            stabilised.append(canonical)
        return stabilised

    @staticmethod
    def build_cached_system_blocks(
        stable_content: str,
        dynamic_content: str | None = None,
    ) -> list[dict[str, Any]]:
        """Build system content blocks with cache breakpoint.

        The stable layer gets ``cache_control`` so it is cached.  The
        dynamic layer is appended *after* the breakpoint so changes to
        it never invalidate the cached prefix.
        """
        blocks: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": stable_content,
                "cache_control": {"type": "ephemeral"},
            },
        ]
        if dynamic_content:
            blocks.append({"type": "text", "text": dynamic_content})
        return blocks

    # ------------------------------------------------------------------
    # Usage tracking
    # ------------------------------------------------------------------

    def record_usage(self, usage: dict[str, Any]) -> None:
        """Record token usage from an API response and check cache health."""
        cache_read = usage.get("cache_read_input_tokens", 0)
        cache_creation = usage.get("cache_creation_input_tokens", 0)
        input_tokens = usage.get("input_tokens", 0)

        self._stats.total_requests += 1
        self._stats.total_input_tokens += input_tokens
        self._stats.total_cache_read_tokens += cache_read
        self._stats.total_cache_creation_tokens += cache_creation

        if cache_read > 0:
            self._stats.cache_hits += 1
        else:
            self._stats.cache_misses += 1

        self._check_miss_rate()

        logger.info(
            "cache_usage",
            extra={
                "cache_read_tokens": cache_read,
                "cache_creation_tokens": cache_creation,
                "input_tokens": input_tokens,
                "hit": cache_read > 0,
                "miss_rate": round(self._stats.miss_rate, 4),
            },
        )

    def _check_miss_rate(self) -> None:
        if self._stats.total_requests < 20:
            return
        if self._stats.miss_rate <= CACHE_MISS_ALERT_THRESHOLD:
            return
        now = time.monotonic()
        if now - self._last_alert_time < 300:
            return
        self._last_alert_time = now
        logger.warning(
            "cache_miss_rate_high",
            extra={
                "miss_rate": round(self._stats.miss_rate, 4),
                "threshold": CACHE_MISS_ALERT_THRESHOLD,
                "total_requests": self._stats.total_requests,
            },
        )

    def estimated_savings(self) -> dict[str, Any]:
        """Return estimated cost savings from caching."""
        read = self._stats.total_cache_read_tokens
        creation = self._stats.total_cache_creation_tokens
        saved_tokens = max(0, read - creation)
        return {
            "cache_read_tokens": read,
            "cache_creation_tokens": creation,
            "net_saved_tokens": saved_tokens,
            "miss_rate": round(self._stats.miss_rate, 4),
        }
