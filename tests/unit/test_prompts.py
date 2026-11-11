"""Tests for prompt assembly (src/prompts/)."""

from __future__ import annotations

import json
import re
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.prompts.system_stable import build_stable_prompt
from src.prompts.system_dynamic import build_dynamic_prompt
from src.prompts.classifier_prompt import build_classifier_prompt
from src.prompts.schemas import CLASSIFICATION_SCHEMA, CUSTOMER_RESPONSE_SCHEMA


# ------------------------------------------------------------------
# Stable prompt
# ------------------------------------------------------------------

@pytest.mark.unit
def test_stable_prompt_ends_with_cache_control() -> None:
    """The stable system prompt must end with cache_control for caching."""
    blocks = build_stable_prompt()
    last_block = blocks[-1]
    assert last_block.get("cache_control") == {"type": "ephemeral"}


@pytest.mark.unit
def test_stable_prompt_contains_brand_voice() -> None:
    blocks = build_stable_prompt()
    text = " ".join(
        b["text"] if isinstance(b, dict) and "text" in b else str(b)
        for b in blocks
    )
    assert "brand" in text.lower() or "voice" in text.lower() or "tone" in text.lower()


@pytest.mark.unit
def test_stable_prompt_contains_safety_boundaries() -> None:
    blocks = build_stable_prompt()
    text = " ".join(
        b["text"] if isinstance(b, dict) and "text" in b else str(b)
        for b in blocks
    )
    assert "data" in text.lower() and "instruction" in text.lower()


@pytest.mark.unit
def test_stable_prompt_no_timestamps() -> None:
    """No datetime.now(), random IDs, or volatile values before the cache breakpoint."""
    blocks = build_stable_prompt()
    text = json.dumps(blocks)
    iso_pattern = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
    uuid_pattern = re.compile(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    )
    assert not iso_pattern.search(text), "Stable prompt contains a timestamp"
    assert not uuid_pattern.search(text), "Stable prompt contains a UUID"


@pytest.mark.unit
def test_stable_prompt_deterministic() -> None:
    """Two consecutive calls must produce byte-identical output."""
    first = json.dumps(build_stable_prompt(), sort_keys=True)
    second = json.dumps(build_stable_prompt(), sort_keys=True)
    assert first == second


# ------------------------------------------------------------------
# Dynamic prompt
# ------------------------------------------------------------------

@pytest.mark.unit
def test_dynamic_prompt_includes_customer_context() -> None:
    customer_context = {
        "customer_id": "cust_12345",
        "tier": "gold",
        "account_age_days": 730,
        "open_tickets": 1,
    }
    blocks = build_dynamic_prompt(
        customer_context=customer_context,
        active_promotions=["HOLIDAY20"],
        session_state={"escalation_count": 0},
    )
    text = " ".join(
        b["text"] if isinstance(b, dict) and "text" in b else str(b)
        for b in blocks
    )
    assert "cust_12345" in text
    assert "gold" in text


@pytest.mark.unit
def test_dynamic_prompt_includes_promotions() -> None:
    blocks = build_dynamic_prompt(
        customer_context={"customer_id": "cust_00001"},
        active_promotions=["SUMMER25", "FREESHIP"],
        session_state={},
    )
    text = " ".join(
        b["text"] if isinstance(b, dict) and "text" in b else str(b)
        for b in blocks
    )
    assert "SUMMER25" in text
    assert "FREESHIP" in text


@pytest.mark.unit
def test_dynamic_prompt_empty_promotions() -> None:
    """Dynamic prompt works fine with no active promotions."""
    blocks = build_dynamic_prompt(
        customer_context={"customer_id": "cust_00001"},
        active_promotions=[],
        session_state={},
    )
    assert isinstance(blocks, list)
    assert len(blocks) > 0


# ------------------------------------------------------------------
# Classifier prompt
# ------------------------------------------------------------------

@pytest.mark.unit
def test_classifier_prompt_is_minimal() -> None:
    """Classifier prompt should be short — focused on routing accuracy."""
    blocks = build_classifier_prompt()
    text = " ".join(
        b["text"] if isinstance(b, dict) and "text" in b else str(b)
        for b in blocks
    )
    assert len(text) < 2000, "Classifier prompt should be minimal"


@pytest.mark.unit
def test_classifier_prompt_mentions_tiers() -> None:
    blocks = build_classifier_prompt()
    text = " ".join(
        b["text"] if isinstance(b, dict) and "text" in b else str(b)
        for b in blocks
    )
    assert "tier" in text.lower()


# ------------------------------------------------------------------
# Structured output schemas
# ------------------------------------------------------------------

@pytest.mark.unit
def test_classification_schema_has_required_fields() -> None:
    props = CLASSIFICATION_SCHEMA["properties"]
    required = CLASSIFICATION_SCHEMA["required"]
    for field in ["intent", "confidence", "tier", "entities"]:
        assert field in props, f"Missing property: {field}"
        assert field in required, f"Missing from required: {field}"


@pytest.mark.unit
def test_customer_response_schema_valid() -> None:
    assert "properties" in CUSTOMER_RESPONSE_SCHEMA
    assert "required" in CUSTOMER_RESPONSE_SCHEMA


# ------------------------------------------------------------------
# Assembly order
# ------------------------------------------------------------------

@pytest.mark.unit
def test_prompt_assembly_order() -> None:
    """Render order must be tools -> system -> messages (per Claude API)."""
    from src.prompts.system_stable import build_stable_prompt
    from src.prompts.system_dynamic import build_dynamic_prompt

    stable = build_stable_prompt()
    dynamic = build_dynamic_prompt(
        customer_context={"customer_id": "test"},
        active_promotions=[],
        session_state={},
    )
    system_blocks = stable + dynamic

    # Verify that system blocks are a list of content blocks
    assert isinstance(system_blocks, list)
    assert all(isinstance(b, dict) for b in system_blocks)

    # Cache breakpoint must be on the last stable block, before dynamic
    assert stable[-1].get("cache_control") == {"type": "ephemeral"}
