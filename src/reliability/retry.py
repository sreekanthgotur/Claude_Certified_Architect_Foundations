"""Retry logic wrapping the Anthropic SDK's built-in retry behaviour.

Configures per-tier max_retries and handles the SDK exception chain:
NotFoundError → RateLimitError → APIStatusError → APIConnectionError.
"""

from __future__ import annotations

import logging
from enum import IntEnum
from typing import Any

import anthropic

logger = logging.getLogger(__name__)


class Tier(IntEnum):
    CLASSIFIER = 0
    TIER1 = 1
    TIER2 = 2
    TIER3 = 3


DEFAULT_MAX_RETRIES: dict[Tier, int] = {
    Tier.CLASSIFIER: 2,
    Tier.TIER1: 2,
    Tier.TIER2: 3,
    Tier.TIER3: 5,
}


class RetryHandler:
    """Configures retry behaviour per tier and normalises SDK errors.

    The Anthropic SDK auto-retries on 429/5xx with exponential backoff.
    This handler sets ``max_retries`` per tier so latency-sensitive
    tiers fail fast while complex agentic loops get more attempts.
    """

    def __init__(
        self,
        overrides: dict[Tier, int] | None = None,
    ) -> None:
        self._max_retries = {**DEFAULT_MAX_RETRIES}
        if overrides:
            self._max_retries.update(overrides)

    def get_max_retries(self, tier: Tier) -> int:
        return self._max_retries.get(tier, 2)

    def create_client(self, tier: Tier, **kwargs: Any) -> anthropic.Anthropic:
        """Create an Anthropic client with tier-appropriate retries."""
        return anthropic.Anthropic(
            max_retries=self.get_max_retries(tier),
            **kwargs,
        )

    def create_async_client(
        self,
        tier: Tier,
        **kwargs: Any,
    ) -> anthropic.AsyncAnthropic:
        return anthropic.AsyncAnthropic(
            max_retries=self.get_max_retries(tier),
            **kwargs,
        )

    @staticmethod
    def classify_error(exc: Exception) -> dict[str, Any]:
        """Classify an SDK exception into a structured error record.

        Returns a dict with ``error_type``, ``retryable``, ``status``,
        and ``message`` for structured logging.
        """
        if isinstance(exc, anthropic.NotFoundError):
            return {
                "error_type": "not_found",
                "retryable": False,
                "status": 404,
                "message": str(exc),
            }
        if isinstance(exc, anthropic.RateLimitError):
            return {
                "error_type": "rate_limit",
                "retryable": True,
                "status": 429,
                "message": str(exc),
            }
        if isinstance(exc, anthropic.APIStatusError):
            status = getattr(exc, "status_code", 500)
            return {
                "error_type": "api_status",
                "retryable": status >= 500,
                "status": status,
                "message": str(exc),
            }
        if isinstance(exc, anthropic.APIConnectionError):
            return {
                "error_type": "connection",
                "retryable": True,
                "status": 0,
                "message": str(exc),
            }
        return {
            "error_type": "unknown",
            "retryable": False,
            "status": 0,
            "message": str(exc),
        }

    def handle_error(self, exc: Exception, tier: Tier) -> dict[str, Any]:
        """Log and classify an error from a Claude API call."""
        info = self.classify_error(exc)
        info["tier"] = tier.name
        logger.error("api_error", extra=info)
        return info
