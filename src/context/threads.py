"""Message threads for server-side conversation state.

Uses the message-threads-2026-08-12 beta so only new messages are sent
each turn, lowering TTFT.  Falls back to full replay on thread expiry.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

THREADS_BETA = "message-threads-2026-08-12"
DEFAULT_THREAD_TTL = 3600  # 1 hour


@dataclass
class ThreadInfo:
    thread_id: str
    created_at: float
    last_used_at: float
    turn_count: int = 0


class ThreadManager:
    """Manages server-side message threads for multi-turn conversations.

    When a thread is active only new messages are sent each turn,
    reducing input tokens and TTFT.  The manager tracks thread
    lifetimes and falls back to full replay when a thread expires.
    """

    def __init__(self, ttl: int = DEFAULT_THREAD_TTL) -> None:
        self._threads: dict[str, ThreadInfo] = {}
        self._ttl = ttl

    @property
    def beta_header(self) -> str:
        return THREADS_BETA

    def get_thread(self, session_id: str) -> ThreadInfo | None:
        info = self._threads.get(session_id)
        if info is None:
            return None
        if self._is_expired(info):
            logger.info(
                "thread_expired",
                extra={"session_id": session_id, "thread_id": info.thread_id},
            )
            del self._threads[session_id]
            return None
        return info

    def create_thread(
        self,
        session_id: str,
        thread_id: str,
    ) -> ThreadInfo:
        now = time.time()
        info = ThreadInfo(
            thread_id=thread_id,
            created_at=now,
            last_used_at=now,
        )
        self._threads[session_id] = info
        logger.info(
            "thread_created",
            extra={"session_id": session_id, "thread_id": thread_id},
        )
        return info

    def prepare_request_params(
        self,
        session_id: str,
        messages: list[dict[str, Any]],
        params: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Add thread header and trim messages if a thread is active.

        Returns (messages_to_send, updated_params).  When a thread is
        active only the most recent user message is sent.  When no
        thread exists or it has expired the full message list is sent
        so the server can create a new thread.
        """
        betas: list[str] = list(params.get("betas", []))
        if THREADS_BETA not in betas:
            betas.append(THREADS_BETA)
        params = {**params, "betas": betas}

        thread = self.get_thread(session_id)
        if thread is None:
            return messages, params

        params["thread_id"] = thread.thread_id
        latest = [m for m in messages if m.get("role") == "user"]
        if latest:
            messages_to_send = [latest[-1]]
        else:
            messages_to_send = messages

        thread.last_used_at = time.time()
        thread.turn_count += 1

        logger.info(
            "thread_reused",
            extra={
                "session_id": session_id,
                "thread_id": thread.thread_id,
                "turn": thread.turn_count,
                "messages_sent": len(messages_to_send),
                "messages_total": len(messages),
            },
        )
        return messages_to_send, params

    def handle_response_thread(
        self,
        session_id: str,
        response_headers: dict[str, Any],
    ) -> None:
        """Extract and store thread_id from the API response."""
        thread_id = response_headers.get("thread_id")
        if not thread_id:
            return
        existing = self.get_thread(session_id)
        if existing is None or existing.thread_id != thread_id:
            self.create_thread(session_id, thread_id)

    def remove_thread(self, session_id: str) -> None:
        removed = self._threads.pop(session_id, None)
        if removed:
            logger.info(
                "thread_removed",
                extra={
                    "session_id": session_id,
                    "thread_id": removed.thread_id,
                },
            )

    def _is_expired(self, info: ThreadInfo) -> bool:
        return (time.time() - info.last_used_at) > self._ttl
