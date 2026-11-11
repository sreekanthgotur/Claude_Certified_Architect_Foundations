"""Cross-session memory via the memory tool.

Uses tool type memory_20250818 for storing returning-customer
preferences, past resolutions, and ongoing issue context.  Enforces
customer-ID isolation and PII redaction on writes.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

MEMORY_TOOL_TYPE = "memory_20250818"

EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)
PHONE_PATTERN = re.compile(
    r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
)
SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
CREDIT_CARD_PATTERN = re.compile(r"\b(?:\d[ -]*?){13,19}\b")


@dataclass
class MemoryEntry:
    customer_id: str
    key: str
    value: str
    category: str  # "preference" | "resolution" | "context"


class MemoryManager:
    """Manages cross-session customer memory with isolation and PII redaction.

    Every memory key is namespaced by customer_id so one customer's
    data can never leak to another.  All values are scrubbed for PII
    before being stored.
    """

    def __init__(self) -> None:
        self._write_count = 0
        self._read_count = 0
        self._redaction_count = 0

    @property
    def tool_type(self) -> str:
        return MEMORY_TOOL_TYPE

    def build_memory_tool(self) -> dict[str, Any]:
        """Return the memory tool definition for the API request."""
        return {"type": MEMORY_TOOL_TYPE}

    def namespace_key(self, customer_id: str, key: str) -> str:
        """Prefix the key with customer_id for isolation."""
        return f"customer:{customer_id}:{key}"

    def prepare_write(
        self,
        customer_id: str,
        key: str,
        value: str,
        category: str = "context",
    ) -> dict[str, Any]:
        """Build a memory-write payload with PII redaction.

        The value is scrubbed before it reaches the memory tool so
        sensitive data is never persisted.
        """
        namespaced = self.namespace_key(customer_id, key)
        redacted = self.redact_pii(value)

        self._write_count += 1
        logger.info(
            "memory_write",
            extra={
                "customer_id": customer_id,
                "key": key,
                "category": category,
                "redacted": redacted != value,
            },
        )
        return {
            "action": "write",
            "key": namespaced,
            "value": redacted,
            "metadata": {"category": category, "customer_id": customer_id},
        }

    def prepare_read(
        self,
        customer_id: str,
        key: str,
    ) -> dict[str, Any]:
        """Build a memory-read payload scoped to the customer."""
        namespaced = self.namespace_key(customer_id, key)
        self._read_count += 1
        logger.info(
            "memory_read",
            extra={"customer_id": customer_id, "key": key},
        )
        return {"action": "read", "key": namespaced}

    def prepare_search(
        self,
        customer_id: str,
        query: str,
    ) -> dict[str, Any]:
        """Build a memory-search payload scoped to the customer."""
        self._read_count += 1
        return {
            "action": "search",
            "query": query,
            "filter": {"customer_id": customer_id},
        }

    def validate_isolation(
        self,
        customer_id: str,
        memory_key: str,
    ) -> bool:
        """Check that a memory key belongs to the given customer."""
        expected_prefix = f"customer:{customer_id}:"
        return memory_key.startswith(expected_prefix)

    def redact_pii(self, text: str) -> str:
        """Replace common PII patterns with redaction markers."""
        original = text
        text = EMAIL_PATTERN.sub("[EMAIL_REDACTED]", text)
        text = SSN_PATTERN.sub("[SSN_REDACTED]", text)
        text = CREDIT_CARD_PATTERN.sub("[CARD_REDACTED]", text)
        text = PHONE_PATTERN.sub("[PHONE_REDACTED]", text)
        if text != original:
            self._redaction_count += 1
            logger.info("memory_pii_redacted")
        return text

    def get_stats(self) -> dict[str, int]:
        return {
            "writes": self._write_count,
            "reads": self._read_count,
            "redactions": self._redaction_count,
        }
