"""Context editing to strip old tool results and thinking blocks.

Uses the context-management-2025-06-27 beta to reduce input tokens
per turn.  Target: >30 % reduction after tool-heavy sequences.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

CONTEXT_MGMT_BETA = "context-management-2025-06-27"
CLEAR_TOOL_USES = "clear_tool_uses_20250919"
CLEAR_THINKING = "clear_thinking_20251015"
MIN_TURNS_BEFORE_EDIT = 4
TOKEN_REDUCTION_TARGET = 0.30


@dataclass
class EditStats:
    edits_applied: int = 0
    total_tokens_saved: int = 0
    last_reduction_pct: float = 0.0


class ContextEditor:
    """Strips stale tool results and thinking blocks from the context.

    After several tool-heavy turns the context grows fast.  This editor
    injects ``clear_tool_uses`` and ``clear_thinking`` directives that
    the server processes to trim old content, keeping only the most
    recent tool results and removing all thinking blocks.
    """

    def __init__(
        self,
        min_turns: int = MIN_TURNS_BEFORE_EDIT,
    ) -> None:
        self._min_turns = min_turns
        self._stats = EditStats()
        self._tool_turn_count = 0

    @property
    def stats(self) -> EditStats:
        return self._stats

    @property
    def beta_header(self) -> str:
        return CONTEXT_MGMT_BETA

    def record_tool_turn(self) -> None:
        """Call after each turn that contained tool use."""
        self._tool_turn_count += 1

    def should_edit(self) -> bool:
        return self._tool_turn_count >= self._min_turns

    def build_edit_directives(
        self,
        keep_recent_tool_turns: int = 2,
    ) -> list[dict[str, Any]]:
        """Return context-edit content blocks for the API request.

        These directives tell the server to clear old tool results and
        all thinking blocks, keeping only the N most recent tool turns.
        """
        if not self.should_edit():
            return []

        directives: list[dict[str, Any]] = [
            {
                "type": CLEAR_TOOL_USES,
                "keep_recent": keep_recent_tool_turns,
            },
            {
                "type": CLEAR_THINKING,
            },
        ]
        logger.info(
            "context_edit_directives",
            extra={
                "tool_turns": self._tool_turn_count,
                "keep_recent": keep_recent_tool_turns,
            },
        )
        return directives

    def prepare_request_params(
        self,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Inject context-management beta and edit directives."""
        if not self.should_edit():
            return params

        betas: list[str] = list(params.get("betas", []))
        if CONTEXT_MGMT_BETA not in betas:
            betas.append(CONTEXT_MGMT_BETA)
        params = {**params, "betas": betas}
        return params

    def record_reduction(
        self,
        tokens_before: int,
        tokens_after: int,
    ) -> None:
        """Record the token reduction achieved by editing."""
        if tokens_before == 0:
            return
        saved = tokens_before - tokens_after
        pct = saved / tokens_before

        self._stats.edits_applied += 1
        self._stats.total_tokens_saved += max(0, saved)
        self._stats.last_reduction_pct = round(pct, 4)
        self._tool_turn_count = 0

        logger.info(
            "context_edit_result",
            extra={
                "tokens_before": tokens_before,
                "tokens_after": tokens_after,
                "reduction_pct": round(pct * 100, 1),
                "meets_target": pct >= TOKEN_REDUCTION_TARGET,
            },
        )
