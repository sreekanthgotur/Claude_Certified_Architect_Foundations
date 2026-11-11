"""Model fallback chain and refusal fallbacks.

Opus → Sonnet → Haiku → queue for human.  Server-side refusal
fallbacks via ``fallbacks="default"`` (beta server-side-fallback-2026-07-01).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

REFUSAL_FALLBACK_BETA = "server-side-fallback-2026-07-01"

MODEL_CHAIN: list[str] = [
    "claude-opus-5-5",
    "claude-sonnet-5-5",
    "claude-haiku-5-5",
]


@dataclass
class FallbackEvent:
    original_model: str
    fallback_model: str | None
    reason: str
    queued_for_human: bool = False


@dataclass
class FallbackStats:
    fallbacks_triggered: int = 0
    queued_for_human: int = 0
    events: list[FallbackEvent] = field(default_factory=list)


class FallbackChain:
    """Manages model fallback and server-side refusal fallbacks.

    When the primary model is unavailable or refuses, the chain tries
    progressively cheaper models.  If all fail the request is queued
    for a human agent.
    """

    def __init__(
        self,
        model_chain: list[str] | None = None,
    ) -> None:
        self._chain = model_chain or list(MODEL_CHAIN)
        self._stats = FallbackStats()

    @property
    def stats(self) -> FallbackStats:
        return self._stats

    @property
    def beta_header(self) -> str:
        return REFUSAL_FALLBACK_BETA

    def next_model(self, current_model: str) -> str | None:
        """Return the next model in the fallback chain, or None."""
        try:
            idx = self._chain.index(current_model)
        except ValueError:
            return None
        if idx + 1 < len(self._chain):
            return self._chain[idx + 1]
        return None

    def prepare_refusal_fallback(
        self,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Add server-side refusal fallback to request params.

        With ``fallbacks="default"`` the server automatically retries
        on a different model when the primary model declines due to
        its safety policy.
        """
        betas: list[str] = list(params.get("betas", []))
        if REFUSAL_FALLBACK_BETA not in betas:
            betas.append(REFUSAL_FALLBACK_BETA)
        params = {
            **params,
            "betas": betas,
            "fallbacks": "default",
        }
        return params

    def record_fallback(
        self,
        original_model: str,
        fallback_model: str | None,
        reason: str,
    ) -> FallbackEvent:
        """Record a fallback event for monitoring."""
        queued = fallback_model is None
        event = FallbackEvent(
            original_model=original_model,
            fallback_model=fallback_model,
            reason=reason,
            queued_for_human=queued,
        )
        self._stats.fallbacks_triggered += 1
        if queued:
            self._stats.queued_for_human += 1
        self._stats.events.append(event)

        logger.warning(
            "model_fallback",
            extra={
                "original_model": original_model,
                "fallback_model": fallback_model,
                "reason": reason,
                "queued_for_human": queued,
            },
        )
        return event

    def should_queue_for_human(self, current_model: str) -> bool:
        """True when no further model fallback is available."""
        return self.next_model(current_model) is None

    def build_queue_payload(
        self,
        session_id: str,
        messages: list[dict[str, Any]],
        reason: str,
    ) -> dict[str, Any]:
        """Build a payload for the human-agent queue."""
        logger.warning(
            "queue_for_human",
            extra={"session_id": session_id, "reason": reason},
        )
        return {
            "session_id": session_id,
            "reason": reason,
            "message_count": len(messages),
            "last_user_message": next(
                (
                    m.get("content", "")
                    for m in reversed(messages)
                    if m.get("role") == "user"
                ),
                "",
            ),
        }
