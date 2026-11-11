"""Observability: token usage tracking, request-ID logging, metrics.

Emits structured JSON logs with token counts, latency, cost estimates,
and Claude request IDs for debugging with Anthropic support.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

COST_PER_MTOK: dict[str, dict[str, float]] = {
    "claude-haiku-5-5": {"input": 0.10, "output": 0.50},
    "claude-sonnet-5-5": {"input": 0.80, "output": 4.00},
    "claude-opus-5-5": {"input": 4.00, "output": 16.00},
    "claude-opus-5-5-fast": {"input": 8.00, "output": 40.00},
}


@dataclass
class RequestMetrics:
    model: str
    tier: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    latency_ms: float = 0.0
    request_id: str = ""
    estimated_cost_usd: float = 0.0


@dataclass
class AggregateMetrics:
    total_requests: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cost_usd: float = 0.0
    errors: int = 0
    per_tier: dict[str, dict[str, Any]] = field(default_factory=dict)


class ObservabilityManager:
    """Tracks token usage, latency, cost, and request IDs.

    Every API call is logged as a structured JSON record that
    CloudWatch can parse for dashboards and alerting.
    """

    def __init__(self) -> None:
        self._aggregate = AggregateMetrics()

    @property
    def aggregate(self) -> AggregateMetrics:
        return self._aggregate

    def start_timer(self) -> float:
        return time.monotonic()

    def record_response(
        self,
        model: str,
        tier: str,
        usage: dict[str, Any],
        start_time: float,
        response: Any = None,
    ) -> RequestMetrics:
        """Record a completed API response with full metrics."""
        latency_ms = (time.monotonic() - start_time) * 1000

        input_tok = usage.get("input_tokens", 0)
        output_tok = usage.get("output_tokens", 0)
        cache_read = usage.get("cache_read_input_tokens", 0)
        cache_create = usage.get("cache_creation_input_tokens", 0)

        request_id = ""
        if response is not None:
            request_id = getattr(
                getattr(response, "_response", None),
                "headers",
                {},
            ).get("request-id", "")
            if not request_id:
                request_id = getattr(response, "_request_id", "")

        cost = self._estimate_cost(model, input_tok, output_tok, cache_read)

        metrics = RequestMetrics(
            model=model,
            tier=tier,
            input_tokens=input_tok,
            output_tokens=output_tok,
            cache_read_tokens=cache_read,
            cache_creation_tokens=cache_create,
            latency_ms=round(latency_ms, 1),
            request_id=request_id,
            estimated_cost_usd=round(cost, 6),
        )

        self._update_aggregate(metrics)
        self._log_metrics(metrics)
        return metrics

    def record_error(self, tier: str, error_type: str) -> None:
        self._aggregate.errors += 1
        logger.error(
            "api_call_error",
            extra={"tier": tier, "error_type": error_type},
        )

    def get_tier_summary(self, tier: str) -> dict[str, Any]:
        return self._aggregate.per_tier.get(tier, {})

    def get_cost_summary(self) -> dict[str, Any]:
        return {
            "total_cost_usd": round(self._aggregate.total_cost_usd, 4),
            "total_requests": self._aggregate.total_requests,
            "total_input_tokens": self._aggregate.total_input_tokens,
            "total_output_tokens": self._aggregate.total_output_tokens,
            "total_cache_read_tokens": self._aggregate.total_cache_read_tokens,
            "per_tier": {
                k: {
                    "cost_usd": round(v.get("cost_usd", 0), 4),
                    "requests": v.get("requests", 0),
                }
                for k, v in self._aggregate.per_tier.items()
            },
        }

    def _estimate_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int,
    ) -> float:
        rates = COST_PER_MTOK.get(model)
        if rates is None:
            return 0.0
        billable_input = input_tokens - cache_read_tokens
        cache_cost = cache_read_tokens * rates["input"] * 0.1 / 1_000_000
        input_cost = max(0, billable_input) * rates["input"] / 1_000_000
        output_cost = output_tokens * rates["output"] / 1_000_000
        return input_cost + output_cost + cache_cost

    def _update_aggregate(self, m: RequestMetrics) -> None:
        agg = self._aggregate
        agg.total_requests += 1
        agg.total_input_tokens += m.input_tokens
        agg.total_output_tokens += m.output_tokens
        agg.total_cache_read_tokens += m.cache_read_tokens
        agg.total_cost_usd += m.estimated_cost_usd

        tier_data = agg.per_tier.setdefault(m.tier, {
            "requests": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
            "total_latency_ms": 0.0,
        })
        tier_data["requests"] += 1
        tier_data["input_tokens"] += m.input_tokens
        tier_data["output_tokens"] += m.output_tokens
        tier_data["cost_usd"] += m.estimated_cost_usd
        tier_data["total_latency_ms"] += m.latency_ms

    def _log_metrics(self, m: RequestMetrics) -> None:
        logger.info(
            "api_call",
            extra={
                "model": m.model,
                "tier": m.tier,
                "input_tokens": m.input_tokens,
                "output_tokens": m.output_tokens,
                "cache_read_tokens": m.cache_read_tokens,
                "cache_creation_tokens": m.cache_creation_tokens,
                "latency_ms": m.latency_ms,
                "request_id": m.request_id,
                "estimated_cost_usd": m.estimated_cost_usd,
            },
        )
