from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import anthropic

from src.orchestrator.models import (
    CLASSIFICATION_JSON_SCHEMA,
    ClassificationResult,
    Intent,
    TierEnum,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

CLASSIFIER_SYSTEM_PROMPT = (
    "You are an intent classifier for a customer support system. "
    "Analyze the customer message and classify it.\n\n"
    "Return a JSON object with:\n"
    "- intent: the customer's primary intent\n"
    "- confidence: your confidence in the classification (0.0 to 1.0)\n"
    "- tier: the support tier to route to\n"
    "  - tier_1: simple FAQ/knowledge questions answerable from documents\n"
    "  - tier_2: actions requiring tool use (order lookup, returns, "
    "subscription changes, ticket creation)\n"
    "  - tier_3: complex multi-step investigations requiring extended reasoning\n"
    "- entities: extracted entities (order IDs, product names, amounts, etc.)\n\n"
    "Be precise. If unsure, lower your confidence score."
)

CONFIDENCE_TIER1_THRESHOLD = 0.85
CONFIDENCE_ESCALATION_THRESHOLD = 0.6


class IntentClassifier:
    def __init__(
        self,
        client: anthropic.AsyncAnthropic | None = None,
        model: str = "claude-haiku-5-5",
    ) -> None:
        self._client = client or anthropic.AsyncAnthropic()
        self._model = model

    async def classify(self, message: str) -> ClassificationResult:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=512,
            effort="low",
            system=CLASSIFIER_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": message}],
            output_config={"format": CLASSIFICATION_JSON_SCHEMA},
        )

        raw_text = _extract_text(response)
        parsed = json.loads(raw_text)
        result = ClassificationResult(**parsed)

        logger.info(
            "Classified message: intent=%s confidence=%.2f tier=%s",
            result.intent.value,
            result.confidence,
            result.tier.value,
        )

        result = self._apply_routing_rules(result)
        return result

    def _apply_routing_rules(
        self, result: ClassificationResult
    ) -> ClassificationResult:
        if result.intent in (Intent.ACCOUNT_DELETION, Intent.LEGAL):
            return result

        if result.confidence < CONFIDENCE_ESCALATION_THRESHOLD:
            return result

        if (
            result.tier == TierEnum.TIER_1
            and result.confidence < CONFIDENCE_TIER1_THRESHOLD
        ):
            return ClassificationResult(
                intent=result.intent,
                confidence=result.confidence,
                tier=TierEnum.TIER_2,
                entities=result.entities,
            )

        return result


def _extract_text(response: anthropic.types.Message) -> str:
    for block in response.content:
        if block.type == "text":
            return block.text
    raise ValueError("No text block in classifier response")
