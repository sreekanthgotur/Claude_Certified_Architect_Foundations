"""Conversation compaction handler.

Triggers server-side auto-summarisation at ~150 K tokens using the
compact-2026-01-12 beta.  Preserves response.content (not just text)
so that compaction blocks survive across turns.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

COMPACTION_THRESHOLD_TOKENS = 150_000
COMPACTION_BETA = "compact-2026-01-12"


@dataclass
class CompactionStats:
    compactions_triggered: int = 0
    tokens_before_last: int = 0
    tokens_after_last: int = 0


class CompactionHandler:
    """Manages conversation compaction via the Claude API beta.

    When the running token count crosses ~150 K the handler signals
    that the next request should include the compaction beta header
    so the server auto-summarises earlier context.
    """

    def __init__(
        self,
        threshold: int = COMPACTION_THRESHOLD_TOKENS,
    ) -> None:
        self._threshold = threshold
        self._current_token_count = 0
        self._stats = CompactionStats()

    @property
    def stats(self) -> CompactionStats:
        return self._stats

    @property
    def beta_header(self) -> str:
        return COMPACTION_BETA

    def update_token_count(self, usage: dict[str, Any]) -> None:
        """Update the running input-token estimate from API usage."""
        self._current_token_count = usage.get("input_tokens", 0)

    def needs_compaction(self) -> bool:
        return self._current_token_count >= self._threshold

    def prepare_request_params(
        self,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Inject compaction beta header into request params if needed."""
        if not self.needs_compaction():
            return params

        betas: list[str] = list(params.get("betas", []))
        if COMPACTION_BETA not in betas:
            betas.append(COMPACTION_BETA)
        params = {**params, "betas": betas}

        logger.info(
            "compaction_triggered",
            extra={
                "current_tokens": self._current_token_count,
                "threshold": self._threshold,
            },
        )
        return params

    def process_response(
        self,
        response_content: list[dict[str, Any]],
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Append the full response.content to messages.

        Uses the raw content list (not just extracted text) so that
        compaction summary blocks are preserved for future turns.
        """
        tokens_before = self._current_token_count

        messages.append({"role": "assistant", "content": response_content})

        if self.needs_compaction():
            self._stats.compactions_triggered += 1
            self._stats.tokens_before_last = tokens_before
            logger.info(
                "compaction_applied",
                extra={
                    "tokens_before": tokens_before,
                    "compaction_count": self._stats.compactions_triggered,
                },
            )

        return messages

    def record_post_compaction_usage(self, usage: dict[str, Any]) -> None:
        """Record the token count after compaction for stats."""
        after = usage.get("input_tokens", 0)
        self._stats.tokens_after_last = after
        self._current_token_count = after
        if self._stats.tokens_before_last > 0:
            reduction = 1 - (after / self._stats.tokens_before_last)
            logger.info(
                "compaction_reduction",
                extra={
                    "tokens_before": self._stats.tokens_before_last,
                    "tokens_after": after,
                    "reduction_pct": round(reduction * 100, 1),
                },
            )
