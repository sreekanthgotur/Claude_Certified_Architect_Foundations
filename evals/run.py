"""Eval runner for the Enterprise AI Customer Support Agent.

Usage:
    python -m evals.run --suite golden       # Full 250+ case golden set
    python -m evals.run --suite smoke        # 11-case smoke subset
    python -m evals.run --suite golden --live # Against live Claude API (needs ANTHROPIC_API_KEY)

Without --live, runs against a deterministic stub model (no API key needed).
Exit code 1 if any dimension drops below its pass threshold.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from evals.score import (
    DIMENSIONS,
    DimensionResult,
    score_case,
    aggregate_results,
    passes_all_thresholds,
)

EVALS_DIR = Path(__file__).parent
GOLDEN_DIR = EVALS_DIR / "golden"
SMOKE_DIR = EVALS_DIR / "smoke"


@dataclass
class EvalCase:
    id: str
    prompt: str
    expected: dict[str, Any]
    category: str = ""
    description: str = ""


@dataclass
class EvalResult:
    case_id: str
    passed: bool
    dimensions: dict[str, DimensionResult] = field(default_factory=dict)
    latency_ms: float = 0.0
    error: str | None = None


def load_suite(suite: str) -> list[EvalCase]:
    """Load test cases for the given suite."""
    cases: list[EvalCase] = []

    if suite == "smoke":
        smoke_file = SMOKE_DIR / "smoke_cases.json"
        if smoke_file.exists():
            data = json.loads(smoke_file.read_text())
            for item in data:
                cases.append(EvalCase(
                    id=item["id"],
                    prompt=item["prompt"],
                    expected=item["expected"],
                    category=item.get("category", ""),
                    description=item.get("description", ""),
                ))
    else:
        for json_file in sorted(GOLDEN_DIR.glob("*.json")):
            data = json.loads(json_file.read_text())
            category = json_file.stem
            for item in data:
                cases.append(EvalCase(
                    id=item["id"],
                    prompt=item["prompt"],
                    expected=item["expected"],
                    category=item.get("category", category),
                    description=item.get("description", ""),
                ))

    return cases


class StubModel:
    """Deterministic stub that returns canned responses based on keywords."""

    def respond(self, prompt: str, expected: dict[str, Any]) -> dict[str, Any]:
        tier = expected.get("tier", 1)
        response: dict[str, Any] = {
            "text": f"[STUB] Response for tier {tier} query.",
            "tier_routed": tier,
            "stop_reason": "end_turn",
            "model": "stub",
            "input_tokens": 500,
            "output_tokens": 100,
            "citations": [],
            "tool_calls": [],
            "escalated": False,
        }

        if expected.get("has_citation"):
            response["citations"] = [
                {
                    "cited_text": "Stub cited passage.",
                    "document_index": 0,
                    "start_char_index": 0,
                    "end_char_index": 20,
                }
            ]

        if expected.get("expected_tools"):
            response["tool_calls"] = [
                {"name": t, "input": {}} for t in expected["expected_tools"]
            ]

        if expected.get("should_escalate"):
            response["escalated"] = True

        if expected.get("dedup_expected"):
            dedup = expected["dedup_expected"]
            response["dedup_result"] = {
                "is_duplicate": dedup.get("is_duplicate", False),
                "match_type": dedup.get("match_type"),
                "existing_ticket_id": dedup.get("existing_ticket_id"),
            }

        return response


class LiveModel:
    """Calls the live Claude API. Requires ANTHROPIC_API_KEY."""

    def __init__(self) -> None:
        import anthropic
        self.client = anthropic.Anthropic()

    def respond(self, prompt: str, expected: dict[str, Any]) -> dict[str, Any]:
        response = self.client.messages.create(
            model="claude-sonnet-5-5",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text += block.text

        return {
            "text": text,
            "tier_routed": expected.get("tier", 1),
            "stop_reason": response.stop_reason,
            "model": response.model,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "citations": [],
            "tool_calls": [],
            "escalated": False,
        }


def run_case(
    case: EvalCase,
    model: StubModel | LiveModel,
) -> EvalResult:
    """Run a single eval case and score it."""
    start = time.monotonic()
    try:
        response = model.respond(case.prompt, case.expected)
        latency_ms = (time.monotonic() - start) * 1000

        dimensions = score_case(
            response=response,
            expected=case.expected,
            latency_ms=latency_ms,
        )

        passed = all(d.passed for d in dimensions.values())

        return EvalResult(
            case_id=case.id,
            passed=passed,
            dimensions=dimensions,
            latency_ms=latency_ms,
        )
    except Exception as exc:
        return EvalResult(
            case_id=case.id,
            passed=False,
            latency_ms=(time.monotonic() - start) * 1000,
            error=str(exc),
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run eval suite")
    parser.add_argument(
        "--suite",
        choices=["golden", "smoke"],
        default="golden",
        help="Which suite to run (default: golden)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run against live Claude API (needs ANTHROPIC_API_KEY)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Path to write JSON results",
    )
    args = parser.parse_args()

    cases = load_suite(args.suite)
    if not cases:
        print(f"No cases found for suite '{args.suite}'")
        sys.exit(1)

    model: StubModel | LiveModel
    if args.live:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("ANTHROPIC_API_KEY not set. Use --live only with a valid key.")
            sys.exit(1)
        model = LiveModel()
    else:
        model = StubModel()

    print(f"Running {len(cases)} cases from '{args.suite}' suite "
          f"({'live' if args.live else 'stub'} model)")
    print("-" * 60)

    results: list[EvalResult] = []
    for case in cases:
        result = run_case(case, model)
        status = "PASS" if result.passed else "FAIL"
        error_suffix = f" ({result.error})" if result.error else ""
        print(f"  [{status}] {case.id}: {result.latency_ms:.0f}ms{error_suffix}")
        results.append(result)

    print("-" * 60)

    # Aggregate
    agg = aggregate_results(results)
    print(f"\nResults: {agg['passed']}/{agg['total']} passed "
          f"({agg['pass_rate']:.1%})")
    print("\nDimension breakdown:")
    for dim_name, dim_agg in agg["dimensions"].items():
        threshold = DIMENSIONS[dim_name]["threshold"]
        status = "OK" if dim_agg["rate"] >= threshold else "BELOW"
        print(f"  {dim_name}: {dim_agg['rate']:.1%} "
              f"(threshold: {threshold:.0%}) [{status}]")

    # Write output
    if args.output:
        output_data = {
            "suite": args.suite,
            "model": "live" if args.live else "stub",
            "total": agg["total"],
            "passed": agg["passed"],
            "pass_rate": agg["pass_rate"],
            "dimensions": agg["dimensions"],
            "cases": [
                {
                    "id": r.case_id,
                    "passed": r.passed,
                    "latency_ms": r.latency_ms,
                    "error": r.error,
                }
                for r in results
            ],
        }
        Path(args.output).write_text(json.dumps(output_data, indent=2))
        print(f"\nResults written to {args.output}")

    # Exit code
    if not passes_all_thresholds(agg):
        print("\nFAILED: One or more dimensions below threshold.")
        sys.exit(1)

    print("\nPASSED: All dimensions meet thresholds.")


if __name__ == "__main__":
    main()
